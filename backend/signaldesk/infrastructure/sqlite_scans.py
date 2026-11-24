import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from signaldesk.domain.models import Candidate, ScanRun, ScheduledScanJob


class SqliteScanRepository:
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
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id TEXT PRIMARY KEY,
                    slot_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    universe_version TEXT NOT NULL,
                    evaluated_count INTEGER NOT NULL,
                    excluded_count INTEGER NOT NULL,
                    coverage_ratio REAL NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_scan_jobs (
                    slot_key TEXT PRIMARY KEY,
                    scheduled_for TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    lease_expires_at TEXT NOT NULL,
                    scan_run_id TEXT,
                    error TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_candidates (
                    run_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, rank),
                    FOREIGN KEY(run_id) REFERENCES scan_runs(id)
                )
                """
            )

    def ping(self) -> bool:
        try:
            with self._connect() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except sqlite3.Error:
            return False

    @staticmethod
    def _to_run(connection: sqlite3.Connection, row: sqlite3.Row) -> ScanRun:
        candidate_rows = connection.execute(
            "SELECT payload FROM scan_candidates WHERE run_id = ? ORDER BY rank",
            (row["id"],),
        ).fetchall()
        candidates = [
            Candidate.model_validate(json.loads(item["payload"]))
            for item in candidate_rows
        ]
        values = dict(row)
        values["candidates"] = candidates
        return ScanRun.model_validate(values)

    def find_by_slot_key(self, slot_key: str) -> Optional[ScanRun]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scan_runs WHERE slot_key = ?", (slot_key,)
            ).fetchone()
            return self._to_run(connection, row) if row else None

    def save(self, run: ScanRun) -> ScanRun:
        values = run.model_dump(mode="json", exclude={"candidates"})
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO scan_runs (
                    id, slot_key, status, as_of, completed_at, source,
                    strategy_version, universe_version, evaluated_count,
                    excluded_count, coverage_ratio
                ) VALUES (
                    :id, :slot_key, :status, :as_of, :completed_at, :source,
                    :strategy_version, :universe_version, :evaluated_count,
                    :excluded_count, :coverage_ratio
                )
                """,
                values,
            )
            for candidate in run.candidates:
                connection.execute(
                    "INSERT INTO scan_candidates (run_id, rank, payload) VALUES (?, ?, ?)",
                    (
                        run.id,
                        candidate.rank,
                        json.dumps(candidate.model_dump(mode="json", by_alias=True)),
                    ),
                )
        return run

    def list_recent(self, retention_days: int) -> List[ScanRun]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scan_runs WHERE completed_at >= ? ORDER BY completed_at DESC",
                (cutoff.isoformat(),),
            ).fetchall()
            return [self._to_run(connection, row) for row in rows]

    def acquire_job(
        self,
        slot_key: str,
        scheduled_for: datetime,
        started_at: datetime,
        lease_expires_at: datetime,
        maximum_attempts: int,
    ) -> bool:
        values = (
            slot_key,
            scheduled_for.isoformat(),
            "RUNNING",
            started_at.isoformat(),
            lease_expires_at.isoformat(),
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO scheduled_scan_jobs (
                    slot_key, scheduled_for, status, attempts, started_at,
                    lease_expires_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                """,
                values,
            )
            if inserted.rowcount == 1:
                return True
            recovered = connection.execute(
                """
                UPDATE scheduled_scan_jobs SET
                    status = 'RUNNING', attempts = attempts + 1,
                    started_at = ?, finished_at = NULL,
                    lease_expires_at = ?, scan_run_id = NULL, error = NULL
                WHERE slot_key = ?
                  AND attempts < ?
                  AND (status = 'FAILED' OR (status = 'RUNNING' AND lease_expires_at < ?))
                """,
                (
                    started_at.isoformat(),
                    lease_expires_at.isoformat(),
                    slot_key,
                    maximum_attempts,
                    started_at.isoformat(),
                ),
            )
            return recovered.rowcount == 1

    def finish_job(
        self,
        slot_key: str,
        status: str,
        finished_at: datetime,
        scan_run_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE scheduled_scan_jobs SET
                    status = ?, finished_at = ?, scan_run_id = ?, error = ?
                WHERE slot_key = ?
                """,
                (status, finished_at.isoformat(), scan_run_id, error, slot_key),
            )

    def list_jobs(self, limit: int) -> List[ScheduledScanJob]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scheduled_scan_jobs
                ORDER BY scheduled_for DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [ScheduledScanJob.model_validate(dict(row)) for row in rows]
