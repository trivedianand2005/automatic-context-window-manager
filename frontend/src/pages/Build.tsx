import { ChevronDown, RotateCcw, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, PageHeader } from "../components/ui";
import { useStore } from "../lib/store";
import type { Compression, Mode, Weights } from "../lib/types";

const MODES: { value: Mode; title: string; text: string }[] = [
  { value: "acwm", title: "Full ACWM", text: "Hybrid ranking, dependency graph, budget optimizer and excerpts." },
  { value: "dependency", title: "BM25 + graph", text: "Keyword search plus import expansion; whole files in rank order." },
  { value: "baseline", title: "Baseline", text: "Keyword (BM25) search only; whole files in rank order." },
];
const COMPRESSION: { value: Compression; label: string; hint: string }[] = [
  { value: "extractive", label: "Extractive", hint: "Verbatim excerpts of large files (no API needed)" },
  { value: "llm", label: "LLM summary", hint: "Uses a configured LLM; falls back to outlines" },
  { value: "none", label: "None", hint: "Whole files only" },
];
const LIBRARY_TASKS = [
  { id: "late-fee-bug", task: "Fix the off-by-one bug in the late fee calculation and add regression tests." },
  { id: "renewal-limit", task: "Allow members to renew a loan at most twice." },
  { id: "isbn-search", task: "Add search by ISBN to the catalog." },
  { id: "overdue-emails", task: "Send overdue reminder emails to members." },
];

const WEIGHT_HELP: Record<keyof Weights, string> = {
  lexical: "BM25 keyword relevance",
  filename: "Task terms in the file path",
  symbol: "Matching function/class names",
  dependency: "Relevance propagated through imports",
  test: "Tests linked to relevant code",
  config: "Configuration files",
  semantic: "Embeddings (unavailable unless installed)",
};

export function BuildPage() {
  const { task, setTask, buildContext, busy, apiStatus, config, benchmarkTasks, details, repo } = useStore();
  const exampleTasks = repo?.repository.root_name === "sample_library_repo" ? LIBRARY_TASKS : benchmarkTasks;
  const [budget, setBudget] = useState(4000);
  const [mode, setMode] = useState<Mode>("acwm");
  const [depth, setDepth] = useState(2);
  const [compression, setCompression] = useState<Compression>("extractive");
  const [research, setResearch] = useState(false);
  const [required, setRequired] = useState<string[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [weights, setWeights] = useState<Weights | null>(null);

  useEffect(() => {
    if (config && !weights) {
      setWeights(config.weights);
      setDepth(config.expansion_depth);
    }
  }, [config, weights]);

  const submit = () =>
    buildContext({
      task, mode, token_budget: budget, expansion_depth: depth, compression,
      include_research: research, required_paths: required, ...(weights ? { weights } : {}),
    });

  const canBuild = apiStatus === "online" && !busy && task.trim().length >= 3;

  return (
    <div>
      <PageHeader title="Build context" subtitle="Describe a coding task. ACWM selects the most useful files and excerpts that fit your token budget." />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <label className="label" htmlFor="task">Coding task</label>
            <textarea id="task" rows={4} className="input resize-y text-[15px]" value={task} onChange={(e) => setTask(e.target.value)} placeholder="e.g. Fix database retry behavior and add regression tests." />
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="text-xs text-zinc-500">Examples:</span>
              {exampleTasks.map((t) => (
                <button key={t.id} onClick={() => setTask(t.task)} className="rounded-full border border-zinc-700 px-2.5 py-0.5 text-xs text-zinc-300 hover:border-sky-500 hover:text-sky-300">
                  {t.id}
                </button>
              ))}
            </div>
          </Card>

          <Card title="Retrieval mode">
            <div className="grid gap-3 md:grid-cols-3" role="radiogroup">
              {MODES.map((m) => (
                <button key={m.value} role="radio" aria-checked={mode === m.value} onClick={() => setMode(m.value)}
                  className={`rounded-lg border p-3 text-left transition-colors ${mode === m.value ? "border-sky-500 bg-sky-500/10" : "border-zinc-800 hover:border-zinc-600"}`}>
                  <div className="text-sm font-medium text-zinc-100">{m.title}</div>
                  <div className="mt-1 text-xs text-zinc-400">{m.text}</div>
                </button>
              ))}
            </div>
          </Card>

          <Card>
            <button onClick={() => setShowAdvanced((v) => !v)} className="flex w-full items-center justify-between text-sm font-semibold text-zinc-200" aria-expanded={showAdvanced}>
              Advanced options <ChevronDown className={`size-4 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
            </button>
            {showAdvanced && (
              <div className="mt-5 space-y-6">
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="label mb-0">Ranking weights (each signal is normalised to 0–1)</span>
                    <button className="btn-ghost px-2 py-1 text-xs" onClick={() => config && setWeights(config.weights)}><RotateCcw className="size-3" /> Reset</button>
                  </div>
                  <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
                    {weights && (Object.keys(WEIGHT_HELP) as (keyof Weights)[]).map((k) => (
                      <label key={k} className="block">
                        <div className="flex justify-between text-xs"><span className="text-zinc-300">{k}</span><span className="tabular-nums text-zinc-400">{weights[k].toFixed(2)}</span></div>
                        <input type="range" min={0} max={1} step={0.05} value={weights[k]} className="w-full accent-sky-500"
                          onChange={(e) => setWeights({ ...weights, [k]: Number(e.target.value) })} />
                        <div className="text-[11px] text-zinc-500">{WEIGHT_HELP[k]}</div>
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="label">Required files (always included, shrunk to an excerpt if needed)</span>
                  <select className="input font-mono" value="" onChange={(e) => e.target.value && setRequired((r) => [...new Set([...r, e.target.value])])}>
                    <option value="">{details ? "Add a file…" : "Index a repository first to pick files"}</option>
                    {(details?.files ?? []).map((f) => <option key={f.path} value={f.path}>{f.path}</option>)}
                  </select>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {required.map((p) => (
                      <button key={p} onClick={() => setRequired((r) => r.filter((x) => x !== p))} className="rounded-md bg-zinc-800 px-2 py-0.5 font-mono text-xs text-zinc-200 hover:bg-red-500/20" title="Remove">
                        {p} ✕
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Budget">
            <label className="label" htmlFor="budget">Total token budget</label>
            <input id="budget" type="number" min={500} max={200000} step={500} className="input tabular-nums" value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
            <input type="range" min={1000} max={20000} step={500} value={Math.min(budget, 20000)} onChange={(e) => setBudget(Number(e.target.value))} className="mt-2 w-full accent-sky-500" aria-label="Token budget slider" />
            <p className="mt-1 text-xs text-zinc-500">
              About {config ? (config.budget.reserved_system_tokens + config.budget.reserved_response_tokens).toLocaleString() : "1,900"} tokens plus a 5% margin are reserved for the system prompt, task and response. Try 4,000 to see the trade-offs.
            </p>
            <label className="label mt-5" htmlFor="depth">Dependency expansion depth: {depth}</label>
            <input id="depth" type="range" min={0} max={5} value={depth} onChange={(e) => setDepth(Number(e.target.value))} className="w-full accent-sky-500" />
          </Card>

          <Card title="Compression">
            <div className="space-y-2" role="radiogroup">
              {COMPRESSION.map((c) => (
                <label key={c.value} className="flex cursor-pointer items-start gap-3 rounded-lg p-1.5 hover:bg-zinc-800/50">
                  <input type="radio" name="compression" checked={compression === c.value} onChange={() => setCompression(c.value)} className="mt-1 accent-sky-500" />
                  <span><span className="block text-sm text-zinc-200">{c.label}</span><span className="text-xs text-zinc-500">{c.hint}</span></span>
                </label>
              ))}
            </div>
            <label className="mt-4 flex cursor-pointer items-start gap-3 border-t border-zinc-800 pt-4">
              <input type="checkbox" checked={research} onChange={(e) => setResearch(e.target.checked)} className="mt-1 accent-sky-500" />
              <span>
                <span className="block text-sm text-zinc-200">Documentation research</span>
                <span className="text-xs text-zinc-500">{config?.providers.tinyfish?.startsWith("real") ? "TinyFish Search API" : "Offline mock results (clearly labelled) — no TinyFish key configured"}</span>
              </span>
            </label>
          </Card>

          <button className="btn-primary w-full py-3 text-base" disabled={!canBuild} onClick={() => void submit()}>
            <Wand2 className="size-5" /> {busy ? "Working…" : "Build context"}
          </button>
          <p className="text-center text-xs text-zinc-500">
            {repo ? <>Using <b className="text-zinc-300">{repo.repository.root_name}</b>. Switch repositories on the Repository page.</> : "The ShopAPI sample repository is indexed automatically if needed."}
          </p>
        </div>
      </div>
    </div>
  );
}
