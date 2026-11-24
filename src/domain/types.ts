export type Direction = "up" | "down" | "flat";
export type SignalState = "READY" | "WATCH" | "AVOID";

export interface MarketIndex {
  readonly id: string;
  readonly name: string;
  readonly value: number;
  readonly changePercent: number;
  readonly direction: Direction;
  readonly status: string;
  readonly points: readonly number[];
}

export interface Candidate {
  readonly id: string;
  readonly rank: number;
  readonly symbol: string;
  readonly company: string;
  readonly sector: string;
  readonly price: number;
  readonly changePercent: number;
  readonly score: number;
  readonly state: SignalState;
  readonly setup: string;
  readonly volumeRatio: number;
  readonly entry: number;
  readonly stop: number;
  readonly targetOne: number;
  readonly targetTwo: number;
  readonly probability: number | null;
  readonly reasons: readonly string[];
  readonly contradictions: readonly string[];
}

export interface DashboardConfig {
  readonly currency: string;
  readonly locale: string;
  readonly mode: "PAPER" | "LIVE";
  readonly dataLabel: string;
  readonly marketStatus: string;
  readonly nextScan: string;
  readonly sourceFreshness: string;
  readonly apiBaseUrl: string;
}

export interface AccountSummary {
  readonly availableCash: number;
  readonly deployed: number;
  readonly openRisk: number;
  readonly todayPnl: number;
}

export interface DashboardPayload {
  readonly as_of: string;
  readonly source: string;
  readonly market_status: string;
  readonly next_scan: string;
  readonly indices: readonly MarketIndex[];
  readonly candidates: readonly Candidate[];
  readonly account: AccountSummary;
  readonly policy: {
    readonly capitalCeiling: number;
    readonly riskPerTrade: number;
    readonly displayLimit: number;
  };
  readonly pendingOrders: readonly PaperOrder[];
  readonly scanCoverage: {
    readonly eligibleCount: number;
    readonly evaluatedCount: number;
    readonly excludedCount: number;
    readonly missingSymbols: readonly string[];
  };
}

export interface ScanRun {
  readonly id: string;
  readonly slotKey: string;
  readonly status: "COMPLETE" | "INCOMPLETE";
  readonly as_of: string;
  readonly completedAt: string;
  readonly source: string;
  readonly strategyVersion: string;
  readonly universeVersion: string;
  readonly evaluatedCount: number;
  readonly excludedCount: number;
  readonly coverageRatio: number;
  readonly candidates: readonly Candidate[];
}

export interface ScanHistoryPayload {
  readonly retentionDays: number;
  readonly scheduleSlots: readonly string[];
  readonly timezone: string;
  readonly archiveLimit: number;
  readonly runs: readonly ScanRun[];
}

export interface PortfolioPositionAnalysis {
  readonly symbol: string;
  readonly status: "OPEN" | "CLOSED";
  readonly quantity: number;
  readonly averageEntry: number;
  readonly currentPrice: number | null;
  readonly currentStop: number;
  readonly targetOne: number;
  readonly targetTwo: number;
  readonly marketValue: number;
  readonly unrealizedPnl: number | null;
  readonly realizedPnl: number;
  readonly distanceToStopPercent: number | null;
  readonly nextTarget: number | null;
}

export interface PortfolioAnalysisPayload {
  readonly as_of: string;
  readonly health: "NO_POSITIONS" | "HEALTHY" | "ATTENTION" | "AT_RISK";
  readonly openPositions: number;
  readonly costBasis: number;
  readonly marketValue: number;
  readonly unrealizedPnl: number;
  readonly realizedPnl: number;
  readonly reservedRisk: number;
  readonly largestPositionPercent: number;
  readonly staleSymbols: readonly string[];
  readonly observations: readonly string[];
  readonly positions: readonly PortfolioPositionAnalysis[];
}

export interface DailyBriefPayload {
  readonly generatedAt: string;
  readonly scan: ScanRun | null;
  readonly topSetups: readonly Candidate[];
  readonly portfolio: PortfolioAnalysisPayload;
  readonly message: string;
}

export interface PerformanceValidationPayload {
  readonly status: "INSUFFICIENT_EVIDENCE" | "FAILED_RISK_GATE" | "EVIDENCE_READY";
  readonly closedTrades: number;
  readonly minimumRequiredTrades: number;
  readonly winningTrades: number;
  readonly losingTrades: number;
  readonly winRatePercent: number;
  readonly netPnl: number;
  readonly averagePnlPerTrade: number;
  readonly maximumDrawdown: number;
  readonly maximumDrawdownPercent: number;
  readonly last30DayReturnPercent: number;
  readonly targetMonthlyReturnPercent: number;
  readonly targetObserved: boolean;
  readonly months: readonly {
    readonly month: string;
    readonly closedTrades: number;
    readonly netPnl: number;
    readonly returnPercent: number;
  }[];
  readonly warnings: readonly string[];
}

export interface ScheduledScanJob {
  readonly slotKey: string;
  readonly scheduledFor: string;
  readonly status: "RUNNING" | "COMPLETE" | "FAILED";
  readonly attempts: number;
  readonly startedAt: string;
  readonly finishedAt: string | null;
  readonly leaseExpiresAt: string;
  readonly scanRunId: string | null;
  readonly error: string | null;
}

export interface SchedulerStatus {
  readonly enabled: boolean;
  readonly timezone: string;
  readonly calendarName: string;
  readonly currentDayIsSession: boolean;
  readonly scheduleSlots: readonly string[];
  readonly activeWeekdays: readonly number[];
  readonly nextRunAt: string | null;
  readonly jobs: readonly ScheduledScanJob[];
}

export interface MarketDataWarmupStatus {
  readonly available: boolean;
  readonly targetVersion: string | null;
  readonly totalSymbols: number;
  readonly warmedSymbols: number;
  readonly remainingSymbols: number;
  readonly batchSize: number;
  readonly activeUniverseSymbols: number;
  readonly failedSymbols: readonly string[];
  readonly lastUpdatedAt: string | null;
  readonly readyToActivate: boolean;
}

export interface UniversePromotionStatus {
  readonly candidateAvailable: boolean;
  readonly candidateVersion: string | null;
  readonly runtimeActiveVersion: string;
  readonly preparedVersion: string | null;
  readonly totalSymbols: number;
  readonly warmedSymbols: number;
  readonly latestSession: string | null;
  readonly corporateActionsFresh: boolean;
  readonly corporateActionsCheckedAt: string | null;
  readonly blockingActionCount: number;
  readonly blockingActionSymbols: readonly string[];
  readonly adjustedActionCount: number;
  readonly adjustedActionSymbols: readonly string[];
  readonly priceAnomalyCount: number;
  readonly priceAnomalySymbols: readonly string[];
  readonly staleHistoryCount: number;
  readonly staleHistorySymbols: readonly string[];
  readonly eligibleToPromote: boolean;
  readonly restartRequired: boolean;
  readonly checks: readonly {
    readonly id: string;
    readonly label: string;
    readonly status: "PASS" | "PENDING" | "BLOCKED";
    readonly detail: string;
  }[];
}

export interface PublicSettingsPayload {
  readonly schemaVersion: string;
  readonly configurationHash: string;
  readonly mode: string;
  readonly currency: string;
  readonly capitalCeiling: number;
  readonly providers: {
    readonly research: string;
    readonly marketData: string;
    readonly execution: string;
    readonly institutionalData: string;
  };
  readonly risk: {
    readonly riskPerTrade: number;
    readonly maximumAggregateInitialRisk: number;
    readonly maximumPositionValue: number;
    readonly maximumOpenPositions: number;
  };
  readonly strategy: {
    readonly version: string;
    readonly warmupBars: number;
    readonly fastSmaPeriod: number;
    readonly slowSmaPeriod: number;
    readonly breakoutLookback: number;
    readonly volumeAveragePeriod: number;
    readonly minimumVolumeRatio: number;
    readonly atrPeriod: number;
    readonly initialStopAtrMultiple: number;
    readonly entryBufferBps: number;
    readonly maximumEntryExtensionBps: number;
    readonly targetOneR: number;
    readonly targetTwoR: number;
    readonly maximumHoldingSessions: number;
  };
  readonly scanning: {
    readonly strategyVersion: string;
    readonly universeVersion: string;
    readonly scheduleSlots: readonly string[];
    readonly timezone: string;
    readonly automaticEnabled: boolean;
    readonly activeWeekdays: readonly number[];
    readonly historyRetentionDays: number;
    readonly minimumCoverageRatio: number;
    readonly archivableStates: readonly string[];
  };
  readonly execution: {
    readonly paperEnabled: boolean;
    readonly liveEnabled: boolean;
    readonly requireIndividualEntryApproval: boolean;
  };
}

export interface SystemHealthPayload {
  readonly overall: "SAFE_PAPER" | "DEGRADED";
  readonly checkedAt: string;
  readonly paperSafetyEnforced: boolean;
  readonly components: readonly {
    readonly id: string;
    readonly label: string;
    readonly status: "HEALTHY" | "READY" | "DEMO" | "NOT_CONFIGURED" | "ERROR";
    readonly detail: string;
  }[];
}

export interface PaperOrder {
  readonly id: string;
  readonly candidate_id: string;
  readonly symbol: string;
  readonly status: "PENDING_SIMULATION" | "PARTIALLY_FILLED" | "FILLED" | "CANCELLED";
  readonly quantity: number;
  readonly entry_price: number;
  readonly stop_price: number;
  readonly target_one: number;
  readonly target_two: number;
  readonly planned_risk: number;
  readonly required_cash: number;
  readonly created_at: string;
  readonly filled_quantity: number;
  readonly average_fill_price: number | null;
  readonly fees: number;
  readonly updated_at: string | null;
}

export interface PaperFill {
  readonly id: string;
  readonly order_id: string;
  readonly symbol: string;
  readonly quantity: number;
  readonly observed_price: number;
  readonly fill_price: number;
  readonly fee: number;
  readonly filled_at: string;
}

export interface PaperPosition {
  readonly id: string;
  readonly order_id: string;
  readonly symbol: string;
  readonly status: "OPEN" | "CLOSED";
  readonly quantity_open: number;
  readonly quantity_closed: number;
  readonly average_entry_price: number;
  readonly current_stop: number;
  readonly target_one: number;
  readonly target_two: number;
  readonly tp1_quantity: number;
  readonly tp1_filled_quantity: number;
  readonly trailing_active: boolean;
  readonly highest_price: number;
  readonly entry_fees: number;
  readonly exit_fees: number;
  readonly realized_pnl: number;
  readonly updated_at: string;
}

export interface PaperExitFill {
  readonly id: string;
  readonly position_id: string;
  readonly symbol: string;
  readonly reason: "TP1" | "TP2" | "INITIAL_STOP" | "TRAILING_STOP";
  readonly quantity: number;
  readonly observed_price: number;
  readonly fill_price: number;
  readonly fee: number;
  readonly filled_at: string;
}

export interface PaperAccountPayload {
  readonly orders: readonly PaperOrder[];
  readonly fills: readonly PaperFill[];
  readonly positions: readonly PaperPosition[];
  readonly exitFills: readonly PaperExitFill[];
  readonly availableCash: number;
  readonly reservedCash: number;
  readonly deployedValue: number;
  readonly reservedRisk: number;
}

export interface ExitReplayResult {
  readonly observation: {
    readonly symbol: string;
    readonly sequence: number;
    readonly observed_at: string;
    readonly price: number;
    readonly available_quantity: number;
    readonly trailing_candidate: number | null;
  };
  readonly outcome: "HOLD" | "TP1_FILL" | "TP2_FILL" | "INITIAL_STOP_FILL" | "TRAILING_STOP_FILL" | "TRAILING_UPDATED";
  readonly message: string;
  readonly position: PaperPosition;
  readonly fill: PaperExitFill | null;
  readonly previous_stop: number;
  readonly replay_complete: boolean;
}

export interface ReplayResult {
  readonly observation: {
    readonly symbol: string;
    readonly sequence: number;
    readonly observed_at: string;
    readonly price: number;
    readonly available_quantity: number;
  };
  readonly outcome: "WAITING_FOR_ENTRY" | "PARTIAL_FILL" | "FILLED" | "NO_ACTIVE_ORDER";
  readonly message: string;
  readonly order: PaperOrder | null;
  readonly fill: PaperFill | null;
  readonly replay_complete: boolean;
}
