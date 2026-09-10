import { Section } from "./ui/Card.jsx";
import { Badge } from "./ui/Badge.jsx";
import { useEvaluation } from "../hooks/useEvaluation.js";

const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const dec = (v) => (v == null ? "—" : Number(v).toFixed(2));
const ms  = (v) => (v == null ? "—" : `${Math.round(v)}ms`);

function toneFor(v, { lowerBetter = false } = {}) {
  if (v == null) return "slate";
  const good = lowerBetter ? v <= 0.05 : v >= 0.8;
  const ok   = lowerBetter ? v <= 0.2  : v >= 0.5;
  return good ? "emerald" : ok ? "amber" : "rose";
}

const METER_COLOR = { emerald: "bg-emerald-500", amber: "bg-amber-500", rose: "bg-red-500", slate: "bg-[#30363d]" };
const VALUE_COLOR = { emerald: "text-emerald-300", amber: "text-amber-300", rose: "text-red-300", slate: "text-[#8b949e]" };

function Meter({ value, tone }) {
  const v = Math.max(0, Math.min(1, Number(value) || 0));
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[#30363d]">
      <div className={`h-full rounded-full transition-all ${METER_COLOR[tone] || METER_COLOR.slate}`} style={{ width: `${Math.round(v * 100)}%` }} />
    </div>
  );
}

function StatTile({ label, value, tone = "slate", meter = null, hint }) {
  return (
    <div className="min-w-0 rounded-lg border border-[#30363d] bg-[#161b22] p-3">
      <p className="text-xs font-medium leading-tight text-[#6e7681]">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${VALUE_COLOR[tone]}`}>{value}</p>
      {meter != null ? <Meter value={meter} tone={tone} /> : null}
      {hint ? <p className="mt-1 text-[10px] text-[#6e7681]">{hint}</p> : null}
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg border border-[#30363d] p-3">
          <div className="h-2 w-20 rounded bg-[#21262d]" />
          <div className="mt-2 h-6 w-14 rounded bg-[#21262d]" />
          <div className="mt-2 h-1.5 w-full rounded-full bg-[#21262d]" />
        </div>
      ))}
    </div>
  );
}

export function EvaluationPanel() {
  const { status, data, error } = useEvaluation();

  const generated = data?.generated_at && new Date(data.generated_at).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });

  return (
    <Section
      label="Benchmark"
      title="System Evaluation"
      description="Offline benchmark across labeled test set — measured through real pipeline: retrieval quality, answer grounding, latency"
      accent="slate"
      tag={<Badge color="slate">Latest Run</Badge>}
    >
      {status === "loading" && <SkeletonGrid />}

      {status === "error" && (
        <p className="text-xs text-[#6e7681]">
          No evaluation results yet. Run{" "}
          <code className="rounded bg-[#21262d] px-1 py-0.5 text-[#8b949e]">
            uv run python -m scripts.evaluate
          </code>{" "}
          to populate this panel.
        </p>
      )}

      {status === "success" && data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <StatTile label="Recall@5" value={pct(data.recall_at_5)} tone={toneFor(data.recall_at_5)} meter={data.recall_at_5} hint="correct ticket retrieved" />
            <StatTile label="MRR" value={dec(data.mrr)} tone={toneFor(data.mrr)} meter={data.mrr} hint="mean reciprocal rank" />
            <StatTile label="Root Cause Correctness" value={pct(data.root_cause_correctness)} tone={toneFor(data.root_cause_correctness)} meter={data.root_cause_correctness} hint="vs gold answer" />
            <StatTile label="Hallucination Rate" value={pct(data.hallucination_rate)} tone={toneFor(data.hallucination_rate, { lowerBetter: true })} hint="lower is better" />
            <StatTile label="Evidence Support" value={pct(data.evidence_support_rate)} tone={toneFor(data.evidence_support_rate)} meter={data.evidence_support_rate} hint="citations grounded" />
            <StatTile label="Correct Abstention" value={pct(data.abstention_correct_rate)} tone={toneFor(data.abstention_correct_rate)} meter={data.abstention_correct_rate} hint="on out-of-domain" />
            <StatTile label="Retrieval Latency" value={ms(data.retrieval_latency_ms)} hint="mean, FAISS + rerank" />
            <StatTile label="Embedding Latency" value={ms(data.embedding_latency_ms)} hint="mean, local MiniLM" />
          </div>
          <p className="mt-3 text-xs text-[#6e7681]">
            {data.num_cases} cases
            {data.groq_model ? ` · model: ${data.groq_model}` : ""}
            {generated ? ` · generated: ${generated}` : ""}
          </p>
        </>
      )}
    </Section>
  );
}
