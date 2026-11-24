from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol

import httpx

from signaldesk.config import NseMcpSettings


class NseUniverseError(RuntimeError):
    pass


class UniverseResponse(Protocol):
    text: str

    def raise_for_status(self) -> None: ...


class UniverseHttpClient(Protocol):
    def get(self, url: str) -> UniverseResponse: ...


class NseUniverseSynchronizer:
    SYMBOL_PATTERN = re.compile(r"^[A-Z0-9&.-]+$")
    REQUIRED_COLUMNS = {"Company Name", "Industry", "Symbol", "Series"}

    def __init__(
        self,
        settings: NseMcpSettings,
        http_client: Optional[UniverseHttpClient] = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._settings = settings
        self._http = http_client or httpx.Client(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 SignalDesk-Private/0.1",
                "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.1",
            },
        )
        self._now = now

    def _download(self) -> str:
        try:
            response = self._http.get(self._settings.universe_source_url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise NseUniverseError(
                "Official Nifty 500 constituent download failed"
            ) from error
        if not response.text.strip():
            raise NseUniverseError("Official Nifty 500 constituent file is empty")
        return response.text

    def _parse(self, content: str) -> list[dict]:
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
        columns = set(reader.fieldnames or [])
        missing_columns = self.REQUIRED_COLUMNS - columns
        if missing_columns:
            raise NseUniverseError(
                "Official constituent file omitted columns: "
                + ", ".join(sorted(missing_columns))
            )
        instruments = []
        seen = set()
        for row in reader:
            if str(row.get("Series", "")).strip().upper() != "EQ":
                continue
            symbol = str(row.get("Symbol", "")).strip().upper()
            company = str(row.get("Company Name", "")).strip()
            sector = str(row.get("Industry", "")).strip()
            if not symbol or not company or not sector:
                raise NseUniverseError("Official constituent file contains a blank field")
            if not self.SYMBOL_PATTERN.fullmatch(symbol):
                raise NseUniverseError(f"Official constituent symbol is invalid: {symbol}")
            if symbol in seen:
                raise NseUniverseError(f"Official constituent file duplicates {symbol}")
            seen.add(symbol)
            instruments.append(
                {"symbol": symbol, "company": company, "sector": sector}
            )
        count = len(instruments)
        if not (
            self._settings.universe_expected_minimum
            <= count
            <= self._settings.universe_expected_maximum
        ):
            raise NseUniverseError(
                "Official constituent count "
                f"{count} is outside configured bounds "
                f"{self._settings.universe_expected_minimum}-"
                f"{self._settings.universe_expected_maximum}"
            )
        return sorted(instruments, key=lambda item: item["symbol"])

    @staticmethod
    def _write_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def sync_candidate(self) -> dict:
        instruments = self._parse(self._download())
        synced_at = self._now().astimezone(timezone.utc)
        payload = {
            "version": f"nifty-500-{synced_at.date().isoformat()}",
            "source": self._settings.universe_source_url,
            "synced_at": synced_at.isoformat(),
            "instruments": instruments,
        }
        self._write_atomic(self._settings.universe_candidate_path, payload)
        return payload
