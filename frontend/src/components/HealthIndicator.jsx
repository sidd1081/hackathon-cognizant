// health indicator card
const MAP = {
  checking: ["bg-amber-400 animate-pulse", "text-[#8b949e]", "Checking…"],
  online:   ["bg-emerald-400", "text-emerald-400", "Online"],
  offline:  ["bg-red-400", "text-red-400", "Offline"],
};

export function HealthIndicator({ status }) {
  const [dot, text, label] = MAP[status] || MAP.checking;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      <span className={`font-medium ${text}`}>{label}</span>
    </span>
  );
}
