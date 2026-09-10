import { useCallback, useEffect, useState } from "react";
import { getHealth } from "../services/api.js";

/**
 * Poll the backend /api/health endpoint once on mount (and on demand).
 * status: "checking" | "online" | "offline".
 */
export function useBackendHealth() {
  const [status, setStatus] = useState("checking");

  const check = useCallback(async () => {
    setStatus("checking");
    try {
      const res = await getHealth();
      setStatus(res && res.status === "ok" ? "online" : "offline");
    } catch {
      setStatus("offline");
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  return { status, recheck: check };
}
