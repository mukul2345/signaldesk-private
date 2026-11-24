import math
from datetime import datetime, timezone
from uuid import uuid4

from signaldesk.config import AppSettings
from signaldesk.domain.models import PaperOrder, PaperOrderRequest
from signaldesk.domain.ports import PaperOrderRepository, ResearchProvider


class PaperOrderError(ValueError):
    pass


class PaperOrderService:
    def __init__(
        self,
        settings: AppSettings,
        research: ResearchProvider,
        repository: PaperOrderRepository,
    ) -> None:
        self._settings = settings
        self._research = research
        self._repository = repository

    def create(self, request: PaperOrderRequest) -> PaperOrder:
        existing = self._repository.find_by_idempotency_key(request.idempotency_key)
        if existing:
            return existing
        if not self._settings.execution.paper_enabled:
            raise PaperOrderError("Paper execution is disabled")
        candidate = self._research.candidate(request.candidate_id)
        if candidate is None:
            raise PaperOrderError("Candidate does not exist")
        if candidate.state != "READY":
            raise PaperOrderError("Only READY candidates can create paper orders")
        orders = self._repository.list_orders()
        active = [
            order
            for order in orders
            if order.status in {"PENDING_SIMULATION", "PARTIALLY_FILLED"}
        ]
        open_order_ids = {
            position.order_id
            for position in self._repository.list_positions()
            if position.status == "OPEN"
        }
        engaged = [
            order for order in orders if order in active or order.id in open_order_ids
        ]
        if any(order.candidate_id == candidate.id for order in engaged):
            raise PaperOrderError("This candidate already has an active paper trade")
        if len(engaged) >= self._settings.risk.maximum_open_positions:
            raise PaperOrderError("Maximum open paper-order count reached")
        risk_per_share = candidate.entry - candidate.stop
        if risk_per_share <= 0:
            raise PaperOrderError("Candidate has an invalid protective stop")
        by_risk = math.floor(self._settings.risk.risk_per_trade / risk_per_share)
        by_value = math.floor(
            self._settings.risk.maximum_position_value / candidate.entry
        )
        quantity = min(by_risk, by_value)
        if quantity < 1:
            raise PaperOrderError("Configured risk budget cannot fund one share")
        planned_risk = round(risk_per_share * quantity, 2)
        required_cash = round(candidate.entry * quantity, 2)
        used_cash = sum(
            (item.average_fill_price or 0) * item.filled_quantity
            + item.fees
            + (
                item.entry_price * (item.quantity - item.filled_quantity)
                if item in active
                else 0
            )
            for item in orders
        )
        used_risk = sum(
            (item.entry_price - item.stop_price)
            * (item.quantity if item.status != "CANCELLED" else item.filled_quantity)
            for item in orders
        )
        if required_cash + used_cash > self._settings.capital_ceiling:
            raise PaperOrderError("Insufficient unreserved paper capital")
        if planned_risk + used_risk > self._settings.risk.maximum_aggregate_initial_risk:
            raise PaperOrderError("Aggregate paper risk limit would be exceeded")
        order = PaperOrder(
            id=str(uuid4()),
            candidate_id=candidate.id,
            symbol=candidate.symbol,
            status="PENDING_SIMULATION",
            quantity=quantity,
            entry_price=candidate.entry,
            stop_price=candidate.stop,
            target_one=candidate.target_one,
            target_two=candidate.target_two,
            planned_risk=planned_risk,
            required_cash=required_cash,
            idempotency_key=request.idempotency_key,
            created_at=datetime.now(timezone.utc),
        )
        return self._repository.save(order)
