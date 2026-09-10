import { useRef, useState } from "react";
import { Section } from "./ui/Card.jsx";
import { Button } from "./ui/Button.jsx";
import { Alert } from "./ui/Alert.jsx";
import { Badge } from "./ui/Badge.jsx";
import { MAX_UPLOAD_BYTES, MAX_UPLOAD_MB } from "../lib/constants.js";

export function DatasetPanel({ state, onUpload }) {
  const inputRef = useRef(null);
  const [fileName, setFileName] = useState("");
  const [sizeError, setSizeError] = useState("");
  const busy = state.status === "uploading";

  const handleChange = (e) => {
    const file = e.target.files?.[0];
    setFileName(file ? file.name : "");
    if (file && file.size > MAX_UPLOAD_BYTES) {
      const fileMb = (file.size / (1024 * 1024)).toFixed(1);
      setSizeError(`"${file.name}" is ${fileMb} MB — exceeds ${MAX_UPLOAD_MB} MB limit. Split into smaller batches.`);
    } else {
      setSizeError("");
    }
  };

  const handleSubmit = () => {
    const file = inputRef.current?.files?.[0];
    if (file && !sizeError) onUpload(file);
  };

  return (
    <Section label="Dataset" title="Historical Incident Data" description="Upload a CSV to clean, embed, and rebuild the search index.">
      <div className="space-y-4">
        <div className="flex flex-col gap-3">
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            onChange={handleChange}
            className="block w-full text-xs text-[#8b949e] file:mr-3 file:rounded-md file:border file:border-[#30363d] file:bg-[#21262d] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-[#e6edf3] hover:file:bg-[#30363d]"
          />
          <Button onClick={handleSubmit} loading={busy} disabled={!fileName || busy || Boolean(sizeError)}>
            Upload & Index
          </Button>
        </div>

        {sizeError && <Alert variant="error" title="File too large">{sizeError}</Alert>}

        {state.status === "idle" && !sizeError && (
          <p className="text-xs text-[#6e7681]">
            Required:{" "}
            <code className="rounded bg-[#21262d] px-1 py-0.5 text-[#8b949e]">
              ticket_id, project, summary, description, root_cause, resolution_status, resolution_notes
            </code>
            <br />Max: {MAX_UPLOAD_MB} MB
          </p>
        )}

        {busy && <p className="text-xs text-amber-400">Validating → cleaning → embedding → indexing…</p>}

        {state.status === "error" && <Alert variant="error" title="Upload failed">{state.error}</Alert>}

        {state.status === "success" && state.data && (
          <div className="rounded-lg border border-emerald-700/30 bg-emerald-900/10 p-3">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-emerald-300">
              <Badge color="emerald">Indexed</Badge>
              <span><strong className="tabular-nums">{state.data.records}</strong> incidents</span>
              <span className="text-[#6e7681]">·</span>
              <span>{state.data.duplicates_removed} dupes removed</span>
              <span className="text-[#6e7681]">·</span>
              <span>dim: {state.data.embedding_dimension}</span>
              <span className="text-[#6e7681]">·</span>
              <span>index: {state.data.index_status}</span>
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}
