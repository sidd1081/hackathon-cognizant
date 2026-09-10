import { useState } from "react";
import { Badge } from "./ui/Badge.jsx";
import { SimilarityMeter } from "./ui/SimilarityMeter.jsx";
import { Expandable } from "./ui/Expandable.jsx";
import { NOT_DOCUMENTED } from "../lib/constants.js";

const MATCH_COLORS = {
  semantic: "indigo",
  keyword: "amber",
  "semantic+keyword": "emerald",
};

const MATCH_LABELS = {
  semantic: "Semantic",
  keyword: "Keyword",
  "semantic+keyword": "Semantic + Keyword",
};

function Field({ label, value }) {
  const muted = !value || value === NOT_DOCUMENTED;
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-widest text-[#6e7681]">{label}</p>
      <Expandable
        text={value}
        clampClass="line-clamp-5"
        className={`mt-0.5 text-xs ${muted ? "italic text-[#6e7681]" : "text-[#c9d1d9]"}`}
      />
    </div>
  );
}

function MetricRow({ label, value, muted = false }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-[#6e7681]">{label}</span>
      <span className={`font-mono text-xs ${muted ? "italic text-[#6e7681]" : "font-medium text-[#8b949e]"}`}>
        {value}
      </span>
    </div>
  );
}

function fmt(v, decimals = 4) {
  if (v === null || v === undefined) return null;
  return Number(v).toFixed(decimals);
}

function RetrievalDetails({ incident }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 border-t border-[#30363d] pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 text-xs font-medium text-[#6e7681] transition hover:text-[#8b949e]"
      >
        <svg
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
        </svg>
        Retrieval Details
      </button>

      {open && (
        <div className="mt-2 divide-y divide-[#30363d] rounded-lg border border-[#30363d] bg-[#0d1117] px-3 py-2">
          <div className="pb-1.5">
            <MetricRow label="FAISS Cosine Similarity" value={fmt(incident.similarity) ?? "N/A"} muted={incident.similarity == null} />
            <MetricRow label="BM25 Score" value={fmt(incident.bm25_score) ?? "N/A"} muted={incident.bm25_score == null} />
            <MetricRow label="RRF Score" value={fmt(incident.rrf_score, 6) ?? "N/A"} muted={incident.rrf_score == null} />
          </div>
          <div className="pt-1.5">
            <MetricRow label="FAISS Rank" value={incident.faiss_rank != null ? `#${incident.faiss_rank}` : "N/A"} muted={incident.faiss_rank == null} />
            <MetricRow label="BM25 Rank" value={incident.bm25_rank != null ? `#${incident.bm25_rank}` : "N/A"} muted={incident.bm25_rank == null} />
            <MetricRow label="Final Rank (Hybrid)" value={incident.hybrid_rank ? `#${incident.hybrid_rank}` : "—"} />
          </div>
        </div>
      )}
    </div>
  );
}

export function IncidentCard({ incident, cited = false }) {
  const matchType = incident.match_type || "semantic";
  const matchColor = MATCH_COLORS[matchType] || "slate";
  const matchLabel = MATCH_LABELS[matchType] || matchType;

  return (
    <div className="overflow-hidden rounded-lg border border-[#30363d] bg-[#161b22] p-4 transition hover:border-[#6e7681]">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-bold text-cyan-400">{incident.ticket_id}</span>
          {cited && <Badge color="indigo">Cited by AI</Badge>}
          <Badge color={matchColor}>{matchLabel}</Badge>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {incident.hybrid_rank > 0 && (
            <span
              className="inline-flex items-center rounded-full bg-[#21262d] px-2 py-0.5 text-xs font-semibold text-[#8b949e] ring-1 ring-inset ring-[#30363d]"
              title="Hybrid rank (RRF fusion of FAISS + BM25)"
            >
              #{incident.hybrid_rank}
            </span>
          )}
          <div className="flex items-center gap-2">
            <span className="hidden text-xs text-[#6e7681] sm:inline">Similarity</span>
            <SimilarityMeter value={incident.similarity} label="Semantic Similarity" />
          </div>
        </div>
      </div>

      <Expandable
        text={incident.description}
        clampClass="line-clamp-3"
        className="mt-2 text-xs text-[#8b949e]"
      />

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Root Cause" value={incident.root_cause} />
        <Field label="Resolution" value={incident.resolution} />
      </div>

      <RetrievalDetails incident={incident} />
    </div>
  );
}
