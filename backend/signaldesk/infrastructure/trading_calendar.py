from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Set


class TradingCalendarError(RuntimeError):
    pass


class JsonTradingCalendar:
    def __init__(self, path: Path) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TradingCalendarError("NSE trading calendar is unreadable") from error
        self._name = str(payload.get("name", "")).strip()
        weekdays = payload.get("regular_weekdays")
        if not self._name or not isinstance(weekdays, list) or not weekdays:
            raise TradingCalendarError("NSE trading calendar metadata is incomplete")
        self._regular_weekdays = {int(item) for item in weekdays}
        if any(item < 0 or item > 6 for item in self._regular_weekdays):
            raise TradingCalendarError("NSE trading calendar has an invalid weekday")
        self._holidays = self._dates(payload.get("holidays"), "holidays")
        self._special_sessions = self._dates(
            payload.get("special_sessions"), "special sessions"
        )
        overlap = self._holidays & self._special_sessions
        if overlap:
            raise TradingCalendarError(
                "NSE calendar marks dates as both holiday and special session"
            )

    @staticmethod
    def _dates(items: object, label: str) -> Set[date]:
        if not isinstance(items, list):
            raise TradingCalendarError(f"NSE trading calendar {label} are invalid")
        try:
            return {date.fromisoformat(str(item["date"])) for item in items}
        except (KeyError, TypeError, ValueError) as error:
            raise TradingCalendarError(
                f"NSE trading calendar {label} contain an invalid date"
            ) from error

    def name(self) -> str:
        return self._name

    def is_session(self, day: date) -> bool:
        if day in self._special_sessions:
            return True
        return day.weekday() in self._regular_weekdays and day not in self._holidays
