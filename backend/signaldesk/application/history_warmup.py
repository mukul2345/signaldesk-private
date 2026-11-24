import asyncio

from signaldesk.config import NseMcpSettings
from signaldesk.infrastructure.nse_mcp_market_data import NseMcpDailyBarProvider


class HistoryWarmupWorker:
    def __init__(
        self, settings: NseMcpSettings, provider: NseMcpDailyBarProvider
    ) -> None:
        self._settings = settings
        self._provider = provider

    async def run_forever(self) -> None:
        while self._settings.automatic_history_warmup_enabled:
            try:
                status = await asyncio.to_thread(self._provider.warmup_status)
                if status.available and not status.ready_to_activate:
                    await asyncio.to_thread(self._provider.warmup_next_batch)
            except Exception:
                # Per-symbol failures are persisted by the provider and retried on
                # later passes. The worker must not terminate the API lifespan.
                pass
            await asyncio.sleep(self._settings.history_warmup_interval_seconds)
