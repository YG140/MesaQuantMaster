import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { applyVisualPreferences, readVisualPreferences } from "../../features/preferences/visualPreferences";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const AIContextPanel = lazy(() => import("../AIContextPanel").then(module => ({ default: module.AIContextPanel })));

export function AppShell() {
  const [aiOpen, setAiOpen] = useState(false);
  const openAI = useCallback(() => setAiOpen(true), []);
  const closeAI = useCallback(() => setAiOpen(false), []);
  useEffect(() => applyVisualPreferences(readVisualPreferences()), []);
  return (
    <div className="app-shell">
      <Sidebar onOpenAI={openAI} />
      <div className="app-main">
        <Header onOpenAI={openAI} />
        <main className="content" id="main-content">
          <Outlet context={{ openAI }} />
        </main>
      </div>
      {aiOpen ? <Suspense fallback={null}><AIContextPanel open={aiOpen} onClose={closeAI} /></Suspense> : null}
    </div>
  );
}
