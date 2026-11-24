import { useCallback, useEffect, useState } from "react";
import { dashboardApi } from "../api/client";
import type { PaperAccountPayload } from "../domain/types";

const emptyAccount: PaperAccountPayload = {
  orders: [],
  fills: [],
  positions: [],
  exitFills: [],
  availableCash: 0,
  reservedCash: 0,
  deployedValue: 0,
  reservedRisk: 0
};

export function usePaperAccount(enabled: boolean) {
  const [account, setAccount] = useState<PaperAccountPayload>(emptyAccount);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    try {
      setAccount(await dashboardApi.paperAccount());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Paper account unavailable");
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => { void refresh(); }, [refresh]);
  return { account, loading, error, refresh };
}
