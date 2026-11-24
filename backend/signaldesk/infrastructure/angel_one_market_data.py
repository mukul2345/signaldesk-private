from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time as clock
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence
from zoneinfo import ZoneInfo

import httpx

from signaldesk.config import AngelOneSettings
from signaldesk.domain.models import (
    DailyBar,
    InstrumentBars,
    MarketIndex,
    ProviderReadiness,
)
from signaldesk.domain.ports import DailyBarProvider

class AngelOneError(RuntimeError):
    pass


@dataclass(frozen=True)
class AngelOneCredentials:
    api_key: str
    client_code: str
    pin: str
    totp_secret: str
    client_local_ip: str
    client_public_ip: str
    mac_address: str

    @classmethod
    def from_environment(
        cls, environment: Optional[Mapping[str, str]] = None
    ) -> "AngelOneCredentials":
        values = environment if environment is not None else os.environ
        return cls(
            api_key=values.get("ANGEL_API_KEY", "").strip(),
            client_code=values.get("ANGEL_CLIENT_CODE", "").strip(),
            pin=values.get("ANGEL_PIN", "").strip(),
            totp_secret=values.get("ANGEL_TOTP_SECRET", "").strip(),
            client_local_ip=values.get("ANGEL_CLIENT_LOCAL_IP", "127.0.0.1").strip(),
            client_public_ip=values.get("ANGEL_CLIENT_PUBLIC_IP", "").strip(),
            mac_address=values.get("ANGEL_MAC_ADDRESS", "").strip(),
        )

    def missing_environment_fields(self) -> List[str]:
        required = {
            "ANGEL_API_KEY": self.api_key,
            "ANGEL_CLIENT_CODE": self.client_code,
            "ANGEL_PIN": self.pin,
            "ANGEL_TOTP_SECRET": self.totp_secret,
            "ANGEL_CLIENT_PUBLIC_IP": self.client_public_ip,
            "ANGEL_MAC_ADDRESS": self.mac_address,
        }
        return [name for name, value in required.items() if not value]


def _credential_problem(
    credentials: AngelOneCredentials,
) -> Optional[ProviderReadiness]:
    missing = credentials.missing_environment_fields()
    invalid_totp = False
    if credentials.totp_secret:
        try:
            generate_totp(credentials.totp_secret)
        except AngelOneError:
            invalid_totp = True
    details = []
    if missing:
        details.append("Missing " + ", ".join(missing))
    if invalid_totp:
        details.append("ANGEL_TOTP_SECRET is not a valid Base32 setup secret")
    if not details:
        return None
    return ProviderReadiness(
        status="NOT_CONFIGURED" if missing else "ERROR",
        detail=" · ".join(details),
    )


@dataclass(frozen=True)
class AngelOneInstrument:
    symbol: str
    company: str
    sector: str
    symbol_token: str


class AngelOneCandleClient(Protocol):
    @property
    def authenticated(self) -> bool: ...

    def candles(
        self,
        symbol_token: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Sequence[object]]: ...


def generate_totp(secret: str, at: Optional[int] = None) -> str:
    normalized = secret.replace(" ", "").upper()
    try:
        key = base64.b32decode(normalized, casefold=True)
    except Exception as error:
        raise AngelOneError("ANGEL_TOTP_SECRET is not valid Base32") from error
    counter = int(at if at is not None else clock.time()) // 30
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


class AngelOneHttpClient:
    LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
    CANDLES_PATH = "/rest/secure/angelbroking/historical/v1/getCandleData"

    def __init__(
        self,
        settings: AngelOneSettings,
        credentials: AngelOneCredentials,
        http_client: Optional[httpx.Client] = None,
        clock_seconds: Callable[[], float] = clock.time,
    ) -> None:
        self._settings = settings
        self._credentials = credentials
        self._clock_seconds = clock_seconds
        self._http = http_client or httpx.Client(
            base_url=settings.base_url,
            timeout=settings.request_timeout_seconds,
        )
        self._access_token: Optional[str] = None

    @property
    def authenticated(self) -> bool:
        return self._access_token is not None

    def _headers(self, authorized: bool = False) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": self._credentials.client_local_ip,
            "X-ClientPublicIP": self._credentials.client_public_ip,
            "X-MACAddress": self._credentials.mac_address,
            "X-PrivateKey": self._credentials.api_key,
        }
        if authorized and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    @staticmethod
    def _payload(response: httpx.Response, operation: str) -> dict:
        try:
            payload = response.json()
        except ValueError as error:
            raise AngelOneError(f"Angel One {operation} returned invalid JSON") from error
        if response.is_error or payload.get("status") is not True:
            message = payload.get("message") or f"HTTP {response.status_code}"
            raise AngelOneError(f"Angel One {operation} failed: {message}")
        return payload

    def authenticate(self) -> None:
        missing = self._credentials.missing_environment_fields()
        if missing:
            raise AngelOneError("Missing Angel One credentials: " + ", ".join(missing))
        response = self._http.post(
            self.LOGIN_PATH,
            headers=self._headers(),
            json={
                "clientcode": self._credentials.client_code,
                "password": self._credentials.pin,
                "totp": generate_totp(
                    self._credentials.totp_secret, int(self._clock_seconds())
                ),
            },
        )
        payload = self._payload(response, "authentication")
        token = payload.get("data", {}).get("jwtToken")
        if not token:
            raise AngelOneError("Angel One authentication did not return a JWT")
        self._access_token = str(token)

    def candles(
        self,
        symbol_token: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Sequence[object]]:
        if not self.authenticated:
            self.authenticate()
        response = self._http.post(
            self.CANDLES_PATH,
            headers=self._headers(authorized=True),
            json={
                "exchange": exchange,
                "symboltoken": symbol_token,
                "interval": interval,
                "fromdate": start.strftime("%Y-%m-%d %H:%M"),
                "todate": end.strftime("%Y-%m-%d %H:%M"),
            },
        )
        payload = self._payload(response, "historical candle request")
        data = payload.get("data")
        if not isinstance(data, list):
            raise AngelOneError("Angel One historical candle data is missing")
        return data


class AngelOneDailyBarProvider:
    def __init__(
        self,
        settings: AngelOneSettings,
        credentials: AngelOneCredentials,
        client: Optional[AngelOneCandleClient] = None,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        monotonic: Callable[[], float] = clock.monotonic,
    ) -> None:
        self._settings = settings
        self._credentials = credentials
        self._client = client or AngelOneHttpClient(settings, credentials)
        self._now = now
        self._monotonic = monotonic
        self._cache: Optional[List[InstrumentBars]] = None
        self._cached_at = 0.0

    def source(self) -> str:
        return "angel_one_daily_candles"

    def market_supportive(self) -> bool:
        return self._settings.market_supportive

    def cutoff_time(self) -> str:
        return self._settings.cutoff_time

    def readiness(self) -> ProviderReadiness:
        problem = _credential_problem(self._credentials)
        if problem is not None:
            return problem
        if self._client.authenticated:
            return ProviderReadiness(
                status="HEALTHY",
                detail="Authenticated in memory; secrets are not exposed or persisted",
            )
        return ProviderReadiness(
            status="READY",
            detail="Credentials present; authentication occurs on the first candle request",
        )

    def indices(self) -> List[MarketIndex]:
        return []

    def _instrument_manifest(self) -> List[AngelOneInstrument]:
        path = self._settings.instruments_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        instruments = []
        for item in payload.get("instruments", []):
            token = str(item.get("symbol_token", "")).strip()
            if not token or token.startswith("REPLACE_"):
                raise AngelOneError(
                    f"Angel One symbol token is not configured for {item.get('symbol', 'unknown')}"
                )
            instruments.append(
                AngelOneInstrument(
                    symbol=str(item["symbol"]),
                    company=str(item["company"]),
                    sector=str(item["sector"]),
                    symbol_token=token,
                )
            )
        if not instruments:
            raise AngelOneError("Angel One instrument manifest is empty")
        return instruments

    def _completed_bars(
        self, rows: Sequence[Sequence[object]], current: datetime
    ) -> List[DailyBar]:
        zone = ZoneInfo(self._settings.timezone)
        local_now = current.astimezone(zone)
        cutoff = time.fromisoformat(self._settings.cutoff_time)
        by_session: Dict[date, DailyBar] = {}
        for row in rows:
            if len(row) < 6:
                raise AngelOneError("Angel One candle row has fewer than six fields")
            timestamp = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=zone)
            session = timestamp.astimezone(zone).date()
            if session > local_now.date() or (
                session == local_now.date() and local_now.time() < cutoff
            ):
                continue
            by_session[session] = DailyBar(
                session=session,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        return [by_session[key] for key in sorted(by_session)]

    def instruments(self) -> List[InstrumentBars]:
        now_tick = self._monotonic()
        if self._cache is not None and (
            now_tick - self._cached_at <= self._settings.cache_ttl_seconds
        ):
            return self._cache
        current = self._now()
        zone = ZoneInfo(self._settings.timezone)
        local_now = current.astimezone(zone)
        start = datetime.combine(
            local_now.date() - timedelta(days=self._settings.lookback_calendar_days),
            time.min,
            tzinfo=zone,
        )
        end = datetime.combine(local_now.date(), time.max, tzinfo=zone)
        results = []
        for instrument in self._instrument_manifest():
            rows = self._client.candles(
                instrument.symbol_token,
                self._settings.exchange,
                self._settings.interval,
                start,
                end,
            )
            results.append(
                InstrumentBars(
                    symbol=instrument.symbol,
                    company=instrument.company,
                    sector=instrument.sector,
                    bars=self._completed_bars(rows, current),
                )
            )
        self._cache = results
        self._cached_at = now_tick
        return results


def angel_one_credential_readiness(
    credentials: AngelOneCredentials, active_provider: DailyBarProvider
) -> ProviderReadiness:
    problem = _credential_problem(credentials)
    if problem is not None:
        return ProviderReadiness(
            status=problem.status,
            detail="Inactive · " + problem.detail,
        )
    if isinstance(active_provider, AngelOneDailyBarProvider):
        return active_provider.readiness()
    return ProviderReadiness(
        status="READY",
        detail="Credentials present · switch market-data provider to activate",
    )
