import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from signaldesk.config import AppSettings
from signaldesk.domain.models import ScheduledScanJob, SchedulerStatus
from signaldesk.domain.ports import ScanRepository, TradingCalendar

from .scans import ScanService


class ScanScheduler:
    def __init__(
        self,
        settings: AppSettings,
        scans: ScanService,
        repository: ScanRepository,
        calendar: TradingCalendar,
    ) -> None:
        self._settings = settings
        self._scans = scans
        self._repository = repository
        self._calendar = calendar
        self._timezone = ZoneInfo(settings.scanning.timezone)

    @staticmethod
    def _slot_time(slot: str) -> time:
        hour, minute = (int(part) for part in slot.split(":"))
        return time(hour=hour, minute=minute)

    def _scheduled_at(self, local_now: datetime, slot: str) -> datetime:
        return datetime.combine(
            local_now.date(), self._slot_time(slot), tzinfo=self._timezone
        )

    def _slot_key(self, scheduled_for: datetime, slot: str) -> str:
        policy = self._settings.scanning
        return ":".join(
            (
                scheduled_for.date().isoformat(),
                slot,
                self._settings.strategy.version,
                policy.universe_version,
            )
        )

    def tick(self, now: Optional[datetime] = None) -> List[ScheduledScanJob]:
        policy = self._settings.scanning
        if not policy.automatic_enabled:
            return []
        current = now or datetime.now(timezone.utc)
        local_now = current.astimezone(self._timezone)
        if not self._calendar.is_session(local_now.date()):
            return []

        window = timedelta(minutes=policy.catch_up_window_minutes)
        lease = timedelta(seconds=policy.job_lease_seconds)
        attempted = False
        for slot in policy.schedule_slots:
            scheduled_for = self._scheduled_at(local_now, slot)
            if not (scheduled_for <= local_now <= scheduled_for + window):
                continue
            started_at = datetime.now(timezone.utc)
            slot_key = self._slot_key(scheduled_for, slot)
            claimed = self._repository.acquire_job(
                slot_key=slot_key,
                scheduled_for=scheduled_for,
                started_at=started_at,
                lease_expires_at=started_at + lease,
                maximum_attempts=policy.maximum_attempts,
            )
            if not claimed:
                continue
            attempted = True
            try:
                run = self._scans.archive_current(slot_key=slot_key)
                self._repository.finish_job(
                    slot_key,
                    "COMPLETE",
                    datetime.now(timezone.utc),
                    scan_run_id=run.id,
                )
            except Exception as error:
                self._repository.finish_job(
                    slot_key,
                    "FAILED",
                    datetime.now(timezone.utc),
                    error=str(error),
                )
        return (
            self._repository.list_jobs(policy.job_history_limit) if attempted else []
        )

    def next_run(self, now: Optional[datetime] = None) -> Optional[datetime]:
        policy = self._settings.scanning
        if not policy.automatic_enabled:
            return None
        current = (now or datetime.now(timezone.utc)).astimezone(self._timezone)
        for day_offset in range(370):
            day = current + timedelta(days=day_offset)
            if not self._calendar.is_session(day.date()):
                continue
            for slot in sorted(policy.schedule_slots):
                candidate = self._scheduled_at(day, slot)
                if candidate > current:
                    return candidate
        return None

    def status(self, now: Optional[datetime] = None) -> SchedulerStatus:
        policy = self._settings.scanning
        current = (now or datetime.now(timezone.utc)).astimezone(self._timezone)
        return SchedulerStatus(
            enabled=policy.automatic_enabled,
            timezone=policy.timezone,
            calendarName=self._calendar.name(),
            currentDayIsSession=self._calendar.is_session(current.date()),
            scheduleSlots=policy.schedule_slots,
            activeWeekdays=policy.active_weekdays,
            nextRunAt=self.next_run(current),
            jobs=self._repository.list_jobs(policy.job_history_limit),
        )

    async def run_forever(self) -> None:
        policy = self._settings.scanning
        while policy.automatic_enabled:
            await asyncio.to_thread(self.tick)
            await asyncio.sleep(policy.poll_interval_seconds)
