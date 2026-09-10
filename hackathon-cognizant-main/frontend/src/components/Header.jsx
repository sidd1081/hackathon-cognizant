export function Header({ right }) {
  return (
    <header className="border-b border-[#30363d] bg-[#161b22]">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-600 text-xs font-bold text-white shadow-sm">
            RCA
          </div>
          <div>
            <h1 className="text-base font-bold text-[#e6edf3]">AI Incident RCA Assistant</h1>
            <p className="text-xs text-[#6e7681]">evidence-grounded root cause analysis · zero hallucination</p>
          </div>
        </div>
        {right ? <div className="shrink-0">{right}</div> : null}
      </div>
    </header>
  );
}
