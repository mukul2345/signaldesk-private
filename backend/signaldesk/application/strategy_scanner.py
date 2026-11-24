import json
from datetime import datetime, time
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from signaldesk.config import AppSettings
from signaldesk.domain.models import Candidate, DashboardPayload
from signaldesk.domain.ports import DailyBarProvider
from signaldesk.domain.strategy import DailyBreakoutStrategy, StrategyParameters


def build_strategy(settings: AppSettings) -> DailyBreakoutStrategy:
    p = settings.strategy
    return DailyBreakoutStrategy(
        StrategyParameters(
            version=p.version,
            warmup_bars=p.warmup_bars,
            fast_sma_period=p.fast_sma_period,
            slow_sma_period=p.slow_sma_period,
            breakout_lookback=p.breakout_lookback,
            volume_average_period=p.volume_average_period,
            minimum_volume_ratio=p.minimum_volume_ratio,
            atr_period=p.atr_period,
            initial_stop_atr_multiple=p.initial_stop_atr_multiple,
            entry_buffer_bps=p.entry_buffer_bps,
            maximum_entry_extension_bps=p.maximum_entry_extension_bps,
            target_one_r=p.target_one_r,
            target_two_r=p.target_two_r,
            maximum_holding_sessions=p.maximum_holding_sessions,
            tick_size=p.tick_size,
            watch_score_minimum=p.watch_score_minimum,
            ready_score_minimum=p.ready_score_minimum,
            trend_weight=p.score_weights.trend,
            breakout_weight=p.score_weights.breakout,
            volume_weight=p.score_weights.volume,
            market_weight=p.score_weights.market,
        )
    )


class StrategyResearchProvider:
    def __init__(
        self,
        settings: AppSettings,
        context_path: Path,
        bars: DailyBarProvider,
    ) -> None:
        self._settings = settings
        self._context_path = context_path
        self._bars = bars
        self._strategy = build_strategy(settings)

    def dashboard(self) -> DashboardPayload:
        payload = json.loads(self._context_path.read_text(encoding="utf-8"))
        candidates = []
        excluded = 0
        latest_session = None
        instruments = self._bars.instruments()
        market_supportive = self._bars.market_supportive()
        for instrument in instruments:
            result = self._strategy.evaluate(instrument.bars, market_supportive)
            if result.as_of is not None:
                latest_session = (
                    max(latest_session, result.as_of)
                    if latest_session is not None
                    else result.as_of
                )
            if result.state == "INSUFFICIENT" or not all(
                (result.entry, result.stop, result.target_one, result.target_two)
            ):
                excluded += 1
                continue
            current = instrument.bars[-1]
            previous = instrument.bars[-2]
            candidates.append(
                Candidate(
                    id=instrument.symbol.lower(),
                    rank=1,
                    symbol=instrument.symbol,
                    company=instrument.company,
                    sector=instrument.sector,
                    price=current.close,
                    changePercent=(current.close / previous.close - 1) * 100,
                    score=result.score,
                    state=result.state,
                    setup="Daily range breakout",
                    volumeRatio=result.volume_ratio or 0,
                    entry=result.entry,
                    stop=result.stop,
                    targetOne=result.target_one,
                    targetTwo=result.target_two,
                    probability=None,
                    reasons=result.reasons,
                    contradictions=result.contradictions,
                )
            )
        priority = {"READY": 0, "WATCH": 1, "AVOID": 2}
        candidates.sort(key=lambda item: (priority[item.state], -item.score, item.symbol))
        candidates = [item.model_copy(update={"rank": index + 1}) for index, item in enumerate(candidates)]
        if latest_session is None:
            raise ValueError("The daily-bar provider returned no completed sessions")
        timezone = ZoneInfo(self._settings.scanning.timezone)
        as_of = datetime.combine(
            latest_session,
            time.fromisoformat(self._bars.cutoff_time()),
            tzinfo=timezone,
        )
        indices = self._bars.indices()
        payload.update(
            {
                "as_of": as_of.isoformat(),
                "source": self._bars.source(),
                "next_scan": "Weekdays · {} IST".format(
                    ", ".join(self._settings.scanning.schedule_slots)
                ),
                **(
                    {"indices": [item.model_dump(mode="json", by_alias=True) for item in indices]}
                    if indices
                    else {}
                ),
                "candidates": [item.model_dump(mode="json", by_alias=True) for item in candidates],
                "scanCoverage": {
                    "eligibleCount": len(candidates) + excluded,
                    "evaluatedCount": len(candidates),
                    "excludedCount": excluded,
                    "missingSymbols": [],
                },
            }
        )
        return DashboardPayload.model_validate(payload)

    def candidate(self, candidate_id: str) -> Optional[Candidate]:
        return next(
            (item for item in self.dashboard().candidates if item.id == candidate_id),
            None,
        )
