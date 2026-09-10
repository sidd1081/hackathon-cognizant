import { API_BASE_URL } from "../services/api.js";
import { Button } from "./ui/Button.jsx";

export function OfflineBanner({ onRetry, checking = false }) {
  const target = API_BASE_URL || "backend via dev proxy (/api)";
  return (
    <div className="mb-6 flex flex-col gap-3 rounded-lg border border-red-700/50 bg-red-900/20 px-4 py-3 text-xs text-red-300 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="font-semibold">Backend Offline</p>
        <p className="mt-0.5 text-red-400">
          Could not reach {target}. Start with{" "}
          <code className="rounded bg-red-950/50 px-1 py-0.5 text-red-300">
            uv run uvicorn app.main:app --reload
          </code>
        </p>
      </div>
      <Button variant="secondary" onClick={onRetry} loading={checking} className="shrink-0">
        Retry
      </Button>
    </div>
  );
}
