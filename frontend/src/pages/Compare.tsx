import { CheckCircle2, Circle, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { METHOD_COLOR, METHOD_LABEL, MethodChart } from "../components/MethodChart";
import type { MetricRow } from "../components/MethodChart";
import { Badge, Card, PageHeader } from "../components/ui";
import { fmtInt, fmtPct, fmtScore } from "../lib/format";
import { useStore } from "../lib/store";

export function ComparePage() {
  const { benchmarkTasks, runComparison, comparison, busy, apiStatus, task: currentTask, details } = useStore();
  const [presetId, setPresetId] = useState("jwt-auth");
  const preset = benchmarkTasks.find((t) => t.id === presetId);
  const [task, setTask] = useState("");
  const [budget, setBudget] = useState(4000);
  const [labels, setLabels] = useState<string[]>([]);

  useEffect(() => {
    if (preset) {
      setTask(preset.task);
      setLabels(preset.relevant);
    } else {
      setTask(currentTask);
      setLabels([]);
    }
  }, [preset, currentTask]);

  const rows: MetricRow[] = useMemo(() => {
    if (!comparison) return [];
    const get = (mode: string, key: "coverage" | "precision_at_k" | "recall_at_k" | "mrr") =>
      comparison.methods.find((m) => m.mode === mode)?.[key] ?? null;
    return ([
      ["Coverage", "coverage"],
      [`Precision@${comparison.k}`, "precision_at_k"],
      [`Recall@${comparison.k}`, "recall_at_k"],
      ["MRR", "mrr"],
    ] as const).map(([metric, key]) => ({
      metric, baseline: get("baseline", key), dependency: get("dependency", key), acwm: get("acwm", key),
    }));
  }, [comparison]);
  const relevant = new Set(comparison?.relevant_paths ?? []);
  const hasLabels = relevant.size > 0;

  return (
    <div>
      <PageHeader title="Compare methods" subtitle="Run the BM25 baseline, BM25 + dependency expansion, and full ACWM on the same task with the same token budget." />
      <Card className="mb-6">
        <div className="grid gap-4 md:grid-cols-4">
          <div>
            <label className="label" htmlFor="preset">Benchmark task</label>
            <select id="preset" className="input" value={presetId} onChange={(e) => setPresetId(e.target.value)}>
              {benchmarkTasks.map((t) => <option key={t.id} value={t.id}>{t.id}</option>)}
              <option value="">Custom (no labels)</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="label" htmlFor="cmp-task">Task</label>
            <input id="cmp-task" className="input" value={task} onChange={(e) => setTask(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="cmp-budget">Total token budget</label>
            <input id="cmp-budget" type="number" min={500} step={500} className="input tabular-nums" value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-zinc-500">
            {labels.length ? <>Ground truth: {labels.length} manually labelled relevant files{preset?.rationale ? ` — ${preset.rationale}` : ""}</> : "No ground-truth labels: accuracy metrics will be N/A."}
            {!preset && details && labels.length === 0 && " Pick a benchmark task to get labels."}
          </p>
          <button className="btn-primary" disabled={apiStatus !== "online" || !!busy || task.trim().length < 3} onClick={() => void runComparison(task, budget, labels)}>
            <Play className="size-4" /> Run comparison
          </button>
        </div>
      </Card>

      {comparison && (
        <>
          {hasLabels && (
            <Card title="Accuracy against the labels (higher is better)" className="mb-6">
              <MethodChart rows={rows} />
            </Card>
          )}
          <div className="mb-6 grid gap-4 lg:grid-cols-3">
            {comparison.methods.map((m) => {
              const hits = m.selected.filter((p) => relevant.has(p)).length;
              return (
                <section key={m.mode} className="card overflow-hidden">
                  <div className="h-1" style={{ background: METHOD_COLOR[m.mode] }} />
                  <div className="p-4">
                    <div className="flex items-center gap-2">
                      <span className="inline-block size-2.5 rounded-sm" style={{ background: METHOD_COLOR[m.mode] }} aria-hidden />
                      <h3 className="text-sm font-semibold text-zinc-100">{METHOD_LABEL[m.mode]}</h3>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                      <div><div className="text-lg font-semibold tabular-nums text-zinc-50">{hasLabels ? `${hits}/${relevant.size}` : m.selected.length}</div><div className="text-[11px] text-zinc-500">{hasLabels ? "relevant found" : "files"}</div></div>
                      <div><div className="text-lg font-semibold tabular-nums text-zinc-50">{fmtInt(m.rendered_tokens)}</div><div className="text-[11px] text-zinc-500">tokens</div></div>
                      <div><div className="text-lg font-semibold tabular-nums text-zinc-50">{Math.round(m.latency_ms)}</div><div className="text-[11px] text-zinc-500">ms</div></div>
                    </div>
                    <ul className="mt-4 space-y-1">
                      {m.selected.map((p) => (
                        <li key={p} className="flex items-center gap-2 text-xs">
                          {hasLabels ? (relevant.has(p) ? <CheckCircle2 className="size-3.5 shrink-0 text-emerald-400" aria-label="relevant" /> : <Circle className="size-3.5 shrink-0 text-zinc-600" aria-label="not labelled relevant" />) : null}
                          <code className="truncate text-zinc-300">{p}</code>
                          {m.kinds[p] !== "full" && <Badge>{m.kinds[p]}</Badge>}
                        </li>
                      ))}
                    </ul>
                    {m.missing_relevant.length > 0 && (
                      <div className="mt-3 border-t border-zinc-800 pt-3 text-xs">
                        <div className="mb-1 text-zinc-500">Missed relevant files</div>
                        {m.missing_relevant.map((p) => <div key={p} className="font-mono text-red-300/80">{p}</div>)}
                      </div>
                    )}
                  </div>
                </section>
              );
            })}
          </div>
          <Card title="All metrics">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-zinc-500 uppercase">
                  <tr><th className="py-2 pr-4">Method</th><th className="pr-4 text-right">Coverage</th><th className="pr-4 text-right">Full-file cov.</th><th className="pr-4 text-right">P@{comparison.k}</th><th className="pr-4 text-right">R@{comparison.k}</th><th className="pr-4 text-right">MRR</th><th className="pr-4 text-right">Tokens</th><th className="pr-4 text-right">Utilization</th><th className="text-right">Over budget</th></tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/70 tabular-nums">
                  {comparison.methods.map((m) => (
                    <tr key={m.mode}>
                      <td className="py-2 pr-4 text-zinc-200"><span className="mr-2 inline-block size-2.5 rounded-sm" style={{ background: METHOD_COLOR[m.mode] }} />{METHOD_LABEL[m.mode]}</td>
                      <td className="pr-4 text-right">{fmtScore(m.coverage)}</td>
                      <td className="pr-4 text-right">{fmtScore(m.full_coverage)}</td>
                      <td className="pr-4 text-right">{fmtScore(m.precision_at_k)}</td>
                      <td className="pr-4 text-right">{fmtScore(m.recall_at_k)}</td>
                      <td className="pr-4 text-right">{fmtScore(m.mrr)}</td>
                      <td className="pr-4 text-right">{fmtInt(m.rendered_tokens)} / {fmtInt(m.usable_tokens)}</td>
                      <td className="pr-4 text-right">{fmtPct(m.utilization)}</td>
                      <td className="text-right">{m.budget_violation ? "yes" : "no"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="mt-3 space-y-1 text-xs text-zinc-500">{comparison.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </Card>
        </>
      )}
    </div>
  );
}
