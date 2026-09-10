import { useCallback, useEffect, useState } from "react";
import { getEvaluation } from "../services/api.js";

/**
 * Fetch the latest offline evaluation metrics once on mount (and on demand).
 * status: "loading" | "success" | "error".
 * When no results file exists yet the backend returns 404 -> status "error".
 */
export function useEvaluation() {
  const [state, setState] = useState({
    status: "loading",
    data: null,
    error: null,
  });

  const load = useCallback(async () => {
    setState({ status: "loading", data: null, error: null });
    try {
      const data = await getEvaluation();
      setState({ status: "success", data, error: null });
    } catch (err) {
      setState({ status: "error", data: null, error: err.message });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}
