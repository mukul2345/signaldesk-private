from signaldesk.config import AppSettings
from signaldesk.domain.models import (
    AccountSummary,
    DashboardPayload,
    DashboardPolicy,
    PaperAccountPayload,
)
from signaldesk.domain.ports import PaperOrderRepository, ResearchProvider


class DashboardService:
    def __init__(
        self,
        settings: AppSettings,
        research: ResearchProvider,
        repository: PaperOrderRepository,
    ) -> None:
        self._settings = settings
        self._research = research
        self._repository = repository

    def view(self) -> DashboardPayload:
        snapshot = self._research.dashboard()
        orders = self._repository.list_orders()
        positions = self._repository.list_positions()
        active = [
            order
            for order in orders
            if order.status in {"PENDING_SIMULATION", "PARTIALLY_FILLED"}
        ]
        open_order_ids = {
            position.order_id for position in positions if position.status == "OPEN"
        }
        engaged = [
            order
            for order in orders
            if order in active or order.id in open_order_ids
        ]
        reserved_cash = sum(
            order.entry_price * (order.quantity - order.filled_quantity)
            for order in active
        )
        deployed = sum(
            position.average_entry_price * position.quantity_open
            for position in positions
        )
        realized_pnl = sum(position.realized_pnl for position in positions)
        position_risk = sum(
            max(position.average_entry_price - position.current_stop, 0)
            * position.quantity_open
            for position in positions
        )
        entry_risk = sum(
            (order.entry_price - order.stop_price)
            * (order.quantity - order.filled_quantity)
            for order in active
        )
        reserved_risk = position_risk + entry_risk
        return snapshot.model_copy(
            update={
                "account": AccountSummary(
                    availableCash=max(
                        self._settings.capital_ceiling
                        + realized_pnl
                        - reserved_cash
                        - deployed,
                        0,
                    ),
                    deployed=deployed,
                    openRisk=reserved_risk,
                    todayPnl=snapshot.account.today_pnl,
                ),
                "policy": DashboardPolicy(
                    capitalCeiling=self._settings.capital_ceiling,
                    riskPerTrade=self._settings.risk.risk_per_trade,
                    displayLimit=self._settings.universe.display_limit,
                ),
                "pending_orders": engaged,
            }
        )

    def paper_account(self) -> PaperAccountPayload:
        dashboard = self.view()
        orders = self._repository.list_orders()
        reserved_cash = sum(
            order.entry_price * (order.quantity - order.filled_quantity)
            for order in orders
            if order.status in {"PENDING_SIMULATION", "PARTIALLY_FILLED"}
        )
        return PaperAccountPayload(
            orders=orders,
            fills=self._repository.list_fills(),
            positions=self._repository.list_positions(),
            exitFills=self._repository.list_exit_fills(),
            availableCash=dashboard.account.available_cash,
            reservedCash=reserved_cash,
            deployedValue=dashboard.account.deployed,
            reservedRisk=dashboard.account.open_risk,
        )
