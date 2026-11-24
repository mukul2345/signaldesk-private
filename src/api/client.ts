import { dashboardConfig } from "../config/dashboard";
import { accessToken, cloudMode } from "../auth/supabaseAuth";
import type { DailyBriefPayload, DashboardPayload, ExitReplayResult, MarketDataWarmupStatus, PaperAccountPayload, PaperOrder, PerformanceValidationPayload, PortfolioAnalysisPayload, PublicSettingsPayload, ReplayResult, ScanHistoryPayload, ScanRun, SchedulerStatus, SystemHealthPayload, UniversePromotionStatus } from "../domain/types";

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const cloudPath = cloudMode ? ({ "/dashboard": "/cloud/dashboard", "/paper/orders": "/cloud/paper/orders", "/paper/account": "/cloud/paper/account", "/portfolio/analysis": "/cloud/portfolio/analysis", "/mvp/daily-brief": "/cloud/mvp/daily-brief", "/validation/performance": "/cloud/validation/performance" } as Record<string, string>)[path] ?? path : path;
  const token = cloudMode ? accessToken() : null;
  const response = await fetch(`${dashboardConfig.apiBaseUrl}${cloudPath}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init?.headers }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new ApiError(body?.detail ?? "SignalDesk request failed", response.status);
  }
  return response.json() as Promise<T>;
}

export const dashboardApi = {
  load: () => request<DashboardPayload>("/dashboard"),
  createPaperOrder: (candidateId: string, idempotencyKey: string) =>
    request<PaperOrder>("/paper/orders", {
      method: "POST",
      body: JSON.stringify({ candidate_id: candidateId, idempotency_key: idempotencyKey })
    }),
  paperAccount: () => request<PaperAccountPayload>("/paper/account"),
  dailyBrief: () => request<DailyBriefPayload>("/mvp/daily-brief"),
  runDailyAnalysis: () => request<DailyBriefPayload>("/mvp/run", { method: "POST" }),
  portfolioAnalysis: () => request<PortfolioAnalysisPayload>("/portfolio/analysis"),
  performanceValidation: () => request<PerformanceValidationPayload>("/validation/performance"),
  advanceReplay: (orderId: string) =>
    request<ReplayResult>(`/paper/orders/${orderId}/replay/advance`, { method: "POST" }),
  cancelPaperOrder: (orderId: string) =>
    request<PaperOrder>(`/paper/orders/${orderId}/cancel`, { method: "POST" }),
  advanceExitReplay: (positionId: string) =>
    request<ExitReplayResult>(`/paper/positions/${positionId}/replay/advance`, { method: "POST" }),
  scanHistory: () => request<ScanHistoryPayload>("/scans/history"),
  archiveCurrentScan: () => request<ScanRun>("/scans/archive", { method: "POST" }),
  schedulerStatus: () => request<SchedulerStatus>("/scheduler/status"),
  marketDataWarmup: () => request<MarketDataWarmupStatus>("/market-data/warmup"),
  advanceMarketDataWarmup: () => request<MarketDataWarmupStatus>("/market-data/warmup/advance", { method: "POST" }),
  universePromotion: () => request<UniversePromotionStatus>("/market-data/promotion"),
  refreshPromotionEvidence: () => request<UniversePromotionStatus>("/market-data/promotion/refresh", { method: "POST" }),
  prepareUniversePromotion: (candidateVersion: string) => request<UniversePromotionStatus>("/market-data/promotion/prepare", {
    method: "POST",
    body: JSON.stringify({ candidateVersion })
  }),
  publicSettings: () => request<PublicSettingsPayload>("/settings/public"),
  systemHealth: () => request<SystemHealthPayload>("/system/health")
};
