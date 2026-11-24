from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from signaldesk.config import CorporateActionSettings
from signaldesk.domain.models import DailyBar


class CorporateActionAdjustmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppliedCorporateAction:
    symbol: str
    subject: str
    ex_date: date
    factor: float


@dataclass(frozen=True)
class CorporateActionAdjustmentResult:
    bars: list[DailyBar]
    applied: list[AppliedCorporateAction]
    unresolved_subjects: list[str]


class CorporateActionAdjuster:
    """Creates an adjusted view while preserving the raw NSE cache."""

    def __init__(self, settings: CorporateActionSettings) -> None:
        self._settings = settings
        self._bonus = re.compile(settings.bonus_ratio_pattern, re.IGNORECASE)
        self._face_value = re.compile(
            settings.face_value_ratio_pattern, re.IGNORECASE
        )

    @staticmethod
    def _read(path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CorporateActionAdjustmentError(
                "Corporate-action evidence is unreadable"
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("actions"), list):
            raise CorporateActionAdjustmentError(
                "Corporate-action evidence is invalid"
            )
        return payload

    def _factor(self, subject: str) -> Optional[float]:
        bonus = self._bonus.search(subject)
        if bonus:
            issued, held = (float(value) for value in bonus.groups())
            if issued <= 0 or held <= 0:
                return None
            return held / (held + issued)
        face_value = self._face_value.search(subject)
        if face_value:
            old_value, new_value = (float(value) for value in face_value.groups())
            if old_value <= 0 or new_value <= 0:
                return None
            return new_value / old_value
        return None

    def actions(self) -> list[dict]:
        payload = self._read(self._settings.cache_path)
        return [] if payload is None else list(payload["actions"])

    def adjust(
        self,
        symbol: str,
        bars: Iterable[DailyBar],
        actions: Optional[list[dict]] = None,
    ) -> CorporateActionAdjustmentResult:
        adjusted = sorted(list(bars), key=lambda item: item.session)
        if not adjusted:
            return CorporateActionAdjustmentResult([], [], [])
        first_session = adjusted[0].session
        last_session = adjusted[-1].session
        relevant_keywords = [item.upper() for item in self._settings.blocking_keywords]
        applied: list[AppliedCorporateAction] = []
        unresolved: list[str] = []
        source = self.actions() if actions is None else actions
        for action in source:
            if str(action.get("symbol", "")).upper() != symbol.upper():
                continue
            if str(action.get("series", "")).upper() != "EQ":
                continue
            subject = str(action.get("subject", "")).strip()
            if not any(keyword in subject.upper() for keyword in relevant_keywords):
                continue
            try:
                ex_date = date.fromisoformat(str(action.get("ex_date")))
            except (TypeError, ValueError):
                unresolved.append(subject)
                continue
            if ex_date <= first_session:
                continue
            if ex_date > last_session:
                unresolved.append(subject)
                continue
            factor = self._factor(subject)
            if factor is None:
                unresolved.append(subject)
                continue
            adjusted = [
                DailyBar(
                    session=bar.session,
                    open=round(bar.open * factor, self._settings.adjustment_price_decimals),
                    high=round(bar.high * factor, self._settings.adjustment_price_decimals),
                    low=round(bar.low * factor, self._settings.adjustment_price_decimals),
                    close=round(bar.close * factor, self._settings.adjustment_price_decimals),
                    volume=round(bar.volume / factor, self._settings.adjustment_volume_decimals),
                )
                if bar.session < ex_date
                else bar
                for bar in adjusted
            ]
            applied.append(
                AppliedCorporateAction(symbol.upper(), subject, ex_date, factor)
            )
        return CorporateActionAdjustmentResult(
            bars=adjusted,
            applied=applied,
            unresolved_subjects=sorted(set(unresolved)),
        )
