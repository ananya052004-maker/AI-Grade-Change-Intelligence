import { useState } from "react";
import "./styles.css";
import { AdvisoryBanner } from "./components/AdvisoryBanner";
import { LiveTransitionView } from "./views/LiveTransitionView";
import { CorrelationExplorer } from "./views/CorrelationExplorer";
import { FutureStatePanel } from "./views/FutureStatePanel";
import { StabilizationImpactView } from "./views/StabilizationImpactView";
import { SuggestionLogView } from "./views/SuggestionLogView";

export default function App() {
  const [tab, setTab] = useState("live");

  const TABS = [
    { id: "live", label: "Live Transition", el: <LiveTransitionView onNavigateToLog={() => setTab("log")} /> },
    { id: "corr", label: "Correlation Explorer", el: <CorrelationExplorer /> },
    { id: "future", label: "Future State", el: <FutureStatePanel /> },
    { id: "stab", label: "Stabilization Impact", el: <StabilizationImpactView /> },
    { id: "log", label: "Suggestion Log", el: <SuggestionLogView /> },
  ];

  return (
    <div className="app">
      <h1 style={{ fontSize: 20, marginBottom: 4 }}>Grade Change Intelligence</h1>
      <p className="muted" style={{ marginTop: 0, marginBottom: 12 }}>
        Advisory intelligence layer over Honeywell QCS/MD-MPC grade-change control (PRD-GCI-001).
      </p>
      <AdvisoryBanner />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      {TABS.find((t) => t.id === tab)?.el}
    </div>
  );
}
