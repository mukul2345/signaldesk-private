import { useCallback, useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import { accountMetrics, candidates, marketIndices } from "../data/demo";
import type { DashboardPayload } from "../domain/types";

const fallback: DashboardPayload = {
  as_of: new Date(0).toISOString(),
  source: "frontend_demo_fallback",
  market_status: "Market closed",
  next_scan: "Monday · 15:40 IST",
  indices: marketIndices,
  candidates,
  account: accountMetrics,
  policy: { capitalCeiling: 50_000, riskPerTrade: 250, displayLimit: 50 },
  pendingOrders: [],
  scanCoverage: { eligibleCount: 5, evaluatedCount: 5, excludedCount: 0, missingSymbols: [] }
};

export function useDashboard() {
  const [data, setData] = useState<DashboardPayload>(fallback);
  const [connection, setConnection] = useState<"loading" | "connected" | "fallback">("loading");

  const refresh = useCallback(() => {
    const controller = new AbortController();
    dashboardApi.load()
      .then(payload => {
        if (!controller.signal.aborted) {
          setData(payload);
          setConnection("connected");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setConnection("fallback");
      });
    return controller;
  }, []);

  useEffect(() => {
    const controller = refresh();
    return () => controller.abort();
  }, [refresh]);

  return { data, connection, refresh };
}
