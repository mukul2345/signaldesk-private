import json
from datetime import date, timedelta
from pathlib import Path
from typing import List

from signaldesk.domain.models import DailyBar, InstrumentBars, MarketIndex, ProviderReadiness


class ScenarioDailyBarProvider:
    def __init__(self, source_path: Path) -> None:
        self._payload = json.loads(source_path.read_text(encoding="utf-8"))

    def source(self) -> str:
        return str(self._payload["source"])

    def market_supportive(self) -> bool:
        return bool(self._payload["market_supportive"])

    def cutoff_time(self) -> str:
        return str(self._payload["cutoff_time"])

    def readiness(self) -> ProviderReadiness:
        return ProviderReadiness(
            status="DEMO",
            detail="Deterministic completed-bar fixture; no external market feed",
        )

    def indices(self) -> List[MarketIndex]:
        return []

    @staticmethod
    def _sessions(start: date, count: int) -> List[date]:
        sessions = []
        current = start
        while len(sessions) < count:
            if current.weekday() < 5:
                sessions.append(current)
            current += timedelta(days=1)
        return sessions

    def instruments(self) -> List[InstrumentBars]:
        start = date.fromisoformat(self._payload["start_date"])
        count = int(self._payload["sessions"])
        sessions = self._sessions(start, count)
        results = []
        for item in self._payload["instruments"]:
            bars = []
            for index, session in enumerate(sessions):
                close = float(item["base_close"]) + index * float(item["daily_change"])
                spread = float(item["bar_range"])
                bars.append(
                    DailyBar(
                        session=session,
                        open=close - spread / 4,
                        high=close + spread,
                        low=close - spread,
                        close=close,
                        volume=float(item["base_volume"]),
                    )
                )
            bars[-1] = DailyBar(session=sessions[-1], **item["final"])
            results.append(
                InstrumentBars(
                    symbol=item["symbol"],
                    company=item["company"],
                    sector=item["sector"],
                    bars=bars,
                )
            )
        return results
