export function Card({ className = "", children }) {
  return (
    <div className={`rounded-lg border border-[#30363d] bg-[#161b22] shadow-sm ${className}`}>
      {children}
    </div>
  );
}

const ACCENTS = {
  indigo: "border-l-2 border-l-violet-500",
  slate:  "border-l-2 border-l-cyan-600",
};

const LABEL_TONES = {
  indigo: "text-violet-400",
  slate:  "text-cyan-400",
};

export function Section({ label, title, description, actions, tag, accent, className = "", children }) {
  const accentClass = accent ? (ACCENTS[accent] || "") : "";
  const labelTone   = accent ? (LABEL_TONES[accent] || "text-slate-400") : "text-slate-400";
  return (
    <Card className={`${accentClass} ${className}`}>
      <div className="flex items-start justify-between gap-4 border-b border-[#30363d] px-5 py-4 sm:px-6">
        <div className="min-w-0">
          {label && (
            <p className={`text-xs font-semibold uppercase tracking-widest ${labelTone}`}>{label}</p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-bold text-[#e6edf3]">{title}</h2>
            {tag}
          </div>
          {description && (
            <p className="mt-0.5 text-xs text-[#6e7681]">{description}</p>
          )}
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      <div className="px-5 py-5 sm:px-6">{children}</div>
    </Card>
  );
}
