from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from signaldesk.config import AppSettings
from signaldesk.domain.models import (
    ExitReplayObservation,
    ExitReplayResult,
    PaperExitFill,
    PaperPosition,
)
from signaldesk.domain.ports import (
    ExitReplayProvider,
    PaperOrderRepository,
)


class PositionExitError(ValueError):
    pass


ExitReason = Literal["TP1", "TP2", "INITIAL_STOP", "TRAILING_STOP"]


class PositionExitService:
    def __init__(
        self,
        settings: AppSettings,
        replay: ExitReplayProvider,
        repository: PaperOrderRepository,
    ) -> None:
        self._settings = settings
        self._replay = replay
        self._repository = repository

    def _position(self, position_id: str) -> PaperPosition:
        position = self._repository.find_position(position_id)
        if position is None:
            raise PositionExitError("Paper position does not exist")
        if position.status != "OPEN" or position.quantity_open < 1:
            raise PositionExitError("Paper position is already closed")
        return position

    def _fee(self, price: float, quantity: int) -> float:
        return round(
            price
            * quantity
            * self._settings.paper_execution.fee_bps
            / 10_000,
            2,
        )

    def _target_price(self, observed: float, target: float) -> float:
        slipped = observed * (
            1 - self._settings.paper_execution.slippage_bps / 10_000
        )
        return round(max(target, slipped), 2)

    def _stop_price(self, observed: float, stop: float) -> float:
        base = min(observed, stop)
        return round(
            base * (1 - self._settings.paper_execution.slippage_bps / 10_000),
            2,
        )

    def _complete(
        self,
        position: PaperPosition,
        observation: ExitReplayObservation,
        reason: ExitReason,
        quantity: int,
        fill_price: float,
        replay_complete: bool,
    ) -> ExitReplayResult:
        fee = self._fee(fill_price, quantity)
        remaining = position.quantity_open - quantity
        tp1_filled = position.tp1_filled_quantity + (
            quantity if reason == "TP1" else 0
        )
        trailing_active = position.trailing_active or (
            position.tp1_quantity > 0 and tp1_filled >= position.tp1_quantity
        )
        new_stop = position.current_stop
        if trailing_active and observation.trailing_candidate is not None:
            new_stop = max(new_stop, observation.trailing_candidate)
        updated = position.model_copy(
            update={
                "status": "CLOSED" if remaining == 0 else "OPEN",
                "quantity_open": remaining,
                "quantity_closed": position.quantity_closed + quantity,
                "tp1_filled_quantity": tp1_filled,
                "trailing_active": trailing_active,
                "highest_price": max(position.highest_price, observation.price),
                "current_stop": new_stop,
                "exit_fees": round(position.exit_fees + fee, 2),
                "realized_pnl": round(
                    position.realized_pnl
                    + (fill_price - position.average_entry_price) * quantity
                    - fee,
                    2,
                ),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        fill = PaperExitFill(
            id=str(uuid4()),
            position_id=position.id,
            symbol=position.symbol,
            reason=reason,
            quantity=quantity,
            observed_price=observation.price,
            fill_price=fill_price,
            fee=fee,
            filled_at=observation.observed_at,
        )
        self._repository.apply_exit_replay(observation, updated, fill)
        outcome = {
            "TP1": "TP1_FILL",
            "TP2": "TP2_FILL",
            "INITIAL_STOP": "INITIAL_STOP_FILL",
            "TRAILING_STOP": "TRAILING_STOP_FILL",
        }[reason]
        message = {
            "TP1": "TP1 exit filled; trailing protection is now active",
            "TP2": "TP2 exit filled",
            "INITIAL_STOP": "Initial protective stop exit filled",
            "TRAILING_STOP": "Trailing protective stop exit filled",
        }[reason]
        return ExitReplayResult(
            observation=observation,
            outcome=outcome,
            message=message,
            position=updated,
            fill=fill,
            previous_stop=position.current_stop,
            replay_complete=replay_complete,
        )

    def advance(self, position_id: str) -> ExitReplayResult:
        position = self._position(position_id)
        sequence = self._repository.exit_observation_count(position.symbol)
        observation = self._replay.observation(position.symbol, sequence)
        if observation is None:
            raise PositionExitError("No more exit replay observations are available")
        replay_complete = sequence + 1 >= self._replay.count(position.symbol)

        if observation.price <= position.current_stop:
            reason: ExitReason = (
                "TRAILING_STOP" if position.trailing_active else "INITIAL_STOP"
            )
            return self._complete(
                position,
                observation,
                reason,
                min(position.quantity_open, observation.available_quantity),
                self._stop_price(observation.price, position.current_stop),
                replay_complete,
            )

        if position.tp1_quantity == 0 and not position.trailing_active:
            if observation.price >= position.target_one:
                new_stop = max(
                    position.current_stop,
                    observation.trailing_candidate or position.current_stop,
                )
                updated = position.model_copy(
                    update={
                        "trailing_active": True,
                        "current_stop": new_stop,
                        "highest_price": max(
                            position.highest_price, observation.price
                        ),
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                self._repository.apply_exit_replay(observation, updated)
                return ExitReplayResult(
                    observation=observation,
                    outcome="TRAILING_UPDATED",
                    message="TP1 milestone reached; trailing activated for the single share",
                    position=updated,
                    previous_stop=position.current_stop,
                    replay_complete=replay_complete,
                )

        if (
            position.tp1_quantity > position.tp1_filled_quantity
            and observation.price >= position.target_one
        ):
            quantity = min(
                position.tp1_quantity - position.tp1_filled_quantity,
                position.quantity_open,
                observation.available_quantity,
            )
            return self._complete(
                position,
                observation,
                "TP1",
                quantity,
                self._target_price(observation.price, position.target_one),
                replay_complete,
            )

        if observation.price >= position.target_two:
            return self._complete(
                position,
                observation,
                "TP2",
                min(position.quantity_open, observation.available_quantity),
                self._target_price(observation.price, position.target_two),
                replay_complete,
            )

        if (
            position.trailing_active
            and observation.trailing_candidate is not None
            and observation.trailing_candidate > position.current_stop
        ):
            updated = position.model_copy(
                update={
                    "current_stop": observation.trailing_candidate,
                    "highest_price": max(position.highest_price, observation.price),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._repository.apply_exit_replay(observation, updated)
            return ExitReplayResult(
                observation=observation,
                outcome="TRAILING_UPDATED",
                message="Trailing stop tightened from {:.2f} to {:.2f}".format(
                    position.current_stop, updated.current_stop
                ),
                position=updated,
                previous_stop=position.current_stop,
                replay_complete=replay_complete,
            )

        updated = position.model_copy(
            update={
                "highest_price": max(position.highest_price, observation.price),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._repository.apply_exit_replay(observation, updated)
        return ExitReplayResult(
            observation=observation,
            outcome="HOLD",
            message="No exit level was reached; position remains open",
            position=updated,
            previous_stop=position.current_stop,
            replay_complete=replay_complete,
        )
