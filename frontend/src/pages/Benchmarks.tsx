import { Play } from "lucide-react";
import { useState } from "react";
import { METHOD_COLOR, METHOD_LABEL, METHOD_ORDER, MethodChart } from "../components/MethodChart";
import { Card, Empty, Notice, PageHeader } from "../components/ui";
import { fmtInt, fmtScore } from "../lib/format";
import { useStore } from "../lib/store";

export function BenchmarksPage() {
  const { runBenchmarks, benchmark, busy, apiStatus, benchmarkTasks } = useStore();
  const [budget, setBudget] = useState(4000);
  const k = benchmark?.k ?? 5;
  const agg = benchmark?.aggregate;
  const rows = agg
    ? ([["Coverage", "coverage"], [`Precision@${k}`, `precision@${k}`], [`Recall@${k}`, `recall@${k}`], ["MRR", "mrr"]] as const).map(
        ([metric, key]) => ({ metric, baseline: agg.baseline[key] ?? null, dependency: agg.dependency[key] ?? null, acwm: agg.acwm[key] ?? null }),
      )
    : [];

  return (
    <div>
      <PageHeader
        title="Benchmarks"
        subtitle={`Runs all ${benchmarkTasks.length || 5} manually labelled tasks on the sample repository with every method at the same budget. Numbers are measured live.`}
        actions={
          <div className="flex items-end gap-2">
            <div>
              <label className="label" htmlFor="bench-budget">Total budget</label>
              <input id="bench-budget" type="number" min={1000} step={500} className="input w-32 tabular-nums" value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
            </div>
            <button className="btn-primary" disabled={apiStatus !== "online" || !!busy} onClick={() => void runBenchmarks(budget)}><Play className="size-4" /> Run benchmarks</button>
          </div>
        }
      />
      {!benchmark ? (
        <Empty title="No benchmark run yet">Choose a budget and click <b>Run benchmarks</b>. It takes a few seconds.</Empty>
      ) : (
        <div className="space-y-6">
          <Card title={`Mean scores over ${benchmark.tasks.length} tasks · budget ${fmtInt(benchmark.token_budget)} · ${benchmark.tokenizer}`}>
            <MethodChart rows={rows} />
          </Card>
          <Card title="Aggregate table">
            <div className="overflow-x-auto">
              <table className="w-full text-sm tabular-nums">
                <thead className="text-left text-xs text-zinc-500 uppercase">
                  <tr><th className="py-2 pr-4">Method</th><th className="pr-4 text-right">Coverage</th><th className="pr-4 text-right">P@{k}</th><th className="pr-4 text-right">R@{k}</th><th className="pr-4 text-right">MRR</th><th className="pr-4 text-right">Mean tokens</th><th className="pr-4 text-right">Violations</th><th className="text-right">Latency</th></tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/70">
                  {METHOD_ORDER.map((m) => (
                    <tr key={m}>
                      <td className="py-2 pr-4 text-zinc-200"><span className="mr-2 inline-block size-2.5 rounded-sm" style={{ background: METHOD_COLOR[m] }} />{METHOD_LABEL[m]}</td>
                      <td className="pr-4 text-right">{fmtScore(benchmark.aggregate[m].coverage, 3)}</td>
                      <td className="pr-4 text-right">{fmtScore(benchmark.aggregate[m][`precision@${k}`], 3)}</td>
                      <td className="pr-4 text-right">{fmtScore(benchmark.aggregate[m][`recall@${k}`], 3)}</td>
                      <td className="pr-4 text-right">{fmtScore(benchmark.aggregate[m].mrr, 3)}</td>
                      <td className="pr-4 text-right">{fmtInt(benchmark.aggregate[m].mean_rendered_tokens)}</td>
                      <td className="pr-4 text-right">{fmtInt(benchmark.aggregate[m].budget_violations)}</td>
                      <td className="text-right">{fmtScore(benchmark.aggregate[m].mean_latency_ms, 1)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="Coverage per task">
            <div className="overflow-x-auto">
              <table className="w-full text-sm tabular-nums">
                <thead className="text-left text-xs text-zinc-500 uppercase">
                  <tr><th className="py-2 pr-4">Task</th>{METHOD_ORDER.map((m) => <th key={m} className="pr-4 text-right">{METHOD_LABEL[m]}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/70">
                  {benchmark.tasks.map((t) => (
                    <tr key={t.task}>
                      <td className="max-w-md py-2 pr-4 text-zinc-300">{t.task}</td>
                      {METHOD_ORDER.map((m) => <td key={m} className="pr-4 text-right">{fmtScore(t.methods.find((x) => x.mode === m)?.coverage, 2)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Notice tone="warn">
            Small benchmark: 5 tasks on one ~10k-token sample repository, and ACWM's heuristics were tuned on it. Treat these numbers as a demonstration, not a general claim.
          </Notice>
        </div>
      )}
    </div>
  );
}
