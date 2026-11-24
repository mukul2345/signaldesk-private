import { useCallback, useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { ScanHistoryPayload } from "../domain/types";

export function useScanHistory() {
  const [data, setData] = useState<ScanHistoryPayload | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState<string>();

  const refresh = useCallback(async () => {
    try {
      setData(await dashboardApi.scanHistory());
      setStatus("ready");
      setMessage(undefined);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Scan history could not be loaded");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  return { data, status, message, refresh };
}
