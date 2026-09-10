export function Tabs({ tabs, active, onChange, className = "" }) {
  return (
    <div role="tablist" className={`flex w-full gap-1 rounded-lg border border-[#30363d] bg-[#161b22] p-1 ${className}`}>
      {tabs.map((t) => {
        const isActive = t.id === active;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(t.id)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${
              isActive
                ? "bg-violet-600 text-white shadow-sm"
                : "text-[#8b949e] hover:text-[#e6edf3]"
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
