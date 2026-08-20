import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { useAuth } from "../../features/auth/useAuth";
import { applyVisualPreferences, readVisualPreferences } from "../../features/preferences/visualPreferences";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const AIContextPanel = lazy(() => import("../AIContextPanel").then(module => ({ default: module.AIContextPanel })));
const GlobalSearchDialog = lazy(() => import("../search/GlobalSearchDialog").then(module => ({ default: module.GlobalSearchDialog })));

export function AppShell() {
  const { token } = useAuth();
  const [aiOpen, setAiOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const openAI = useCallback(() => setAiOpen(true), []);
  const closeAI = useCallback(() => setAiOpen(false), []);
  const openSearch = useCallback(() => setSearchOpen(true), []);
  const closeSearch = useCallback(() => setSearchOpen(false), []);
  useEffect(() => applyVisualPreferences(readVisualPreferences()), []);
  return (
    <div className="app-shell">
      <Sidebar onOpenAI={openAI} />
      <div className="app-main">
        <Header onOpenSearch={openSearch} />
        <main className="content" id="main-content">
          <Outlet context={{ openAI }} />
        </main>
      </div>
      {aiOpen ? <Suspense fallback={null}><AIContextPanel open={aiOpen} onClose={closeAI} /></Suspense> : null}
      {searchOpen && token ? (
        <Suspense fallback={null}>
          <GlobalSearchDialog open={searchOpen} onClose={closeSearch} token={token} />
        </Suspense>
      ) : null}
    </div>
  );
}
