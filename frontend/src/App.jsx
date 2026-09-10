import { useState } from "react";
import { Header } from "./components/Header.jsx";
import { HealthIndicator } from "./components/HealthIndicator.jsx";
import { OfflineBanner } from "./components/OfflineBanner.jsx";
import { DatasetPanel } from "./components/DatasetPanel.jsx";
import { IncidentForm } from "./components/IncidentForm.jsx";
import { RcaSummary } from "./components/RcaSummary.jsx";
import { SimilarIncidents } from "./components/SimilarIncidents.jsx";
import { ChatbotPanel } from "./components/ChatbotPanel.jsx";
import { EvaluationPanel } from "./components/EvaluationPanel.jsx";
import { AuthPage } from "./components/AuthPage.jsx";
import { Tabs } from "./components/ui/Tabs.jsx";
import { useBackendHealth } from "./hooks/useBackendHealth.js";
import { useAuth } from "./hooks/useAuth.js";
import { analyzeIncident, uploadDataset } from "./services/api.js";

const IDLE = { status: "idle", data: null, error: null, latencyMs: null };

const TABS = [
  { id: "analyze", label: "Analyze" },
  { id: "evaluation", label: "Evaluation" },
];

export default function App() {
  const [incidentText, setIncidentText] = useState("");
  const [analysis, setAnalysis] = useState(IDLE);
  const [dataset, setDataset] = useState(IDLE);
  const [tab, setTab] = useState("analyze");
  const backend = useBackendHealth();
  const auth = useAuth();

  const handleAnalyze = async () => {
    if (!incidentText.trim()) return;
    setAnalysis({ status: "loading", data: null, error: null, latencyMs: null });
    const startedAt = performance.now();
    try {
      const data = await analyzeIncident(incidentText.trim());
      const latencyMs = Math.round(performance.now() - startedAt);
      setAnalysis({ status: "success", data, error: null, latencyMs });
    } catch (err) {
      setAnalysis({ status: "error", data: null, error: err.message, latencyMs: null });
    }
  };

  const handleUpload = async (file) => {
    setDataset({ status: "uploading", data: null, error: null });
    try {
      const data = await uploadDataset(file);
      setDataset({ status: "success", data, error: null });
    } catch (err) {
      setDataset({ status: "error", data: null, error: err.message });
    }
  };

  const analyzing = analysis.status === "loading";

  // Gate the dashboard behind authentication.
  if (!auth.isAuthenticated) {
    return <AuthPage onLogin={auth.login} onSignup={auth.signup} />;
  }

  return (
    <div className="min-h-screen bg-[#0d1117]">
      <Header
        right={
          <div className="flex items-center gap-3">
            <HealthIndicator status={backend.status} />
            <span className="hidden font-mono text-xs text-green-800 sm:inline">
              {auth.user?.name || auth.user?.email}
            </span>
            <button
              type="button"
              onClick={auth.logout}
              className="rounded-md border border-[#30363d] px-3 py-1.5 text-xs font-medium text-[#8b949e] transition hover:border-[#6e7681] hover:text-[#e6edf3]"
            >
              Logout
            </button>
          </div>
        }
      />

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:py-8">
        {backend.status === "offline" && (
          <OfflineBanner onRetry={backend.recheck} />
        )}

        <div className="mb-6 sm:max-w-xs">
          <Tabs tabs={TABS} active={tab} onChange={setTab} />
        </div>

        {tab === "analyze" ? (
          <div className="space-y-6">
            {/* Top row: upload dataset (left) + ask query (right) */}
            <div className="grid gap-6 md:grid-cols-2">
              <div className="min-w-0">
                <DatasetPanel state={dataset} onUpload={handleUpload} />
              </div>
              <div className="min-w-0">
                <IncidentForm
                  value={incidentText}
                  onChange={setIncidentText}
                  onAnalyze={handleAnalyze}
                  loading={analyzing}
                />
              </div>
            </div>

            {/* Response (full width) */}
            <RcaSummary analysis={analysis} />

            {/* Assistant chat available after the RCA */}
            <ChatbotPanel analysis={analysis} incidentText={incidentText} />

            {/* Retrievals (full width) */}
            <SimilarIncidents analysis={analysis} />
          </div>
        ) : (
          <EvaluationPanel />
        )}
      </main>
    </div>
  );
}
