import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from signaldesk.config import AppSettings
from signaldesk.domain.models import (
    ComponentHealth,
    PublicExecutionSettings,
    PublicProviderSettings,
    PublicRiskSettings,
    PublicScanningSettings,
    PublicStrategySettings,
    PublicSettingsPayload,
    ProviderReadiness,
    SystemHealthPayload,
)
from signaldesk.domain.ports import (
    DailyBarProvider,
    PaperOrderRepository,
    ResearchProvider,
    ScanRepository,
)

from .scheduler import ScanScheduler


class SystemStatusService:
    def __init__(
        self,
        settings: AppSettings,
        research: ResearchProvider,
        market_data: DailyBarProvider,
        orders: PaperOrderRepository,
        scans: ScanRepository,
        scheduler: ScanScheduler,
        angel_one_readiness: Optional[ProviderReadiness] = None,
    ) -> None:
        self._settings = settings
        self._research = research
        self._market_data = market_data
        self._orders = orders
        self._scans = scans
        self._scheduler = scheduler
        self._angel_one_readiness = angel_one_readiness

    def public_settings(self) -> PublicSettingsPayload:
        current = self._settings
        safe = {
            "schemaVersion": current.schema_version,
            "mode": current.mode,
            "currency": current.currency,
            "capitalCeiling": current.capital_ceiling,
            "providers": PublicProviderSettings(
                research=current.providers.research,
                marketData=current.providers.market_data,
                execution=current.providers.execution,
                institutionalData=current.providers.institutional_data,
            ).model_dump(mode="json", by_alias=True),
            "risk": PublicRiskSettings(
                riskPerTrade=current.risk.risk_per_trade,
                maximumAggregateInitialRisk=current.risk.maximum_aggregate_initial_risk,
                maximumPositionValue=current.risk.maximum_position_value,
                maximumOpenPositions=current.risk.maximum_open_positions,
            ).model_dump(mode="json", by_alias=True),
            "strategy": PublicStrategySettings(
                version=current.strategy.version,
                warmupBars=current.strategy.warmup_bars,
                fastSmaPeriod=current.strategy.fast_sma_period,
                slowSmaPeriod=current.strategy.slow_sma_period,
                breakoutLookback=current.strategy.breakout_lookback,
                volumeAveragePeriod=current.strategy.volume_average_period,
                minimumVolumeRatio=current.strategy.minimum_volume_ratio,
                atrPeriod=current.strategy.atr_period,
                initialStopAtrMultiple=current.strategy.initial_stop_atr_multiple,
                entryBufferBps=current.strategy.entry_buffer_bps,
                maximumEntryExtensionBps=current.strategy.maximum_entry_extension_bps,
                targetOneR=current.strategy.target_one_r,
                targetTwoR=current.strategy.target_two_r,
                maximumHoldingSessions=current.strategy.maximum_holding_sessions,
            ).model_dump(mode="json", by_alias=True),
            "scanning": PublicScanningSettings(
                strategyVersion=current.strategy.version,
                universeVersion=current.scanning.universe_version,
                scheduleSlots=current.scanning.schedule_slots,
                timezone=current.scanning.timezone,
                automaticEnabled=current.scanning.automatic_enabled,
                activeWeekdays=current.scanning.active_weekdays,
                historyRetentionDays=current.scanning.history_retention_days,
                minimumCoverageRatio=current.scanning.minimum_coverage_ratio,
                archivableStates=current.scanning.archivable_states,
            ).model_dump(mode="json", by_alias=True),
            "execution": PublicExecutionSettings(
                paperEnabled=current.execution.paper_enabled,
                liveEnabled=current.execution.live_enabled,
                requireIndividualEntryApproval=current.execution.require_individual_entry_approval,
            ).model_dump(mode="json", by_alias=True),
        }
        fingerprint = hashlib.sha256(
            json.dumps(safe, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return PublicSettingsPayload(
            **safe,
            configurationHash=fingerprint,
        )

    def health(self) -> SystemHealthPayload:
        checked_at = datetime.now(timezone.utc)
        components = []
        research_ok = True
        try:
            snapshot = self._research.dashboard()
            research_status = (
                "DEMO" if self._market_data.readiness().status == "DEMO" else "HEALTHY"
            )
            components.append(
                ComponentHealth(
                    id="research",
                    label="Research provider",
                    status=research_status,
                    detail="{} · data cutoff {}".format(
                        snapshot.source.replace("_", " "), snapshot.as_of.isoformat()
                    ),
                )
            )
        except Exception as error:
            research_ok = False
            components.append(
                ComponentHealth(
                    id="research",
                    label="Research provider",
                    status="ERROR",
                    detail=str(error),
                )
            )

        database_ok = self._orders.ping() and self._scans.ping()
        next_run = self._scheduler.next_run()
        market_data_readiness = self._market_data.readiness()
        components.extend(
            [
                ComponentHealth(
                    id="database",
                    label="Local SQLite ledger",
                    status="HEALTHY" if database_ok else "ERROR",
                    detail="Order, position, scan and scheduler records are reachable"
                    if database_ok
                    else "Local ledger is unavailable",
                ),
                ComponentHealth(
                    id="scheduler",
                    label="Automatic scheduler",
                    status="HEALTHY"
                    if self._settings.scanning.automatic_enabled
                    else "NOT_CONFIGURED",
                    detail="Next run {}".format(
                        next_run.isoformat() if next_run else "not scheduled"
                    ),
                ),
                ComponentHealth(
                    id="market_data",
                    label="Market data provider",
                    status=market_data_readiness.status,
                    detail=market_data_readiness.detail,
                ),
                ComponentHealth(
                    id="broker",
                    label="Broker execution",
                    status="NOT_CONFIGURED",
                    detail="Paper simulator only; no broker order path",
                ),
                ComponentHealth(
                    id="institutional",
                    label="Institutional evidence",
                    status="NOT_CONFIGURED",
                    detail=self._settings.providers.institutional_data.replace("_", " "),
                ),
            ]
        )
        if self._angel_one_readiness is not None:
            components.append(
                ComponentHealth(
                    id="angel_one",
                    label="Angel One connection",
                    status=self._angel_one_readiness.status,
                    detail=self._angel_one_readiness.detail,
                )
            )
        paper_safe = self._settings.mode == "paper" and not self._settings.execution.live_enabled
        return SystemHealthPayload(
            overall="SAFE_PAPER" if research_ok and database_ok and paper_safe else "DEGRADED",
            checkedAt=checked_at,
            paperSafetyEnforced=paper_safe,
            components=components,
        )
