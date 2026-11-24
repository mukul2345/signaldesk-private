from collections import defaultdict
from datetime import datetime, timedelta, timezone

from signaldesk.config import AppSettings
from signaldesk.domain.models import MonthlyPerformance, PerformanceValidationPayload
from signaldesk.domain.ports import PaperOrderRepository


class PerformanceValidationService:
    def __init__(self, settings: AppSettings, repository: PaperOrderRepository) -> None:
        self._settings = settings
        self._repository = repository

    def report(self) -> PerformanceValidationPayload:
        closed = sorted(
            (item for item in self._repository.list_positions() if item.status == "CLOSED"),
            key=lambda item: item.updated_at,
        )
        pnl = [item.realized_pnl for item in closed]
        wins = sum(value > 0 for value in pnl)
        losses = sum(value < 0 for value in pnl)
        net = sum(pnl)
        equity = float(self._settings.capital_ceiling)
        peak = equity
        maximum_drawdown = 0.0
        for value in pnl:
            equity += value
            peak = max(peak, equity)
            maximum_drawdown = max(maximum_drawdown, peak - equity)
        drawdown_percent = maximum_drawdown / peak * 100 if peak else 0
        by_month = defaultdict(lambda: {"count": 0, "pnl": 0.0})
        for position in closed:
            key = position.updated_at.astimezone(timezone.utc).strftime("%Y-%m")
            by_month[key]["count"] += 1
            by_month[key]["pnl"] += position.realized_pnl
        months = [
            MonthlyPerformance(
                month=month,
                closedTrades=values["count"],
                netPnl=values["pnl"],
                returnPercent=values["pnl"] / self._settings.capital_ceiling * 100,
            )
            for month, values in sorted(by_month.items())
        ]
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        last_30_pnl = sum(
            item.realized_pnl
            for item in closed
            if item.updated_at.astimezone(timezone.utc) >= cutoff
        )
        last_30_return = last_30_pnl / self._settings.capital_ceiling * 100
        evidence_ready = len(closed) >= self._settings.evaluation.minimum_closed_trades
        risk_pass = (
            drawdown_percent
            <= self._settings.evaluation.maximum_acceptable_drawdown_percent
        )
        status = (
            "INSUFFICIENT_EVIDENCE"
            if not evidence_ready
            else "FAILED_RISK_GATE"
            if not risk_pass
            else "EVIDENCE_READY"
        )
        target = self._settings.evaluation.target_monthly_return_percent
        warnings = [
            "Past paper results do not guarantee future returns.",
            "A monthly target is an evaluation threshold, not a forecast or promise.",
            "Replay-generated trades must be separated from live-market forward observations before acceptance.",
        ]
        if not evidence_ready:
            warnings.insert(
                0,
                f"{self._settings.evaluation.minimum_closed_trades - len(closed)} more closed paper trades are required.",
            )
        return PerformanceValidationPayload(
            status=status,
            closedTrades=len(closed),
            minimumRequiredTrades=self._settings.evaluation.minimum_closed_trades,
            winningTrades=wins,
            losingTrades=losses,
            winRatePercent=wins / len(closed) * 100 if closed else 0,
            netPnl=net,
            averagePnlPerTrade=net / len(closed) if closed else 0,
            maximumDrawdown=maximum_drawdown,
            maximumDrawdownPercent=drawdown_percent,
            last30DayReturnPercent=last_30_return,
            targetMonthlyReturnPercent=target,
            targetObserved=any(item.return_percent >= target for item in months),
            months=months,
            warnings=warnings,
        )
