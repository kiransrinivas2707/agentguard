import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { AuthPage } from "./components/AuthPage";
import { Sidebar } from "./components/Sidebar";
import { FolderPage } from "./pages/FolderPage";
import { HistoryPage } from "./pages/HistoryPage";
import { InboxPage } from "./pages/InboxPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TrashPage } from "./pages/TrashPage";
import type { Folder, Stats, User } from "./types";
import { useHashRoute } from "./useHashRoute";

const TITLES: Record<string, string> = {
  inbox: "Inbox",
  review: "Needs Review",
  search: "Search",
  history: "History",
  settings: "Settings",
  trash: "Trash",
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [route, navigate] = useHashRoute();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toast, setToast] = useState<{ message: string; kind: "ok" | "error" } | null>(null);
  const toastTimer = useRef<number | null>(null);

  const notify = useCallback((message: string, kind: "ok" | "error" = "ok") => {
    setToast({ message, kind });
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 4500);
  }, []);

  const refreshMeta = useCallback(async () => {
    try {
      const [nextFolders, nextStats] = await Promise.all([api.folders(), api.stats()]);
      setFolders(nextFolders);
      setStats(nextStats);
    } catch {
      // A failed metadata refresh should not blank the current page.
    }
  }, []);

  useEffect(() => {
    api
      .me()
      .then((me) => setUser(me))
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    if (user) void refreshMeta();
  }, [user, refreshMeta]);

  useEffect(() => {
    if (!user || !stats || stats.inbox === 0) return;
    const timer = window.setInterval(() => void refreshMeta(), 2500);
    return () => window.clearInterval(timer);
  }, [user, stats?.inbox, refreshMeta]);

  useEffect(() => {
    const page = route.split("/")[0];
    const title = page === "folder" ? "Folder" : TITLES[page] ?? "File Organizer";
    document.title = `${title} · AI File Organizer`;
  }, [route]);

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setFolders([]);
      setStats(null);
      navigate("inbox");
    }
  };

  if (checking) {
    return (
      <div className="splash" role="status">
        <span className="brand-mark" aria-hidden="true">
          ◈
        </span>
        <p>Loading your files…</p>
      </div>
    );
  }

  if (!user) {
    return <AuthPage onAuth={(me) => setUser(me)} />;
  }

  const page = route.split("/")[0];
  const folderId = page === "folder" ? route.split("/")[1] : "";
  const inboxId = folders.find((folder) => folder.path.length === 1 && folder.name === "Inbox")?.id ?? null;
  const activeFolder = folders.find((folder) => folder.id === folderId);
  const title = page === "folder" ? activeFolder?.path.join(" / ") ?? "Folder" : TITLES[page] ?? "File Organizer";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className={sidebarOpen ? "sidebar-wrap open" : "sidebar-wrap"}>
        <Sidebar
          user={user}
          stats={stats}
          folders={folders}
          route={route}
          onNavigate={navigate}
          onLogout={logout}
          onClose={() => setSidebarOpen(false)}
        />
      </div>
      {sidebarOpen && <button type="button" className="scrim" aria-label="Close menu" onClick={() => setSidebarOpen(false)} />}

      <main id="main" className="main">
        <header className="topbar">
          <button
            type="button"
            className="btn ghost menu-button"
            aria-label="Open navigation"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen(true)}
          >
            ☰
          </button>
          <div>
            <h1>{title}</h1>
            <p className="muted small">
              {stats ? `${stats.total} file${stats.total === 1 ? "" : "s"} · ${stats.needs_review} awaiting review` : "Loading…"}
            </p>
          </div>
        </header>

        {page === "inbox" && <InboxPage inboxId={inboxId} onChanged={refreshMeta} notify={notify} />}
        {page === "review" && <ReviewPage folders={folders} onChanged={refreshMeta} notify={notify} />}
        {page === "folder" && folderId && (
          <FolderPage
            folderId={folderId}
            folders={folders}
            onChanged={refreshMeta}
            notify={notify}
            onNavigate={navigate}
          />
        )}
        {page === "search" && <SearchPage notify={notify} />}
        {page === "history" && <HistoryPage onChanged={refreshMeta} notify={notify} />}
        {page === "settings" && <SettingsPage onChanged={refreshMeta} notify={notify} />}
        {page === "trash" && <TrashPage onChanged={refreshMeta} notify={notify} />}
      </main>

      {toast && (
        <div className={toast.kind === "error" ? "toast error" : "toast"} role="status" aria-live="polite">
          {toast.message}
        </div>
      )}
    </div>
  );
}
