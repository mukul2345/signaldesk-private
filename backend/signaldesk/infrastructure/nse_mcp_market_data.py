from __future__ import annotations

import json
import os
import time as clock
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List, Optional, Protocol
from zoneinfo import ZoneInfo

import httpx

from signaldesk.config import CorporateActionSettings, NseMcpSettings
from signaldesk.domain.models import (
    DailyBar,
    InstrumentBars,
    MarketDataWarmupStatus,
    MarketIndex,
    ProviderReadiness,
)

from .corporate_action_adjustment import CorporateActionAdjuster


class NseMcpError(RuntimeError):
    pass


class NseMcpToolClient(Protocol):
    def call_tool(self, name: str, arguments: dict) -> dict: ...


class NseMcpHttpClient:
    def __init__(
        self,
        url: str,
        timeout_seconds: float,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._url = url
        self._http = http_client or httpx.Client(timeout=timeout_seconds)
        self._session_id: Optional[str] = None
        self._request_id = 0

    @staticmethod
    def _decode(response: httpx.Response) -> dict:
        if response.is_error:
            raise NseMcpError(f"NSE MCP returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            try:
                return response.json()
            except ValueError as error:
                raise NseMcpError("NSE MCP returned invalid JSON") from error
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError as error:
                    raise NseMcpError("NSE MCP returned invalid event data") from error
        raise NseMcpError("NSE MCP event stream contained no response")

    def _post(self, payload: dict, expect_response: bool = True) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        response = self._http.post(self._url, headers=headers, json=payload)
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id
        if not expect_response:
            if response.is_error:
                raise NseMcpError(
                    f"NSE MCP initialization notification returned HTTP {response.status_code}"
                )
            return {}
        decoded = self._decode(response)
        if "error" in decoded:
            message = decoded["error"].get("message", "Unknown MCP error")
            raise NseMcpError(f"NSE MCP error: {message}")
        return decoded

    def _initialize(self) -> None:
        self._request_id += 1
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "signaldesk-private",
                        "version": "0.1.0",
                    },
                },
            }
        )
        if response.get("result", {}).get("serverInfo", {}).get("name") is None:
            raise NseMcpError("NSE MCP initialization response is incomplete")
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_response=False,
        )

    def call_tool(self, name: str, arguments: dict) -> dict:
        if self._session_id is None:
            self._initialize()
        self._request_id += 1
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        result = response.get("result", {})
        if result.get("isError"):
            raise NseMcpError(f"NSE MCP tool {name} reported an error")
        for item in result.get("content", []):
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except (KeyError, json.JSONDecodeError) as error:
                    raise NseMcpError(
                        f"NSE MCP tool {name} returned invalid JSON text"
                    ) from error
        raise NseMcpError(f"NSE MCP tool {name} returned no JSON content")


class NseMcpDailyBarProvider:
    CACHE_VERSION = 1

    def __init__(
        self,
        settings: NseMcpSettings,
        required_bars: int,
        corporate_action_settings: Optional[CorporateActionSettings] = None,
        client: Optional[NseMcpToolClient] = None,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        monotonic: Callable[[], float] = clock.monotonic,
    ) -> None:
        self._settings = settings
        self._required_bars = required_bars
        self._corporate_action_adjuster = (
            CorporateActionAdjuster(corporate_action_settings)
            if corporate_action_settings is not None
            else None
        )
        self._client = client or NseMcpHttpClient(
            settings.bhavcopy_url, settings.request_timeout_seconds
        )
        self._now = now
        self._monotonic = monotonic
        self._lock = Lock()
        self._cached_instruments: Optional[List[InstrumentBars]] = None
        self._cached_at = 0.0
        self._market_supportive = False
        self._indices: List[MarketIndex] = []
        self._last_session: Optional[str] = None
        self._healthy = False
        self._active_universe_path = (
            settings.promoted_universe_path
            if settings.promoted_universe_path.exists()
            else settings.universe_path
        )

    def source(self) -> str:
        return "official_nse_bhavcopy_mcp"

    def cutoff_time(self) -> str:
        return self._settings.cutoff_time

    def market_supportive(self) -> bool:
        return self._market_supportive

    def indices(self) -> List[MarketIndex]:
        return list(self._indices)

    def readiness(self) -> ProviderReadiness:
        if self._healthy:
            return ProviderReadiness(
                status="HEALTHY",
                detail=f"Official NSE Bhavcopy MCP · latest session {self._last_session}",
            )
        return ProviderReadiness(
            status="READY",
            detail="Official NSE Bhavcopy MCP selected · first refresh pending",
        )

    def _universe_payload(self, path: Path) -> dict:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise NseMcpError(f"NSE universe is unreadable: {path.name}") from error
        instruments = payload.get("instruments", [])
        symbols = [str(item.get("symbol", "")).upper() for item in instruments]
        if not instruments or any(
            not symbol
            or not str(item.get("company", "")).strip()
            or not str(item.get("sector", "")).strip()
            for symbol, item in zip(symbols, instruments)
        ):
            raise NseMcpError("NSE universe is empty or contains a blank field")
        if len(symbols) != len(set(symbols)):
            raise NseMcpError("NSE universe contains duplicate symbols")
        if not str(payload.get("version", "")).strip():
            raise NseMcpError("NSE universe version is missing")
        return payload

    def _universe(self) -> List[dict]:
        return self._universe_payload(self._active_universe_path)["instruments"]

    def _load_cache(self) -> dict:
        path = self._settings.cache_path
        if not path.exists():
            return {"version": self.CACHE_VERSION, "bars": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise NseMcpError("NSE market-data cache is unreadable") from error
        if payload.get("version") != self.CACHE_VERSION:
            return {"version": self.CACHE_VERSION, "bars": {}}
        return payload

    def _save_cache(self, payload: dict) -> None:
        path = self._settings.cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        os.replace(temporary, path)

    def _warmup_status(
        self,
        candidate: Optional[dict] = None,
        cache: Optional[dict] = None,
    ) -> MarketDataWarmupStatus:
        active_count = len(self._universe())
        if candidate is None:
            path = self._settings.universe_candidate_path
            if not path.exists():
                return MarketDataWarmupStatus(
                    available=False,
                    totalSymbols=0,
                    warmedSymbols=0,
                    remainingSymbols=0,
                    batchSize=self._settings.history_warmup_batch_size,
                    activeUniverseSymbols=active_count,
                    failedSymbols=[],
                    readyToActivate=False,
                )
            candidate = self._universe_payload(path)
        cache = cache or self._load_cache()
        bars_by_symbol = cache.get("bars", {})
        symbols = [str(item["symbol"]).upper() for item in candidate["instruments"]]
        warmed = sum(
            1
            for symbol in symbols
            if len(bars_by_symbol.get(symbol, [])) >= self._required_bars
        )
        metadata = cache.get("warmup", {})
        if metadata.get("target_version") != candidate["version"]:
            metadata = {}
        failures = metadata.get("errors", {})
        return MarketDataWarmupStatus(
            available=True,
            targetVersion=str(candidate["version"]),
            totalSymbols=len(symbols),
            warmedSymbols=warmed,
            remainingSymbols=len(symbols) - warmed,
            batchSize=self._settings.history_warmup_batch_size,
            activeUniverseSymbols=active_count,
            failedSymbols=sorted(
                symbol for symbol in failures if symbol in set(symbols)
            ),
            lastUpdatedAt=metadata.get("updated_at"),
            readyToActivate=warmed == len(symbols) and not failures,
        )

    def warmup_status(self) -> MarketDataWarmupStatus:
        with self._lock:
            return self._warmup_status()

    def warmup_next_batch(self) -> MarketDataWarmupStatus:
        with self._lock:
            path = self._settings.universe_candidate_path
            if not path.exists():
                raise NseMcpError(
                    "Nifty 500 candidate is unavailable; run the universe sync first"
                )
            candidate = self._universe_payload(path)
            cache = self._load_cache()
            bars_by_symbol = cache.setdefault("bars", {})
            metadata = cache.setdefault("warmup", {})
            if metadata.get("target_version") != candidate["version"]:
                metadata = {
                    "target_version": candidate["version"],
                    "errors": {},
                }
                cache["warmup"] = metadata
            errors = metadata.setdefault("errors", {})
            symbols = [
                str(item["symbol"]).upper() for item in candidate["instruments"]
            ]
            missing = [
                symbol
                for symbol in symbols
                if len(bars_by_symbol.get(symbol, [])) < self._required_bars
            ]
            unattempted = [symbol for symbol in missing if symbol not in errors]
            batch_pool = unattempted if unattempted else missing
            batch = batch_pool[: self._settings.history_warmup_batch_size]
            for symbol in batch:
                try:
                    bars_by_symbol[symbol] = [
                        bar.model_dump(mode="json") for bar in self._history(symbol)
                    ]
                    errors.pop(symbol, None)
                except Exception as error:
                    errors[symbol] = str(error)
            metadata["updated_at"] = self._now().isoformat()
            metadata["last_batch"] = batch
            self._save_cache(cache)
            return self._warmup_status(candidate, cache)

    @staticmethod
    def _bar(item: dict) -> DailyBar:
        return DailyBar(
            session=item["date"],
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item["volume"]),
        )

    @staticmethod
    def _upsert(bars: List[DailyBar], bar: DailyBar) -> List[DailyBar]:
        by_session = {item.session: item for item in bars}
        by_session[bar.session] = bar
        return [by_session[key] for key in sorted(by_session)]

    def _history(self, symbol: str) -> List[DailyBar]:
        payload = self._client.call_tool(
            "get_stock_history",
            {
                "symbol": symbol,
                "months": self._settings.history_months,
                "endDate": "today",
            },
        )
        if payload.get("symbol") != symbol or not isinstance(payload.get("data"), list):
            raise NseMcpError(f"NSE history response is invalid for {symbol}")
        bars = [self._bar(item) for item in payload["data"]]
        if len(bars) < self._required_bars:
            raise NseMcpError(
                f"NSE returned {len(bars)} bars for {symbol}; {self._required_bars} required"
            )
        return bars

    def _bulk_refresh(self, symbols: List[str], bars_by_symbol: Dict[str, List[DailyBar]]) -> None:
        size = self._settings.bulk_batch_size
        for offset in range(0, len(symbols), size):
            batch = symbols[offset : offset + size]
            payload = self._client.call_tool("get_bulk_quote", {"symbols": batch})
            quotes = payload.get("quotes")
            if not isinstance(quotes, list):
                raise NseMcpError("NSE bulk quote response is invalid")
            returned = set()
            for item in quotes:
                symbol = str(item.get("symbol", "")).upper()
                if symbol not in bars_by_symbol:
                    continue
                returned.add(symbol)
                bars_by_symbol[symbol] = self._upsert(
                    bars_by_symbol[symbol], self._bar(item)
                )
            missing = set(batch) - returned
            if missing:
                raise NseMcpError(
                    "NSE bulk quote omitted symbols: " + ", ".join(sorted(missing))
                )

    def _apply_market_mood(self, payload: dict) -> None:
        breadth = payload.get("stock_breadth", {})
        up_percent = breadth.get("up_pct")
        if up_percent is None:
            raise NseMcpError("NSE market mood omitted stock breadth")
        self._market_supportive = (
            float(up_percent)
            >= self._settings.market_supportive_min_stock_up_percent
        )
        benchmarks = payload.get("benchmarks", {})
        indices = []
        for name in self._settings.index_names:
            item = benchmarks.get(name)
            if item is None:
                raise NseMcpError(f"NSE market mood omitted index {name}")
            close = float(item["close"])
            change = float(item["change_pct"])
            base = close / (1 + change / 100) if change != -100 else close
            indices.append(
                MarketIndex(
                    id=name.lower().replace(" ", "-"),
                    name=name.upper(),
                    value=close,
                    changePercent=change,
                    direction="up" if change > 0 else "down" if change < 0 else "flat",
                    status="Positive" if change > 0 else "Weak" if change < 0 else "Flat",
                    points=[base, close],
                )
            )
        self._indices = indices
        self._last_session = str(payload.get("date"))

    def _from_payload(self, universe: List[dict], payload: dict) -> List[InstrumentBars]:
        bars_payload = payload.get("bars", {})
        results = []
        for item in universe:
            symbol = str(item["symbol"]).upper()
            rows = bars_payload.get(symbol, [])
            bars = [DailyBar.model_validate(row) for row in rows]
            if len(bars) < self._required_bars:
                raise NseMcpError(f"NSE cache is incomplete for {symbol}")
            if self._corporate_action_adjuster is not None:
                reconciliation = self._corporate_action_adjuster.adjust(symbol, bars)
                if reconciliation.unresolved_subjects:
                    raise NseMcpError(
                        f"Corporate-action adjustment is unresolved for {symbol}"
                    )
                bars = reconciliation.bars
            results.append(
                InstrumentBars(
                    symbol=symbol,
                    company=item["company"],
                    sector=item["sector"],
                    bars=bars,
                )
            )
        self._apply_market_mood(payload.get("market_mood", {}))
        return results

    def _refresh(self, universe: List[dict], payload: dict) -> List[InstrumentBars]:
        cached = payload.get("bars", {})
        bars_by_symbol: Dict[str, List[DailyBar]] = {}
        for item in universe:
            symbol = str(item["symbol"]).upper()
            rows = cached.get(symbol, [])
            bars = [DailyBar.model_validate(row) for row in rows]
            bars_by_symbol[symbol] = (
                bars if len(bars) >= self._required_bars else self._history(symbol)
            )
        symbols = list(bars_by_symbol)
        self._bulk_refresh(symbols, bars_by_symbol)
        mood = self._client.call_tool("get_market_mood", {"date": "today"})
        retained_bars = {
            str(symbol): rows[-max(self._required_bars + 10, 90) :]
            for symbol, rows in cached.items()
            if isinstance(rows, list)
        }
        retained_bars.update(
            {
                symbol: [
                    bar.model_dump(mode="json")
                    for bar in bars[-max(self._required_bars + 10, 90) :]
                ]
                for symbol, bars in bars_by_symbol.items()
            }
        )
        refreshed = {
            "version": self.CACHE_VERSION,
            "refreshed_at": self._now().isoformat(),
            "market_mood": mood,
            "bars": retained_bars,
        }
        self._save_cache(refreshed)
        return self._from_payload(universe, refreshed)

    def instruments(self) -> List[InstrumentBars]:
        with self._lock:
            tick = self._monotonic()
            if self._cached_instruments is not None and (
                tick - self._cached_at <= self._settings.cache_ttl_seconds
            ):
                return self._cached_instruments
            universe = self._universe()
            cached = self._load_cache()
            refreshed_at = cached.get("refreshed_at")
            fresh = False
            if refreshed_at:
                refreshed = datetime.fromisoformat(refreshed_at)
                now = self._now().astimezone(ZoneInfo(self._settings.timezone))
                fresh = (
                    now - refreshed.astimezone(ZoneInfo(self._settings.timezone))
                ).total_seconds() <= self._settings.cache_ttl_seconds
            if fresh:
                instruments = self._from_payload(universe, cached)
            else:
                instruments = self._refresh(universe, cached)
            self._cached_instruments = instruments
            self._cached_at = tick
            self._healthy = True
            return instruments
