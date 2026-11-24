import sqlite3
from pathlib import Path
from typing import List, Optional

from signaldesk.domain.models import (
    ExitReplayObservation,
    PaperExitFill,
    PaperFill,
    PaperOrder,
    PaperPosition,
    ReplayObservation,
)


class SqlitePaperOrderRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._database_path))
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_orders (
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    entry_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    target_one REAL NOT NULL,
                    target_two REAL NOT NULL,
                    planned_risk REAL NOT NULL,
                    required_cash REAL NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
                """
            )

            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(paper_orders)").fetchall()
            }
            additions = {
                "filled_quantity": "INTEGER NOT NULL DEFAULT 0",
                "average_fill_price": "REAL",
                "fees": "REAL NOT NULL DEFAULT 0",
                "updated_at": "TEXT",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(
                        "ALTER TABLE paper_orders ADD COLUMN {} {}".format(
                            name, definition
                        )
                    )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_fills (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    observed_price REAL NOT NULL,
                    fill_price REAL NOT NULL,
                    fee REAL NOT NULL,
                    filled_at TEXT NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES paper_orders(id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS replay_observations (
                    symbol TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    price REAL NOT NULL,
                    available_quantity INTEGER NOT NULL,
                    PRIMARY KEY(symbol, sequence)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_positions (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quantity_open INTEGER NOT NULL,
                    quantity_closed INTEGER NOT NULL,
                    average_entry_price REAL NOT NULL,
                    current_stop REAL NOT NULL,
                    target_one REAL NOT NULL,
                    target_two REAL NOT NULL,
                    tp1_quantity INTEGER NOT NULL,
                    tp1_filled_quantity INTEGER NOT NULL,
                    trailing_active INTEGER NOT NULL,
                    highest_price REAL NOT NULL,
                    entry_fees REAL NOT NULL,
                    exit_fees REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES paper_orders(id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_exit_fills (
                    id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    observed_price REAL NOT NULL,
                    fill_price REAL NOT NULL,
                    fee REAL NOT NULL,
                    filled_at TEXT NOT NULL,
                    FOREIGN KEY(position_id) REFERENCES paper_positions(id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exit_replay_observations (
                    symbol TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    price REAL NOT NULL,
                    available_quantity INTEGER NOT NULL,
                    trailing_candidate REAL,
                    PRIMARY KEY(symbol, sequence)
                )
                """
            )

    def ping(self) -> bool:
        try:
            with self._connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    def backfill_positions(self, tp1_fraction: float) -> None:
        orders = [order for order in self.list_orders() if order.filled_quantity > 0]
        existing = {position.order_id for position in self.list_positions()}
        for order in orders:
            if order.id in existing:
                continue
            tp1_quantity = (
                0 if order.quantity == 1 else max(1, int(order.quantity * tp1_fraction))
            )
            position = PaperPosition(
                id="position-{}".format(order.id),
                order_id=order.id,
                symbol=order.symbol,
                status="OPEN",
                quantity_open=order.filled_quantity,
                quantity_closed=0,
                average_entry_price=order.average_fill_price or order.entry_price,
                current_stop=order.stop_price,
                target_one=order.target_one,
                target_two=order.target_two,
                tp1_quantity=tp1_quantity,
                tp1_filled_quantity=0,
                trailing_active=False,
                highest_price=order.average_fill_price or order.entry_price,
                entry_fees=order.fees,
                exit_fees=0,
                realized_pnl=-order.fees,
                updated_at=order.updated_at or order.created_at,
            )
            self._upsert_position(position)

    @staticmethod
    def _to_order(row: sqlite3.Row) -> PaperOrder:
        return PaperOrder.model_validate(dict(row))

    def find_by_idempotency_key(self, key: str) -> Optional[PaperOrder]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_orders WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return self._to_order(row) if row else None

    def find_by_id(self, order_id: str) -> Optional[PaperOrder]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_orders WHERE id = ?", (order_id,)
            ).fetchone()
        return self._to_order(row) if row else None

    def save(self, order: PaperOrder) -> PaperOrder:
        values = order.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_orders (
                    id, candidate_id, symbol, status, quantity, entry_price,
                    stop_price, target_one, target_two, planned_risk,
                    required_cash, idempotency_key, created_at, filled_quantity,
                    average_fill_price, fees, updated_at
                ) VALUES (
                    :id, :candidate_id, :symbol, :status, :quantity, :entry_price,
                    :stop_price, :target_one, :target_two, :planned_risk,
                    :required_cash, :idempotency_key, :created_at, :filled_quantity,
                    :average_fill_price, :fees, :updated_at
                )
                """,
                values,
            )
        return order

    def update(self, order: PaperOrder) -> PaperOrder:
        values = order.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE paper_orders SET
                    status = :status,
                    filled_quantity = :filled_quantity,
                    average_fill_price = :average_fill_price,
                    fees = :fees,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                values,
            )
        return order

    def apply_fill(self, order: PaperOrder, fill: PaperFill) -> PaperOrder:
        order_values = order.model_dump(mode="json")
        fill_values = fill.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO paper_fills (
                    id, order_id, symbol, quantity, observed_price,
                    fill_price, fee, filled_at
                ) VALUES (
                    :id, :order_id, :symbol, :quantity, :observed_price,
                    :fill_price, :fee, :filled_at
                )
                """,
                fill_values,
            )
            connection.execute(
                """
                UPDATE paper_orders SET
                    status = :status,
                    filled_quantity = :filled_quantity,
                    average_fill_price = :average_fill_price,
                    fees = :fees,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                order_values,
            )
        return order

    def list_orders(self) -> List[PaperOrder]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_orders ORDER BY created_at DESC"
            ).fetchall()
        return [self._to_order(row) for row in rows]

    def list_fills(self) -> List[PaperFill]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_fills ORDER BY filled_at DESC"
            ).fetchall()
        return [PaperFill.model_validate(dict(row)) for row in rows]

    @staticmethod
    def _write_position(connection: sqlite3.Connection, position: PaperPosition) -> None:
        connection.execute(
            """
            INSERT INTO paper_positions (
                id, order_id, symbol, status, quantity_open, quantity_closed,
                average_entry_price, current_stop, target_one, target_two,
                tp1_quantity, tp1_filled_quantity, trailing_active,
                highest_price, entry_fees, exit_fees, realized_pnl, updated_at
            ) VALUES (
                :id, :order_id, :symbol, :status, :quantity_open, :quantity_closed,
                :average_entry_price, :current_stop, :target_one, :target_two,
                :tp1_quantity, :tp1_filled_quantity, :trailing_active,
                :highest_price, :entry_fees, :exit_fees, :realized_pnl, :updated_at
            ) ON CONFLICT(order_id) DO UPDATE SET
                status = excluded.status,
                quantity_open = excluded.quantity_open,
                quantity_closed = excluded.quantity_closed,
                average_entry_price = excluded.average_entry_price,
                current_stop = excluded.current_stop,
                tp1_filled_quantity = excluded.tp1_filled_quantity,
                trailing_active = excluded.trailing_active,
                highest_price = excluded.highest_price,
                entry_fees = excluded.entry_fees,
                exit_fees = excluded.exit_fees,
                realized_pnl = excluded.realized_pnl,
                updated_at = excluded.updated_at
            """,
            position.model_dump(mode="json"),
        )

    def _upsert_position(self, position: PaperPosition) -> None:
        with self._connect() as connection:
            self._write_position(connection, position)

    def apply_replay(
        self,
        observation: ReplayObservation,
        order: Optional[PaperOrder] = None,
        fill: Optional[PaperFill] = None,
        position: Optional[PaperPosition] = None,
    ) -> None:
        observation_values = observation.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO replay_observations (
                    symbol, sequence, observed_at, price, available_quantity
                ) VALUES (
                    :symbol, :sequence, :observed_at, :price, :available_quantity
                )
                """,
                observation_values,
            )
            if fill is not None and order is not None:
                connection.execute(
                    """
                    INSERT INTO paper_fills (
                        id, order_id, symbol, quantity, observed_price,
                        fill_price, fee, filled_at
                    ) VALUES (
                        :id, :order_id, :symbol, :quantity, :observed_price,
                        :fill_price, :fee, :filled_at
                    )
                    """,
                    fill.model_dump(mode="json"),
                )
                connection.execute(
                    """
                    UPDATE paper_orders SET
                        status = :status,
                        filled_quantity = :filled_quantity,
                        average_fill_price = :average_fill_price,
                        fees = :fees,
                        updated_at = :updated_at
                    WHERE id = :id
                    """,
                    order.model_dump(mode="json"),
                )
                if position is not None:
                    self._write_position(connection, position)

    def find_position(self, position_id: str) -> Optional[PaperPosition]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_positions WHERE id = ?", (position_id,)
            ).fetchone()
        return PaperPosition.model_validate(dict(row)) if row else None

    def list_positions(self) -> List[PaperPosition]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_positions ORDER BY updated_at DESC"
            ).fetchall()
        return [PaperPosition.model_validate(dict(row)) for row in rows]

    def list_exit_fills(self) -> List[PaperExitFill]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_exit_fills ORDER BY filled_at DESC"
            ).fetchall()
        return [PaperExitFill.model_validate(dict(row)) for row in rows]

    def exit_observation_count(self, symbol: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM exit_replay_observations WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        return int(row["count"])

    def apply_exit_replay(
        self,
        observation: ExitReplayObservation,
        position: PaperPosition,
        fill: Optional[PaperExitFill] = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO exit_replay_observations (
                    symbol, sequence, observed_at, price, available_quantity,
                    trailing_candidate
                ) VALUES (
                    :symbol, :sequence, :observed_at, :price,
                    :available_quantity, :trailing_candidate
                )
                """,
                observation.model_dump(mode="json"),
            )
            if fill is not None:
                connection.execute(
                    """
                    INSERT INTO paper_exit_fills (
                        id, position_id, symbol, reason, quantity,
                        observed_price, fill_price, fee, filled_at
                    ) VALUES (
                        :id, :position_id, :symbol, :reason, :quantity,
                        :observed_price, :fill_price, :fee, :filled_at
                    )
                    """,
                    fill.model_dump(mode="json"),
                )
            self._write_position(connection, position)

    def observation_count(self, symbol: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM replay_observations WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        return int(row["count"])

    def record_observation(self, observation: ReplayObservation) -> None:
        values = observation.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO replay_observations (
                    symbol, sequence, observed_at, price, available_quantity
                ) VALUES (
                    :symbol, :sequence, :observed_at, :price, :available_quantity
                )
                """,
                values,
            )
