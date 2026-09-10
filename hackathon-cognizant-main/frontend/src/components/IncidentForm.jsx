import { useState } from "react";
import { Section } from "./ui/Card.jsx";
import { Button } from "./ui/Button.jsx";
import { EXAMPLE_INCIDENTS } from "../lib/constants.js";

export function IncidentForm({ value, onChange, onAnalyze, loading }) {
  const isEmpty = !value.trim();
  const [exampleIndex, setExampleIndex] = useState(0);

  const useNextExample = () => {
    onChange(EXAMPLE_INCIDENTS[exampleIndex % EXAMPLE_INCIDENTS.length]);
    setExampleIndex((i) => (i + 1) % EXAMPLE_INCIDENTS.length);
  };

  return (
    <Section
      label="New Incident"
      title="Describe the Incident"
      actions={
        <button type="button" onClick={useNextExample}
          className="text-xs font-medium text-amber-400 hover:text-amber-300">
          Use example
        </button>
      }
    >
      <div className="space-y-3">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={8}
          placeholder="e.g. Kafka consumers stopped processing messages after a broker restart…"
          className="w-full resize-y rounded-lg border border-[#30363d] bg-[#0d1117] p-3 text-sm text-[#e6edf3] placeholder:text-[#6e7681] focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
        />
        <div className="flex items-center justify-between">
          <p className="tabular-nums text-xs text-[#6e7681]">{value.trim().length} chars</p>
          <Button onClick={onAnalyze} loading={loading} disabled={isEmpty || loading}>
            Analyze Incident
          </Button>
        </div>
      </div>
    </Section>
  );
}
