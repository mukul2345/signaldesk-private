from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Sequence

from .indicators import (
    average_true_range,
    prior_average_volume,
    prior_highest_high,
    simple_moving_average,
)
from .models import DailyBar, StrategyEvaluation


@dataclass(frozen=True)
class StrategyParameters:
    version: str
    warmup_bars: int
    fast_sma_period: int
    slow_sma_period: int
    breakout_lookback: int
    volume_average_period: int
    minimum_volume_ratio: float
    atr_period: int
    initial_stop_atr_multiple: float
    entry_buffer_bps: int
    maximum_entry_extension_bps: int
    target_one_r: float
    target_two_r: float
    maximum_holding_sessions: int
    tick_size: float
    watch_score_minimum: int
    ready_score_minimum: int
    trend_weight: int
    breakout_weight: int
    volume_weight: int
    market_weight: int


def _to_tick(value: float, tick: float, rounding: str) -> float:
    amount = Decimal(str(value))
    step = Decimal(str(tick))
    return float((amount / step).quantize(Decimal("1"), rounding=rounding) * step)


class DailyBreakoutStrategy:
    def __init__(self, parameters: StrategyParameters) -> None:
        self._p = parameters

    def evaluate(
        self, bars: Sequence[DailyBar], market_supportive: bool
    ) -> StrategyEvaluation:
        p = self._p
        if len(bars) < p.warmup_bars:
            return StrategyEvaluation(
                strategyVersion=p.version,
                state="INSUFFICIENT",
                asOf=bars[-1].session if bars else None,
                barsUsed=len(bars),
                score=0,
                maximumHoldingSessions=p.maximum_holding_sessions,
                reasons=[],
                contradictions=["Insufficient completed daily-bar history"],
            )
        if any(left.session >= right.session for left, right in zip(bars, bars[1:])):
            raise ValueError("Daily bars must be unique and strictly chronological")

        current = bars[-1]
        closes = [bar.close for bar in bars]
        fast = simple_moving_average(closes, p.fast_sma_period)
        slow = simple_moving_average(closes, p.slow_sma_period)
        breakout_level = prior_highest_high(bars, p.breakout_lookback)
        average_volume = prior_average_volume(bars, p.volume_average_period)
        volume_ratio = current.volume / average_volume if average_volume > 0 else 0
        atr = average_true_range(bars, p.atr_period)
        entry = _to_tick(
            breakout_level * (1 + p.entry_buffer_bps / 10000),
            p.tick_size,
            ROUND_CEILING,
        )
        maximum_entry = entry * (1 + p.maximum_entry_extension_bps / 10000)
        trend_ok = current.close > fast > slow
        breakout_ok = current.high >= entry and current.close >= entry
        volume_ok = volume_ratio >= p.minimum_volume_ratio
        extension_ok = current.open <= maximum_entry and current.close <= maximum_entry
        score = (
            (p.trend_weight if trend_ok else 0)
            + (p.breakout_weight if breakout_ok else 0)
            + (p.volume_weight if volume_ok else 0)
            + (p.market_weight if market_supportive else 0)
        )

        reasons = []
        contradictions = []
        (reasons if trend_ok else contradictions).append(
            "Close is above fast and slow daily trend averages"
            if trend_ok
            else "Daily trend alignment is absent"
        )
        (reasons if breakout_ok else contradictions).append(
            "Completed bar confirmed the prior-range breakout"
            if breakout_ok
            else "Breakout entry trigger has not confirmed"
        )
        (reasons if volume_ok else contradictions).append(
            "Volume expansion confirms participation"
            if volume_ok
            else "Volume confirmation is below policy"
        )
        (reasons if market_supportive else contradictions).append(
            "Market regime supports new long exposure"
            if market_supportive
            else "Market regime blocks new long exposure"
        )
        if not extension_ok:
            contradictions.append("Price gapped or extended beyond the permitted entry band")

        if (
            trend_ok
            and breakout_ok
            and volume_ok
            and market_supportive
            and extension_ok
            and score >= p.ready_score_minimum
        ):
            state = "READY"
        elif (
            trend_ok
            and market_supportive
            and extension_ok
            and score >= p.watch_score_minimum
        ):
            state = "WATCH"
        else:
            state = "AVOID"

        risk_distance = atr * p.initial_stop_atr_multiple
        stop = _to_tick(entry - risk_distance, p.tick_size, ROUND_FLOOR)
        if stop <= 0:
            contradictions.append("ATR stop is non-positive, so the setup is invalid")
            state = "AVOID"
            stop = None
            target_one = None
            target_two = None
        else:
            risk_per_share = entry - stop
            target_one = _to_tick(
                entry + risk_per_share * p.target_one_r, p.tick_size, ROUND_HALF_UP
            )
            target_two = _to_tick(
                entry + risk_per_share * p.target_two_r, p.tick_size, ROUND_HALF_UP
            )
        return StrategyEvaluation(
            strategyVersion=p.version,
            state=state,
            asOf=current.session,
            barsUsed=len(bars),
            score=score,
            fastSma=round(fast, 4),
            slowSma=round(slow, 4),
            breakoutLevel=round(breakout_level, 4),
            volumeRatio=round(volume_ratio, 4),
            atr=round(atr, 4),
            entry=entry,
            stop=stop,
            targetOne=target_one,
            targetTwo=target_two,
            maximumHoldingSessions=p.maximum_holding_sessions,
            reasons=reasons,
            contradictions=contradictions,
        )
