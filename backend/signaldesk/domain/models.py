from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MarketIndex(DomainModel):
    id: str
    name: str
    value: float
    change_percent: float = Field(alias="changePercent")
    direction: Literal["up", "down", "flat"]
    status: str
    points: List[float]


class Candidate(DomainModel):
    id: str
    rank: int
    symbol: str
    company: str
    sector: str
    price: float
    change_percent: float = Field(alias="changePercent")
    score: int = Field(ge=0, le=100)
    state: Literal["READY", "WATCH", "AVOID"]
    setup: str
    volume_ratio: float = Field(alias="volumeRatio")
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    target_one: float = Field(alias="targetOne", gt=0)
    target_two: float = Field(alias="targetTwo", gt=0)
    probability: Optional[int]
    reasons: List[str]
    contradictions: List[str]


class AccountSummary(DomainModel):
    available_cash: float = Field(alias="availableCash")
    deployed: float
    open_risk: float = Field(alias="openRisk")
    today_pnl: float = Field(alias="todayPnl")


class DashboardPolicy(DomainModel):
    capital_ceiling: float = Field(alias="capitalCeiling")
    risk_per_trade: float = Field(alias="riskPerTrade")
    display_limit: int = Field(alias="displayLimit")


class ScanCoverage(DomainModel):
    eligible_count: int = Field(alias="eligibleCount", gt=0)
    evaluated_count: int = Field(alias="evaluatedCount", ge=0)
    excluded_count: int = Field(alias="excludedCount", ge=0)
    missing_symbols: List[str] = Field(alias="missingSymbols")


class DashboardPayload(DomainModel):
    as_of: datetime
    source: str
    market_status: str
    next_scan: str
    indices: List[MarketIndex]
    candidates: List[Candidate]
    account: AccountSummary
    policy: Optional[DashboardPolicy] = None
    pending_orders: List[PaperOrder] = Field(default_factory=list, alias="pendingOrders")
    scan_coverage: ScanCoverage = Field(alias="scanCoverage")


class ScanRun(DomainModel):
    id: str
    slot_key: str = Field(alias="slotKey")
    status: Literal["COMPLETE", "INCOMPLETE"]
    as_of: datetime
    completed_at: datetime = Field(alias="completedAt")
    source: str
    strategy_version: str = Field(alias="strategyVersion")
    universe_version: str = Field(alias="universeVersion")
    evaluated_count: int = Field(alias="evaluatedCount", ge=0)
    excluded_count: int = Field(alias="excludedCount", ge=0)
    coverage_ratio: float = Field(alias="coverageRatio", ge=0, le=1)
    candidates: List[Candidate]


class ScanHistoryPayload(DomainModel):
    retention_days: int = Field(alias="retentionDays", gt=0)
    schedule_slots: List[str] = Field(alias="scheduleSlots")
    timezone: str
    archive_limit: int = Field(alias="archiveLimit", gt=0)
    runs: List[ScanRun]


class PortfolioPositionAnalysis(DomainModel):
    symbol: str
    status: Literal["OPEN", "CLOSED"]
    quantity: int = Field(ge=0)
    average_entry: float = Field(alias="averageEntry", gt=0)
    current_price: Optional[float] = Field(default=None, alias="currentPrice", gt=0)
    current_stop: float = Field(alias="currentStop", gt=0)
    target_one: float = Field(alias="targetOne", gt=0)
    target_two: float = Field(alias="targetTwo", gt=0)
    market_value: float = Field(alias="marketValue", ge=0)
    unrealized_pnl: Optional[float] = Field(default=None, alias="unrealizedPnl")
    realized_pnl: float = Field(alias="realizedPnl")
    distance_to_stop_percent: Optional[float] = Field(
        default=None, alias="distanceToStopPercent"
    )
    next_target: Optional[float] = Field(default=None, alias="nextTarget", gt=0)


class PortfolioAnalysisPayload(DomainModel):
    as_of: datetime
    health: Literal["NO_POSITIONS", "HEALTHY", "ATTENTION", "AT_RISK"]
    open_positions: int = Field(alias="openPositions", ge=0)
    cost_basis: float = Field(alias="costBasis", ge=0)
    market_value: float = Field(alias="marketValue", ge=0)
    unrealized_pnl: float = Field(alias="unrealizedPnl")
    realized_pnl: float = Field(alias="realizedPnl")
    reserved_risk: float = Field(alias="reservedRisk", ge=0)
    largest_position_percent: float = Field(alias="largestPositionPercent", ge=0)
    stale_symbols: List[str] = Field(alias="staleSymbols")
    observations: List[str]
    positions: List[PortfolioPositionAnalysis]


class DailyBriefPayload(DomainModel):
    generated_at: datetime = Field(alias="generatedAt")
    scan: Optional[ScanRun]
    top_setups: List[Candidate] = Field(alias="topSetups")
    portfolio: PortfolioAnalysisPayload
    message: str


class MonthlyPerformance(DomainModel):
    month: str
    closed_trades: int = Field(alias="closedTrades", ge=0)
    net_pnl: float = Field(alias="netPnl")
    return_percent: float = Field(alias="returnPercent")


class PerformanceValidationPayload(DomainModel):
    status: Literal["INSUFFICIENT_EVIDENCE", "FAILED_RISK_GATE", "EVIDENCE_READY"]
    closed_trades: int = Field(alias="closedTrades", ge=0)
    minimum_required_trades: int = Field(alias="minimumRequiredTrades", gt=0)
    winning_trades: int = Field(alias="winningTrades", ge=0)
    losing_trades: int = Field(alias="losingTrades", ge=0)
    win_rate_percent: float = Field(alias="winRatePercent", ge=0, le=100)
    net_pnl: float = Field(alias="netPnl")
    average_pnl_per_trade: float = Field(alias="averagePnlPerTrade")
    maximum_drawdown: float = Field(alias="maximumDrawdown", ge=0)
    maximum_drawdown_percent: float = Field(alias="maximumDrawdownPercent", ge=0)
    last_30_day_return_percent: float = Field(alias="last30DayReturnPercent")
    target_monthly_return_percent: float = Field(alias="targetMonthlyReturnPercent")
    target_observed: bool = Field(alias="targetObserved")
    months: List[MonthlyPerformance]
    warnings: List[str]


class ScheduledScanJob(DomainModel):
    slot_key: str = Field(alias="slotKey")
    scheduled_for: datetime = Field(alias="scheduledFor")
    status: Literal["RUNNING", "COMPLETE", "FAILED"]
    attempts: int = Field(ge=1)
    started_at: datetime = Field(alias="startedAt")
    finished_at: Optional[datetime] = Field(default=None, alias="finishedAt")
    lease_expires_at: datetime = Field(alias="leaseExpiresAt")
    scan_run_id: Optional[str] = Field(default=None, alias="scanRunId")
    error: Optional[str] = None


class SchedulerStatus(DomainModel):
    enabled: bool
    timezone: str
    calendar_name: str = Field(alias="calendarName")
    current_day_is_session: bool = Field(alias="currentDayIsSession")
    schedule_slots: List[str] = Field(alias="scheduleSlots")
    active_weekdays: List[int] = Field(alias="activeWeekdays")
    next_run_at: Optional[datetime] = Field(alias="nextRunAt")
    jobs: List[ScheduledScanJob]


class PublicProviderSettings(DomainModel):
    research: str
    market_data: str = Field(alias="marketData")
    execution: str
    institutional_data: str = Field(alias="institutionalData")


class PublicRiskSettings(DomainModel):
    risk_per_trade: int = Field(alias="riskPerTrade")
    maximum_aggregate_initial_risk: int = Field(alias="maximumAggregateInitialRisk")
    maximum_position_value: int = Field(alias="maximumPositionValue")
    maximum_open_positions: int = Field(alias="maximumOpenPositions")


class PublicScanningSettings(DomainModel):
    strategy_version: str = Field(alias="strategyVersion")
    universe_version: str = Field(alias="universeVersion")
    schedule_slots: List[str] = Field(alias="scheduleSlots")
    timezone: str
    automatic_enabled: bool = Field(alias="automaticEnabled")
    active_weekdays: List[int] = Field(alias="activeWeekdays")
    history_retention_days: int = Field(alias="historyRetentionDays")
    minimum_coverage_ratio: float = Field(alias="minimumCoverageRatio")
    archivable_states: List[str] = Field(alias="archivableStates")


class PublicExecutionSettings(DomainModel):
    paper_enabled: bool = Field(alias="paperEnabled")
    live_enabled: bool = Field(alias="liveEnabled")
    require_individual_entry_approval: bool = Field(
        alias="requireIndividualEntryApproval"
    )


class PublicStrategySettings(DomainModel):
    version: str
    warmup_bars: int = Field(alias="warmupBars")
    fast_sma_period: int = Field(alias="fastSmaPeriod")
    slow_sma_period: int = Field(alias="slowSmaPeriod")
    breakout_lookback: int = Field(alias="breakoutLookback")
    volume_average_period: int = Field(alias="volumeAveragePeriod")
    minimum_volume_ratio: float = Field(alias="minimumVolumeRatio")
    atr_period: int = Field(alias="atrPeriod")
    initial_stop_atr_multiple: float = Field(alias="initialStopAtrMultiple")
    entry_buffer_bps: int = Field(alias="entryBufferBps")
    maximum_entry_extension_bps: int = Field(alias="maximumEntryExtensionBps")
    target_one_r: float = Field(alias="targetOneR")
    target_two_r: float = Field(alias="targetTwoR")
    maximum_holding_sessions: int = Field(alias="maximumHoldingSessions")


class PublicSettingsPayload(DomainModel):
    schema_version: str = Field(alias="schemaVersion")
    configuration_hash: str = Field(alias="configurationHash")
    mode: str
    currency: str
    capital_ceiling: int = Field(alias="capitalCeiling")
    providers: PublicProviderSettings
    risk: PublicRiskSettings
    strategy: PublicStrategySettings
    scanning: PublicScanningSettings
    execution: PublicExecutionSettings


class ComponentHealth(DomainModel):
    id: str
    label: str
    status: Literal["HEALTHY", "READY", "DEMO", "NOT_CONFIGURED", "ERROR"]
    detail: str


class ProviderReadiness(DomainModel):
    status: Literal["HEALTHY", "READY", "DEMO", "NOT_CONFIGURED", "ERROR"]
    detail: str


class MarketDataWarmupStatus(DomainModel):
    available: bool
    target_version: Optional[str] = Field(default=None, alias="targetVersion")
    total_symbols: int = Field(alias="totalSymbols", ge=0)
    warmed_symbols: int = Field(alias="warmedSymbols", ge=0)
    remaining_symbols: int = Field(alias="remainingSymbols", ge=0)
    batch_size: int = Field(alias="batchSize", gt=0)
    active_universe_symbols: int = Field(alias="activeUniverseSymbols", ge=0)
    failed_symbols: List[str] = Field(alias="failedSymbols")
    last_updated_at: Optional[datetime] = Field(default=None, alias="lastUpdatedAt")
    ready_to_activate: bool = Field(alias="readyToActivate")


class PromotionCheck(DomainModel):
    id: str
    label: str
    status: Literal["PASS", "PENDING", "BLOCKED"]
    detail: str


class UniversePromotionStatus(DomainModel):
    candidate_available: bool = Field(alias="candidateAvailable")
    candidate_version: Optional[str] = Field(default=None, alias="candidateVersion")
    runtime_active_version: str = Field(alias="runtimeActiveVersion")
    prepared_version: Optional[str] = Field(default=None, alias="preparedVersion")
    total_symbols: int = Field(alias="totalSymbols", ge=0)
    warmed_symbols: int = Field(alias="warmedSymbols", ge=0)
    latest_session: Optional[date] = Field(default=None, alias="latestSession")
    corporate_actions_fresh: bool = Field(alias="corporateActionsFresh")
    corporate_actions_checked_at: Optional[datetime] = Field(
        default=None, alias="corporateActionsCheckedAt"
    )
    blocking_action_count: int = Field(alias="blockingActionCount", ge=0)
    blocking_action_symbols: List[str] = Field(alias="blockingActionSymbols")
    adjusted_action_count: int = Field(alias="adjustedActionCount", ge=0)
    adjusted_action_symbols: List[str] = Field(alias="adjustedActionSymbols")
    price_anomaly_count: int = Field(alias="priceAnomalyCount", ge=0)
    price_anomaly_symbols: List[str] = Field(alias="priceAnomalySymbols")
    stale_history_count: int = Field(alias="staleHistoryCount", ge=0)
    stale_history_symbols: List[str] = Field(alias="staleHistorySymbols")
    eligible_to_promote: bool = Field(alias="eligibleToPromote")
    restart_required: bool = Field(alias="restartRequired")
    checks: List[PromotionCheck]


class UniversePromotionRequest(DomainModel):
    candidate_version: str = Field(alias="candidateVersion", min_length=1)


class SystemHealthPayload(DomainModel):
    overall: Literal["SAFE_PAPER", "DEGRADED"]
    checked_at: datetime = Field(alias="checkedAt")
    paper_safety_enforced: bool = Field(alias="paperSafetyEnforced")
    components: List[ComponentHealth]


class DailyBar(DomainModel):
    session: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "DailyBar":
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("Daily bar OHLC range is invalid")
        return self


class StrategyEvaluation(DomainModel):
    strategy_version: str = Field(alias="strategyVersion")
    state: Literal["READY", "WATCH", "AVOID", "INSUFFICIENT"]
    as_of: Optional[date] = Field(default=None, alias="asOf")
    bars_used: int = Field(alias="barsUsed", ge=0)
    score: int = Field(ge=0, le=100)
    fast_sma: Optional[float] = Field(default=None, alias="fastSma")
    slow_sma: Optional[float] = Field(default=None, alias="slowSma")
    breakout_level: Optional[float] = Field(default=None, alias="breakoutLevel")
    volume_ratio: Optional[float] = Field(default=None, alias="volumeRatio")
    atr: Optional[float] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_one: Optional[float] = Field(default=None, alias="targetOne")
    target_two: Optional[float] = Field(default=None, alias="targetTwo")
    maximum_holding_sessions: int = Field(alias="maximumHoldingSessions", gt=0)
    reasons: List[str]
    contradictions: List[str]


class InstrumentBars(DomainModel):
    symbol: str
    company: str
    sector: str
    bars: List[DailyBar]


class PaperOrderRequest(DomainModel):
    candidate_id: str
    idempotency_key: str = Field(min_length=8, max_length=128)


class PaperOrder(DomainModel):
    id: str
    candidate_id: str
    symbol: str
    status: Literal[
        "PENDING_SIMULATION", "PARTIALLY_FILLED", "FILLED", "CANCELLED"
    ]
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_price: float = Field(gt=0)
    target_one: float = Field(gt=0)
    target_two: float = Field(gt=0)
    planned_risk: float = Field(gt=0)
    required_cash: float = Field(gt=0)
    idempotency_key: str
    created_at: datetime
    filled_quantity: int = Field(default=0, ge=0)
    average_fill_price: Optional[float] = Field(default=None, gt=0)
    fees: float = Field(default=0, ge=0)
    updated_at: Optional[datetime] = None


class PaperFill(DomainModel):
    id: str
    order_id: str
    symbol: str
    quantity: int = Field(gt=0)
    observed_price: float = Field(gt=0)
    fill_price: float = Field(gt=0)
    fee: float = Field(ge=0)
    filled_at: datetime


class PaperPosition(DomainModel):
    id: str
    order_id: str
    symbol: str
    status: Literal["OPEN", "CLOSED"]
    quantity_open: int = Field(ge=0)
    quantity_closed: int = Field(ge=0)
    average_entry_price: float = Field(gt=0)
    current_stop: float = Field(gt=0)
    target_one: float = Field(gt=0)
    target_two: float = Field(gt=0)
    tp1_quantity: int = Field(ge=0)
    tp1_filled_quantity: int = Field(default=0, ge=0)
    trailing_active: bool = False
    highest_price: float = Field(gt=0)
    entry_fees: float = Field(default=0, ge=0)
    exit_fees: float = Field(default=0, ge=0)
    realized_pnl: float = 0
    updated_at: datetime


class PaperExitFill(DomainModel):
    id: str
    position_id: str
    symbol: str
    reason: Literal["TP1", "TP2", "INITIAL_STOP", "TRAILING_STOP"]
    quantity: int = Field(gt=0)
    observed_price: float = Field(gt=0)
    fill_price: float = Field(gt=0)
    fee: float = Field(ge=0)
    filled_at: datetime


class ExitReplayObservation(DomainModel):
    symbol: str
    sequence: int = Field(ge=0)
    observed_at: datetime
    price: float = Field(gt=0)
    available_quantity: int = Field(gt=0)
    trailing_candidate: Optional[float] = Field(default=None, gt=0)


class ExitReplayResult(DomainModel):
    observation: ExitReplayObservation
    outcome: Literal[
        "HOLD",
        "TP1_FILL",
        "TP2_FILL",
        "INITIAL_STOP_FILL",
        "TRAILING_STOP_FILL",
        "TRAILING_UPDATED",
    ]
    message: str
    position: PaperPosition
    fill: Optional[PaperExitFill] = None
    previous_stop: float
    replay_complete: bool = False


class ReplayObservation(DomainModel):
    symbol: str
    sequence: int = Field(ge=0)
    observed_at: datetime
    price: float = Field(gt=0)
    available_quantity: int = Field(gt=0)


class ReplayResult(DomainModel):
    observation: ReplayObservation
    outcome: Literal["WAITING_FOR_ENTRY", "PARTIAL_FILL", "FILLED", "NO_ACTIVE_ORDER"]
    message: str
    order: Optional[PaperOrder] = None
    fill: Optional[PaperFill] = None
    replay_complete: bool = False


class PaperAccountPayload(DomainModel):
    orders: List[PaperOrder]
    fills: List[PaperFill]
    positions: List[PaperPosition]
    exit_fills: List[PaperExitFill] = Field(alias="exitFills")
    available_cash: float = Field(alias="availableCash")
    reserved_cash: float = Field(alias="reservedCash")
    deployed_value: float = Field(alias="deployedValue")
    reserved_risk: float = Field(alias="reservedRisk")
