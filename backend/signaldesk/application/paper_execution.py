from datetime import datetime, timezone
from uuid import uuid4

from signaldesk.config import AppSettings
from signaldesk.domain.models import PaperFill, PaperOrder, PaperPosition, ReplayResult
from signaldesk.domain.ports import PaperOrderRepository, ReplayProvider


class PaperExecutionError(ValueError):
    pass


class PaperExecutionService:
    def __init__(
        self,
        settings: AppSettings,
        replay: ReplayProvider,
        repository: PaperOrderRepository,
    ) -> None:
        self._settings = settings
        self._replay = replay
        self._repository = repository

    def _active_order(self, order_id: str) -> PaperOrder:
        order = self._repository.find_by_id(order_id)
        if order is None:
            raise PaperExecutionError("Paper order does not exist")
        if order.status not in {"PENDING_SIMULATION", "PARTIALLY_FILLED"}:
            raise PaperExecutionError("Paper order is no longer active")
        return order

    def advance(self, order_id: str) -> ReplayResult:
        order = self._active_order(order_id)
        sequence = self._repository.observation_count(order.symbol)
        observation = self._replay.observation(order.symbol, sequence)
        if observation is None:
            raise PaperExecutionError("No more replay observations are available")
        replay_complete = sequence + 1 >= self._replay.count(order.symbol)
        if observation.price < order.entry_price:
            self._repository.apply_replay(observation)
            return ReplayResult(
                observation=observation,
                outcome="WAITING_FOR_ENTRY",
                message="Entry was not crossed; order remains pending",
                order=order,
                replay_complete=replay_complete,
            )

        remaining = order.quantity - order.filled_quantity
        fill_quantity = min(remaining, observation.available_quantity)
        base_price = max(order.entry_price, observation.price)
        fill_price = round(
            base_price * (1 + self._settings.paper_execution.slippage_bps / 10_000),
            2,
        )
        fee = round(
            fill_price
            * fill_quantity
            * self._settings.paper_execution.fee_bps
            / 10_000,
            2,
        )
        previous_value = (order.average_fill_price or 0) * order.filled_quantity
        new_filled = order.filled_quantity + fill_quantity
        average = round((previous_value + fill_price * fill_quantity) / new_filled, 2)
        updated = order.model_copy(
            update={
                "status": "FILLED" if new_filled == order.quantity else "PARTIALLY_FILLED",
                "filled_quantity": new_filled,
                "average_fill_price": average,
                "fees": round(order.fees + fee, 2),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        fill = PaperFill(
            id=str(uuid4()),
            order_id=order.id,
            symbol=order.symbol,
            quantity=fill_quantity,
            observed_price=observation.price,
            fill_price=fill_price,
            fee=fee,
            filled_at=observation.observed_at,
        )
        position_id = "position-{}".format(order.id)
        existing_position = self._repository.find_position(position_id)
        position = PaperPosition(
            id=position_id,
            order_id=order.id,
            symbol=order.symbol,
            status="OPEN",
            quantity_open=new_filled,
            quantity_closed=0,
            average_entry_price=average,
            current_stop=order.stop_price,
            target_one=order.target_one,
            target_two=order.target_two,
            tp1_quantity=(
                0
                if order.quantity == 1
                else max(
                    1,
                    int(
                        order.quantity
                        * self._settings.paper_execution.tp1_fraction
                    ),
                )
            ),
            tp1_filled_quantity=0,
            trailing_active=False,
            highest_price=max(
                average,
                existing_position.highest_price if existing_position else average,
            ),
            entry_fees=updated.fees,
            exit_fees=0,
            realized_pnl=-updated.fees,
            updated_at=datetime.now(timezone.utc),
        )
        self._repository.apply_replay(observation, updated, fill, position)
        outcome = "FILLED" if updated.status == "FILLED" else "PARTIAL_FILL"
        return ReplayResult(
            observation=observation,
            outcome=outcome,
            message=(
                "Entry fully filled"
                if outcome == "FILLED"
                else "Entry partially filled; remaining quantity stays pending"
            ),
            order=updated,
            fill=fill,
            replay_complete=replay_complete,
        )

    def cancel(self, order_id: str) -> PaperOrder:
        order = self._active_order(order_id)
        cancelled = order.model_copy(
            update={"status": "CANCELLED", "updated_at": datetime.now(timezone.utc)}
        )
        return self._repository.update(cancelled)
