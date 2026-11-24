from datetime import datetime, timezone
from typing import Optional

from signaldesk.config import AppSettings
from signaldesk.domain.models import (
    DailyBriefPayload,
    PortfolioAnalysisPayload,
    PortfolioPositionAnalysis,
    ScanRun,
)
from signaldesk.domain.ports import PaperOrderRepository, ResearchProvider, ScanRepository

from .scans import ScanService


class DailyBriefService:
    def __init__(
        self,
        settings: AppSettings,
        research: ResearchProvider,
        orders: PaperOrderRepository,
        scans: ScanService,
        scan_repository: ScanRepository,
    ) -> None:
        self._settings = settings
        self._research = research
        self._orders = orders
        self._scans = scans
        self._scan_repository = scan_repository

    def portfolio(self) -> PortfolioAnalysisPayload:
        snapshot = self._research.dashboard()
        prices = {item.symbol: item.price for item in snapshot.candidates}
        positions = self._orders.list_positions()
        analyses = []
        stale = []
        cost_basis = 0.0
        market_value = 0.0
        unrealized = 0.0
        realized = sum(item.realized_pnl for item in positions)
        reserved_risk = 0.0
        at_risk = False
        open_values = []
        for position in positions:
            current = prices.get(position.symbol)
            quantity = position.quantity_open
            basis = position.average_entry_price * quantity
            value = (current if current is not None else position.average_entry_price) * quantity
            position_unrealized = (
                (current - position.average_entry_price) * quantity
                if current is not None
                else None
            )
            distance = (
                (current - position.current_stop) / current * 100
                if current is not None and quantity > 0
                else None
            )
            if position.status == "OPEN":
                cost_basis += basis
                market_value += value
                open_values.append(value)
                reserved_risk += max(
                    position.average_entry_price - position.current_stop, 0
                ) * quantity
                if position_unrealized is not None:
                    unrealized += position_unrealized
                else:
                    stale.append(position.symbol)
                at_risk = at_risk or (current is not None and current <= position.current_stop)
            analyses.append(
                PortfolioPositionAnalysis(
                    symbol=position.symbol,
                    status=position.status,
                    quantity=quantity,
                    averageEntry=position.average_entry_price,
                    currentPrice=current,
                    currentStop=position.current_stop,
                    targetOne=position.target_one,
                    targetTwo=position.target_two,
                    marketValue=value,
                    unrealizedPnl=position_unrealized,
                    realizedPnl=position.realized_pnl,
                    distanceToStopPercent=distance,
                    nextTarget=(
                        position.target_two
                        if position.trailing_active
                        else position.target_one
                    )
                    if position.status == "OPEN"
                    else None,
                )
            )
        open_count = sum(item.status == "OPEN" for item in positions)
        concentration = max(open_values, default=0) / market_value * 100 if market_value else 0
        health = (
            "NO_POSITIONS"
            if open_count == 0
            else "AT_RISK"
            if at_risk
            else "ATTENTION"
            if stale
            else "HEALTHY"
        )
        observations = []
        if open_count == 0:
            observations.append("No open paper positions; capital is not exposed.")
        if at_risk:
            observations.append("At least one position is at or below its protective stop.")
        if stale:
            observations.append(
                "Current research prices are unavailable for: " + ", ".join(sorted(stale))
            )
        if open_count > 0 and not at_risk and not stale:
            observations.append("All open positions remain above their current protective stops.")
        observations.append(
            f"Portfolio risk uses the configured ₹{self._settings.risk.maximum_aggregate_initial_risk:,.0f} aggregate ceiling."
        )
        return PortfolioAnalysisPayload(
            as_of=snapshot.as_of,
            health=health,
            openPositions=open_count,
            costBasis=cost_basis,
            marketValue=market_value,
            unrealizedPnl=unrealized,
            realizedPnl=realized,
            reservedRisk=reserved_risk,
            largestPositionPercent=concentration,
            staleSymbols=sorted(stale),
            observations=observations,
            positions=analyses,
        )

    def _latest_scan(self) -> Optional[ScanRun]:
        runs = self._scan_repository.list_recent(
            self._settings.scanning.history_retention_days
        )
        return runs[0] if runs else None

    def brief(self, scan: Optional[ScanRun] = None) -> DailyBriefPayload:
        latest = scan or self._latest_scan()
        setups = latest.candidates if latest else []
        return DailyBriefPayload(
            generatedAt=datetime.now(timezone.utc),
            scan=latest,
            topSetups=setups,
            portfolio=self.portfolio(),
            message=(
                f"{len(setups)} actionable setup{'s' if len(setups) != 1 else ''} in the latest complete scan."
                if latest
                else "No completed daily scan has been archived yet."
            ),
        )

    def run(self) -> DailyBriefPayload:
        return self.brief(self._scans.archive_current())
