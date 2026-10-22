import {
  BarChart3, Bookmark, CheckCircle2, Download, FolderTree, GitCompare, LayoutDashboard, ListChecks,
  LogOut, MessagesSquare, RefreshCw, UserCircle2, Wand2, X,
} from "lucide-react";
import type { ReactNode } from "react";
import { API_URL } from "../lib/api";
import { useStore } from "../lib/store";
import type { Page } from "../lib/store";
import { Spinner } from "./ui";

const NAV: { page: Page; label: string; icon: typeof LayoutDashboard }[] = [
  { page: "overview", label: "Overview", icon: LayoutDashboard },
  { page: "repository", label: "Repository", icon: FolderTree },
  { page: "build", label: "Build context", icon: Wand2 },
  { page: "results", label: "Results", icon: ListChecks },
  { page: "compare", label: "Compare", icon: GitCompare },
  { page: "benchmarks", label: "Benchmarks", icon: BarChart3 },
  { page: "conversation", label: "Conversation", icon: MessagesSquare },
  { page: "export", label: "Export", icon: Download },
  { page: "saved", label: "Saved packages", icon: Bookmark },
];

function StatusPill() {
  const { apiStatus, health } = useStore();
  const map = {
    online: { dot: "bg-emerald-400", text: `API online${health ? ` · v${health.version}` : ""}` },
    connecting: { dot: "bg-amber-400 animate-pulse", text: "Connecting…" },
    offline: { dot: "bg-red-400", text: "API offline" },
  } as const;
  const s = map[apiStatus];
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 text-xs text-zinc-300" title={API_URL}>
      <span className={`size-2 rounded-full ${s.dot}`} aria-hidden />
      {s.text}
    </span>
  );
}

function ConnectionBanners() {
  const { apiStatus, wakeAttempt, connect } = useStore();
  return (
    <>
      {apiStatus === "connecting" && (
        <div className="mb-6 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-200">
          <Spinner label={wakeAttempt > 1 ? `Waking up the server (attempt ${wakeAttempt})… free hosting sleeps when idle, this can take up to a minute.` : "Connecting to the ACWM API…"} />
        </div>
      )}
      {apiStatus === "offline" && (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-200">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>Could not reach the API at <code className="text-red-100">{API_URL}</code>.</span>
            <button className="btn-ghost" onClick={() => void connect()}><RefreshCw className="size-4" /> Retry</button>
          </div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-red-200/80">
            <li>
              Open <a className="underline" href={`${API_URL}/health`} target="_blank" rel="noreferrer noopener">{API_URL}/health</a> in a new tab.
              If it shows <code>{'{"status":"ok"...}'}</code> the server is up — come back and press Retry.
            </li>
            <li>If that page does not load either, the free server may still be starting (wait a minute) or your network blocks <code>onrender.com</code>; try mobile data.</li>
            <li>If that page loads but this app still cannot connect, an ad blocker or privacy extension (e.g. Brave Shields, uBlock) is blocking the request — allow this site or try an incognito window.</li>
          </ul>
        </div>
      )}
    </>
  );
}

/** Minimal frame for the login screen (no navigation until the user has an account). */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-zinc-800 px-5 py-3 md:px-8">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <div className="text-sm font-semibold text-zinc-50">ACWM</div>
            <div className="text-[11px] text-zinc-500">Context Window Manager</div>
          </div>
        </div>
        <StatusPill />
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-5 py-6 md:px-8">
        <ConnectionBanners />
        {children}
      </main>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { page, setPage, busy, error, clearError, notice, clearNotice, repo, pkg, user, logout } = useStore();
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-zinc-800 bg-zinc-950 md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center gap-3 px-5 py-4 md:py-5">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <div className="text-sm font-semibold text-zinc-50">ACWM</div>
            <div className="text-[11px] text-zinc-500">Context Window Manager</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:pb-0" aria-label="Main">
          {NAV.map(({ page: p, label, icon: Icon }) => {
            const dot = (p === "repository" && repo) || (p === "results" && pkg);
            return (
              <button
                key={p}
                onClick={() => setPage(p)}
                aria-current={page === p ? "page" : undefined}
                className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${page === p ? "bg-zinc-800 text-zinc-50" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"}`}
              >
                <Icon className="size-4" aria-hidden />
                {label}
                {dot && <span className="ml-auto size-1.5 rounded-full bg-sky-400" aria-label="has data" />}
              </button>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-950/85 px-5 py-3 backdrop-blur md:px-8">
          <div className="min-w-0 truncate text-xs text-zinc-500">
            {repo ? (
              <>Repository: <span className="text-zinc-300">{repo.repository.root_name}</span> · {repo.repository.indexed_files} files · {repo.repository.total_tokens.toLocaleString()} tokens</>
            ) : (
              "No repository indexed yet"
            )}
          </div>
          <div className="flex items-center gap-3">
            {busy && <Spinner label={busy} />}
            <StatusPill />
            {user && (
              <div className="flex items-center gap-2 border-l border-zinc-800 pl-3">
                <span className="hidden items-center gap-1.5 text-xs text-zinc-300 sm:inline-flex" title={user.email ?? `GitHub: ${user.github_login}`}>
                  <UserCircle2 className="size-4 text-zinc-400" /> {user.display_name}
                </span>
                <button className="btn-ghost px-2.5 py-1 text-xs" onClick={() => logout()} aria-label="Log out">
                  <LogOut className="size-3.5" /> Log out
                </button>
              </div>
            )}
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-5 py-6 md:px-8 md:py-8">
          <ConnectionBanners />
          {notice && (
            <div role="status" className="mb-6 flex items-start justify-between gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-200">
              <span className="flex items-center gap-2"><CheckCircle2 className="size-4" /> {notice}</span>
              <button onClick={clearNotice} aria-label="Dismiss message" className="text-emerald-300 hover:text-emerald-100"><X className="size-4" /></button>
            </div>
          )}
          {error && (
            <div role="alert" className="mb-6 flex items-start justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-200">
              <span>{error}</span>
              <button onClick={clearError} aria-label="Dismiss error" className="text-red-300 hover:text-red-100"><X className="size-4" /></button>
            </div>
          )}
          {children}
        </main>
        <footer className="border-t border-zinc-900 px-5 py-4 text-xs text-zinc-600 md:px-8">
          ACWM selects context with static analysis and heuristics; it does not guarantee correct code changes. Token counts are tiktoken estimates.
        </footer>
      </div>
    </div>
  );
}
