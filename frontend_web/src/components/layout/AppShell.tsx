import { useCallback, useState } from "react";
import { Outlet } from "react-router-dom";
import { AIContextPanel } from "../AIContextPanel";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const [aiOpen, setAiOpen] = useState(false);
  const openAI = useCallback(() => setAiOpen(true), []);
  const closeAI = useCallback(() => setAiOpen(false), []);
  return (
    <div className="app-shell">
      <Sidebar onOpenAI={openAI} />
      <div className="app-main">
        <Header onOpenAI={openAI} />
        <main className="content" id="main-content">
          <Outlet />
        </main>
      </div>
      <AIContextPanel open={aiOpen} onClose={closeAI} />
    </div>
  );
}
