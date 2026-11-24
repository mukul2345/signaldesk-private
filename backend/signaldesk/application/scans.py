from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from signaldesk.config import AppSettings
from signaldesk.domain.models import ScanHistoryPayload, ScanRun
from signaldesk.domain.ports import ResearchProvider, ScanRepository


class ScanError(ValueError):
    pass


class ScanService:
    def __init__(
        self,
        settings: AppSettings,
        research: ResearchProvider,
        repository: ScanRepository,
    ) -> None:
        self._settings = settings
        self._research = research
        self._repository = repository

    def archive_current(self, slot_key: Optional[str] = None) -> ScanRun:
        snapshot = self._research.dashboard()
        policy = self._settings.scanning
        slot_key = slot_key or ":".join(
            (
                snapshot.as_of.date().isoformat(),
                policy.snapshot_label,
                self._settings.strategy.version,
                policy.universe_version,
            )
        )
        existing = self._repository.find_by_slot_key(slot_key)
        if existing is not None:
            return existing

        coverage = snapshot.scan_coverage
        resolved = coverage.evaluated_count + coverage.excluded_count
        coverage_ratio = resolved / coverage.eligible_count
        count_matches = (
            resolved + len(coverage.missing_symbols) == coverage.eligible_count
        )
        if (
            not count_matches
            or coverage_ratio < policy.minimum_coverage_ratio
            or coverage.missing_symbols
        ):
            raise ScanError(
                "Scan is incomplete and cannot replace the published shortlist"
            )

        archived = [
            candidate
            for candidate in sorted(snapshot.candidates, key=lambda item: item.rank)
            if candidate.state in policy.archivable_states
        ][: self._settings.universe.archive_limit]
        run = ScanRun(
            id=str(uuid4()),
            slotKey=slot_key,
            status="COMPLETE",
            as_of=snapshot.as_of,
            completedAt=datetime.now(timezone.utc),
            source=snapshot.source,
            strategyVersion=self._settings.strategy.version,
            universeVersion=policy.universe_version,
            evaluatedCount=coverage.evaluated_count,
            excludedCount=coverage.excluded_count,
            coverageRatio=coverage_ratio,
            candidates=archived,
        )
        return self._repository.save(run)

    def history(self) -> ScanHistoryPayload:
        policy = self._settings.scanning
        return ScanHistoryPayload(
            retentionDays=policy.history_retention_days,
            scheduleSlots=policy.schedule_slots,
            timezone=policy.timezone,
            archiveLimit=self._settings.universe.archive_limit,
            runs=self._repository.list_recent(policy.history_retention_days),
        )
