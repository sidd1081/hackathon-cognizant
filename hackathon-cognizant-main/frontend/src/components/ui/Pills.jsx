export function AiBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-900/30 px-2.5 py-0.5 text-xs font-medium text-amber-300 ring-1 ring-inset ring-amber-700/40">
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M11 2 8.9 7.9 3 10l5.9 2.1L11 18l2.1-5.9L19 10l-5.9-2.1L11 2Zm7 11-1 2.8L14 17l2.9 1.1L18 21l1.1-2.9L22 17l-2.9-1.1L18 13Z" />
      </svg>
      AI Generated
    </span>
  );
}

export function DataBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-cyan-900/30 px-2.5 py-0.5 text-xs font-medium text-cyan-300 ring-1 ring-inset ring-cyan-700/40">
      Dataset Records
    </span>
  );
}

const TONES = {
  slate:  "bg-[#21262d] text-[#8b949e] ring-[#30363d]",
  indigo: "bg-violet-900/30 text-violet-300 ring-violet-700/40",
  rose:   "bg-red-900/30 text-red-300 ring-red-700/40",
};

export function StatusPill({ tone = "slate", pulse = false, children }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}>
      {pulse && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function LatencyPill({ ms }) {
  if (ms == null) return null;
  const label = ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
  return (
    <StatusPill tone="slate">
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path strokeLinecap="round" d="M12 7v5l3 2" />
      </svg>
      <span title="Client-measured round-trip time">{label}</span>
    </StatusPill>
  );
}
