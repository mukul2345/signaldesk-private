import { useCallback, useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { MarketDataWarmupStatus, PublicSettingsPayload, SchedulerStatus, SystemHealthPayload, UniversePromotionStatus } from "../domain/types";

export function useSystemStatus() {
  const [settings, setSettings] = useState<PublicSettingsPayload | null>(null);
  const [health, setHealth] = useState<SystemHealthPayload | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [warmup, setWarmup] = useState<MarketDataWarmupStatus | null>(null);
  const [warmupBusy, setWarmupBusy] = useState(false);
  const [warmupError, setWarmupError] = useState<string | null>(null);
  const [promotion, setPromotion] = useState<UniversePromotionStatus | null>(null);
  const [promotionBusy, setPromotionBusy] = useState(false);
  const [promotionError, setPromotionError] = useState<string | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  const refresh = useCallback(async () => {
    try {
      const [nextSettings, nextHealth, nextScheduler, nextWarmup, nextPromotion] = await Promise.all([
        dashboardApi.publicSettings(),
        dashboardApi.systemHealth(),
        dashboardApi.schedulerStatus(),
        dashboardApi.marketDataWarmup(),
        dashboardApi.universePromotion()
      ]);
      setSettings(nextSettings);
      setHealth(nextHealth);
      setScheduler(nextScheduler);
      setWarmup(nextWarmup);
      setPromotion(nextPromotion);
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, []);

  const refreshPromotion = useCallback(async () => {
    setPromotionBusy(true);
    setPromotionError(null);
    try {
      setPromotion(await dashboardApi.refreshPromotionEvidence());
    } catch (error) {
      setPromotionError(error instanceof Error ? error.message : "Evidence refresh failed");
    } finally {
      setPromotionBusy(false);
    }
  }, []);

  const preparePromotion = useCallback(async () => {
    if (!promotion?.candidateVersion) return;
    setPromotionBusy(true);
    setPromotionError(null);
    try {
      setPromotion(await dashboardApi.prepareUniversePromotion(promotion.candidateVersion));
    } catch (error) {
      setPromotionError(error instanceof Error ? error.message : "Promotion preparation failed");
    } finally {
      setPromotionBusy(false);
    }
  }, [promotion?.candidateVersion]);

  const advanceWarmup = useCallback(async () => {
    setWarmupBusy(true);
    setWarmupError(null);
    try {
      setWarmup(await dashboardApi.advanceMarketDataWarmup());
    } catch (error) {
      setWarmupError(error instanceof Error ? error.message : "Warm-up batch failed");
    } finally {
      setWarmupBusy(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  return { settings, health, scheduler, warmup, warmupBusy, warmupError, advanceWarmup, promotion, promotionBusy, promotionError, refreshPromotion, preparePromotion, status, refresh };
}
