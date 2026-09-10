import { Section } from "./ui/Card.jsx";
import { Badge } from "./ui/Badge.jsx";
import { AiBadge, LatencyPill, StatusPill } from "./ui/Pills.jsx";
import { ConfidenceBadge } from "./ui/Badge.jsx";
import { Alert } from "./ui/Alert.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";
import { Spinner } from "./ui/Spinner.jsx";
import { NOT_DOCUMENTED } from "../lib/constants.js";

function Block({ label, value }) {
  const undocumented = value === NOT_DOCUMENTED;
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-widest text-[#6e7681]">{label}</p>
      <p className={`mt-1 break-words text-sm leading-relaxed ${undocumented ? "italic text-[#6e7681]" : "text-amber-300"}`}>
        {value}
      </p>
    </div>
  );
}

function HeaderActions({ status, data, latencyMs }) {
  if (status === "loading") return <StatusPill tone="indigo" pulse>Analyzing…</StatusPill>;
  if (status === "error") return <StatusPill tone="rose">Failed</StatusPill>;
  if (status === "success" && data) {
    return (
      <div className="flex items-center gap-2">
        <LatencyPill ms={latencyMs} />
        <ConfidenceBadge level={data.confidence} />
      </div>
    );
  }
  return null;
}

export function RcaSummary({ analysis }) {
  const { status, data, error, latencyMs } = analysis;
  const undocumented = data && data.root_cause === NOT_DOCUMENTED;

  return (
    <Section
      label="AI Analysis"
      title="Root Cause Analysis"
      description="Synthesized by LLM from retrieved historical evidence — not a stored fact"
      accent="indigo"
      tag={<AiBadge />}
      actions={<HeaderActions status={status} data={data} latencyMs={latencyMs} />}
    >
      {status === "idle" && (
        <EmptyState title="No analysis yet" message="Enter an incident and click Analyze Incident to generate evidence-grounded RCA." />
      )}

      {status === "loading" && (
        <div className="space-y-2 py-4">
          <div className="flex items-center gap-3 text-sm text-[#8b949e]">
            <Spinner />
            <span>Retrieving evidence → reranking → generating RCA…</span>
          </div>
          <p className="text-xs text-[#6e7681]">Pipeline: vector retrieval → BM25 → RRF → rerank → LLM</p>
        </div>
      )}

      {status === "error" && <Alert variant="error" title="Analysis failed">{error}</Alert>}

      {status === "success" && data && (
        <div className="space-y-5">
          {undocumented && (
            <Alert variant="info">
              No documented root cause found in retrieved evidence — the assistant will not fabricate one.
            </Alert>
          )}

          <Block label="Summary" value={data.summary} />

          <div className="grid gap-5 sm:grid-cols-2">
            <Block label="Root Cause" value={data.root_cause} />
            <Block label="Resolution" value={data.resolution} />
          </div>

          <div className="border-t border-[#30363d] pt-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-[#6e7681]">Supporting Tickets</p>
            {data.supporting_incidents?.length ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {data.supporting_incidents.map((s) => (
                  <Badge key={s.ticket_id} color="indigo">{s.ticket_id}</Badge>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-xs italic text-[#6e7681]">No tickets cited</p>
            )}
            <p className="mt-2 text-xs text-[#6e7681]">
              Confidence = model self-assessment given evidence, not a statistical probability
            </p>
          </div>
        </div>
      )}
    </Section>
  );
}
