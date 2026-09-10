import { useLayoutEffect, useRef, useState } from "react";

export function Expandable({ text, clampClass, className = "", emptyText = "—" }) {
  const ref = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setOverflowing(el.scrollHeight > el.clientHeight + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, clampClass]);

  return (
    <div className="min-w-0">
      <p ref={ref} className={`break-words ${expanded ? "" : clampClass} ${className}`}>
        {text || emptyText}
      </p>
      {overflowing && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-0.5 text-xs font-medium text-violet-400 hover:text-violet-300"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}
