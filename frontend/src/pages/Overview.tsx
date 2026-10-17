import { ArrowRight, FileSearch, GitBranch, Layers, PackageCheck, Play, Scale, ScanSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmtInt } from "../lib/format";
import { EXAMPLE_TASK, useStore } from "../lib/store";
import type { RunInfo } from "../lib/types";
import { Card, Stat } from "../components/ui";

const STEPS = [
  { icon: ScanSearch, title: "Index safely", text: "Skips secrets, binaries, venvs and ignored files. Never executes code." },
  { icon: FileSearch, title: "Parse & search", text: "Python AST symbols plus BM25 over files and functions." },
  { icon: GitBranch, title: "Follow imports", text: "A dependency graph pulls in the code a change really touches." },
  { icon: Scale, title: "Fit the budget", text: "Greedy optimizer with verbatim excerpts for large files." },
  { icon: PackageCheck, title: "Explain & export", text: "Every choice has reasons; export Markdown, JSON or TXT." },
];

export function OverviewPage() {
  const { apiStatus, health, repo, pkg, buildContext, setPage, setTask, busy } = useStore();
  const [runs, setRuns] = useState<RunInfo[]>([]);

  useEffect(() => {
    if (apiStatus === "online") api.runs().then(setRuns).catch(() => setRuns([]));
  }, [apiStatus, pkg]);

  const runDemo = async () => {
    setTask(EXAMPLE_TASK);
    await buildContext({ task: EXAMPLE_TASK, token_budget: 4000 });
  };

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-900 via-zinc-900 to-sky-950/40 px-6 py-10 md:px-10">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-300">
            <Layers className="size-3.5" /> Context selection for AI coding agents
          </span>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-50 md:text-4xl">
            Give your coding agent the <span className="text-sky-400">right</span> code — not all of it.
          </h1>
          <p className="mt-4 text-base text-zinc-300">
            ACWM picks the files and functions a task needs, follows their dependencies, and packs them into a fixed token budget — explaining every decision along the way.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button className="btn-primary" disabled={apiStatus !== "online" || !!busy} onClick={runDemo}>
              <Play className="size-4" /> Run the demo
            </button>
            <button className="btn-ghost" onClick={() => setPage("build")}>
              Build your own <ArrowRight className="size-4" />
            </button>
          </div>
          <p className="mt-3 text-xs text-zinc-500">
            The demo indexes the bundled sample FastAPI repository and selects context for: “{EXAMPLE_TASK}” at a 4,000-token budget.
          </p>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="API" value={apiStatus === "online" ? "Online" : apiStatus === "connecting" ? "…" : "Offline"} hint={health ? `version ${health.version}` : undefined} />
        <Stat label="Indexed files" value={repo ? repo.repository.indexed_files : "—"} hint={repo?.repository.root_name} />
        <Stat label="Repository tokens" value={repo ? fmtInt(repo.repository.total_tokens) : "—"} hint="tiktoken estimate" />
        <Stat label="Last package" value={pkg ? `${pkg.items.length} items` : "—"} hint={pkg ? `${fmtInt(pkg.token_stats.rendered_context_tokens)} tokens` : undefined} />
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-zinc-300">How it works</h2>
        <ol className="grid gap-3 md:grid-cols-5">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="card p-4">
              <div className="flex items-center gap-2 text-sky-400">
                <Icon className="size-4" /> <span className="text-xs text-zinc-500">Step {i + 1}</span>
              </div>
              <div className="mt-2 text-sm font-medium text-zinc-100">{title}</div>
              <p className="mt-1 text-xs text-zinc-400">{text}</p>
            </li>
          ))}
        </ol>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Your recent runs">
          {runs.length ? (
            <ul className="divide-y divide-zinc-800">
              {runs.map((r) => (
                <li key={r.timestamp} className="py-2.5 text-sm">
                  <div className="truncate text-zinc-200">{r.task}</div>
                  <div className="mt-0.5 text-xs text-zinc-500">
                    {r.mode} · {r.selected_files} files · {fmtInt(r.rendered_tokens)}/{fmtInt(r.usable_tokens)} tokens · {r.latency_ms} ms
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-500">No runs yet in this browser session.</p>
          )}
        </Card>
        <Card title="Optional providers">
          <ul className="space-y-2 text-sm">
            {Object.entries(health?.providers ?? {}).map(([k, v]) => (
              <li key={k} className="flex gap-3">
                <span className="w-32 shrink-0 text-zinc-400">{k}</span>
                <span className="text-zinc-300">{v}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-zinc-500">The core workflow needs no API keys. Mocked or unavailable providers are always labelled.</p>
        </Card>
      </div>
    </div>
  );
}
