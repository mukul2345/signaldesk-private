import { useCallback, useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { SchedulerStatus } from "../domain/types";

export function useSchedulerStatus() {
  const [data, setData] = useState<SchedulerStatus | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await dashboardApi.schedulerStatus());
    } catch {
      setData(null);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  return { data, refresh };
}
