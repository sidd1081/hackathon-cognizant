const COLORS = {
  slate:   "bg-[#21262d] text-[#8b949e] ring-[#30363d]",
  indigo:  "bg-violet-900/30 text-violet-300 ring-violet-700/40",
  emerald: "bg-emerald-900/30 text-emerald-300 ring-emerald-700/40",
  amber:   "bg-amber-900/30 text-amber-300 ring-amber-700/40",
  rose:    "bg-red-900/30 text-red-300 ring-red-700/40",
};

export function Badge({ color = "slate", className = "", children }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${COLORS[color]} ${className}`}>
      {children}
    </span>
  );
}

const CONFIDENCE = {
  high:   ["emerald", "High"],
  medium: ["amber",   "Medium"],
  low:    ["rose",    "Low"],
};

export function ConfidenceBadge({ level }) {
  const key = String(level || "").toLowerCase();
  const [color, label] = CONFIDENCE[key] || ["slate", level || "Unknown"];
  return <Badge color={color}>Confidence: {label}</Badge>;
}
