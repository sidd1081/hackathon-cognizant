export function SimilarityMeter({ value, label }) {
  const isNA = value === null || value === undefined;
  const v = isNA ? 0 : Math.max(0, Math.min(1, Number(value) || 0));
  const pct = Math.round(v * 100);
  const color = isNA ? "bg-[#30363d]" : v >= 0.6 ? "bg-emerald-500" : v >= 0.4 ? "bg-amber-500" : "bg-red-500";
  const textColor = isNA ? "text-[#6e7681]" : v >= 0.6 ? "text-emerald-400" : v >= 0.4 ? "text-amber-400" : "text-red-400";

  return (
    <div
      className="flex items-center gap-2"
      title={isNA ? "Not available (keyword-only match)" : `${label || "Similarity"} ${v.toFixed(4)}`}
    >
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[#30363d]">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`tabular-nums text-xs font-medium ${textColor}`}>
        {isNA ? "N/A" : v.toFixed(2)}
      </span>
    </div>
  );
}
