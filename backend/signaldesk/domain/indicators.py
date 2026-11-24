from typing import Sequence

from .models import DailyBar


def simple_moving_average(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("Insufficient values for moving average")
    return sum(values[-period:]) / period


def average_true_range(bars: Sequence[DailyBar], period: int) -> float:
    if len(bars) < period + 1:
        raise ValueError("Insufficient bars for ATR")
    ranges = []
    for index in range(len(bars) - period, len(bars)):
        bar = bars[index]
        previous_close = bars[index - 1].close
        ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return sum(ranges) / period


def prior_highest_high(bars: Sequence[DailyBar], lookback: int) -> float:
    if len(bars) < lookback + 1:
        raise ValueError("Insufficient bars for breakout level")
    return max(bar.high for bar in bars[-lookback - 1 : -1])


def prior_average_volume(bars: Sequence[DailyBar], period: int) -> float:
    if len(bars) < period + 1:
        raise ValueError("Insufficient bars for volume average")
    return sum(bar.volume for bar in bars[-period - 1 : -1]) / period
