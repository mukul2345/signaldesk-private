from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol

import httpx

from signaldesk.config import CorporateActionSettings


class CorporateActionError(RuntimeError):
    pass


class CorporateActionResponse(Protocol):
    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class CorporateActionHttpClient(Protocol):
    def get(self, url: str, params: dict) -> CorporateActionResponse: ...


class NseCorporateActionClient:
    CACHE_VERSION = 1

    def __init__(
        self,
        settings: CorporateActionSettings,
        http_client: Optional[CorporateActionHttpClient] = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._settings = settings
        self._now = now
        self._http = http_client or httpx.Client(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 SignalDesk-Private/0.1",
                "Accept": "application/json",
            },
        )

    @staticmethod
    def _nse_date(value: date) -> str:
        return value.strftime("%d-%m-%Y")

    @staticmethod
    def _iso_date(value: object) -> Optional[str]:
        text = str(value or "").strip()
        if not text or text == "-":
            return None
        try:
            return datetime.strptime(text, "%d-%b-%Y").date().isoformat()
        except ValueError as error:
            raise CorporateActionError(
                f"NSE corporate action returned an invalid date: {text}"
            ) from error

    @staticmethod
    def _write_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)

    def sync(self) -> dict:
        current = self._now().astimezone(timezone.utc)
        start = current.date() - timedelta(days=self._settings.lookback_days)
        try:
            response = self._http.get(
                self._settings.url,
                params={
                    "index": "equities",
                    "from_date": self._nse_date(start),
                    "to_date": self._nse_date(current.date()),
                },
            )
            response.raise_for_status()
            raw = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise CorporateActionError(
                "Official NSE corporate-actions refresh failed"
            ) from error
        if not isinstance(raw, list):
            raise CorporateActionError("Official NSE corporate-actions response is invalid")
        actions = []
        for item in raw:
            if not isinstance(item, dict):
                raise CorporateActionError("Official NSE corporate action row is invalid")
            symbol = str(item.get("symbol", "")).strip().upper()
            subject = str(item.get("subject", "")).strip()
            series = str(item.get("series", "")).strip().upper()
            if not symbol or not subject:
                raise CorporateActionError("Official NSE corporate action has a blank field")
            actions.append(
                {
                    "symbol": symbol,
                    "series": series,
                    "subject": subject,
                    "ex_date": self._iso_date(item.get("exDate")),
                    "record_date": self._iso_date(item.get("recDate")),
                }
            )
        payload = {
            "version": self.CACHE_VERSION,
            "source": self._settings.url,
            "fetched_at": current.isoformat(),
            "from_date": start.isoformat(),
            "to_date": current.date().isoformat(),
            "actions": actions,
        }
        self._write_atomic(self._settings.cache_path, payload)
        return payload
