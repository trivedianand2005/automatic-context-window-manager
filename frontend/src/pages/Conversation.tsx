import { CheckCircle2, Play, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceDot, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Badge, Card, Empty, Notice, PageHeader, Spinner, Stat } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { fmtInt, fmtPct } from "../lib/format";
import type { ConversationResults, ConversationStatus, ConversationStrategy, ConversationSummary } from "../lib/types";

/** Fixed strategy -> color mapping (never by rank). */
export const STRATEGY_COLOR: Record<ConversationStrategy, string> = {
  full: "#a1a1aa",
  truncation: "#d95926",
  acwm: "#3987e5",
};
export const STRATEGY_LABEL: Record<ConversationStrategy, string> = {
  full: "No management",
  truncation: "Naive truncation",
  acwm: "ACWM + manager",
};
const STRATEGIES: ConversationStrategy[] = ["full", "truncation", "acwm"];
const MANAGER_COLOR = "#199e70";
const TOOLTIP = {
  contentStyle: { background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#e4e4e7" },
  itemStyle: { color: "#d4d4d8" },
};
const AXIS_TICK = { fill: "#a1a1aa", fontSize: 12 };
const usd = (v: number) => `$${v.toFixed(4)}`;

function TokensChart({ results }: { results: ConversationResults }) {
  const rows = Array.from({ length: results.turns }, (_, i) => {
    const turn = i + 1;
    const row: Record<string, number | null> = { turn };
    for (const s of STRATEGIES) row[s] = results.per_turn[s].find((t) => t.turn === turn)?.context_tokens ?? null;
    return row;
  });
  const compactions = results.per_turn.acwm.filter((t) => t.compaction === "llm");
  const full = results.summary.find((s) => s.strategy === "full");
  const lastFull = results.per_turn.full[results.per_turn.full.length - 1];
  return (
    <div style={{ height: 340 }} role="img" aria-label="Tokens sent to the main model per turn for each strategy; exact numbers are in the tables below">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 16, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid vertical={false} stroke="#27272a" />
          <XAxis dataKey="turn" tick={AXIS_TICK} axisLine={{ stroke: "#3f3f46" }} tickLine={false}
            label={{ value: "Conversation turn", position: "insideBottom", offset: -2, fill: "#71717a", fontSize: 12 }} height={36} />
          <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} width={52} />
          <Tooltip {...TOOLTIP} formatter={(v, name) => [typeof v === "number" ? fmtInt(v) : "—", name]} labelFormatter={(t) => `Turn ${t}`} />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(value: string) => <span style={{ color: "#d4d4d8" }}>{value}</span>} />
          <ReferenceLine y={results.budget_tokens} stroke="#ef4444" strokeDasharray="5 4"
            label={{ value: `Budget ${fmtInt(results.budget_tokens)}`, position: "insideTopRight", fill: "#fca5a5", fontSize: 11 }} />
          {STRATEGIES.map((s) => (
            <Line key={s} type="monotone" dataKey={s} name={STRATEGY_LABEL[s]} stroke={STRATEGY_COLOR[s]}
              strokeWidth={s === "full" ? 3 : 2} strokeDasharray={s === "full" ? "4 4" : undefined}
              dot={false} connectNulls={false} isAnimationActive={false} />
          ))}
          {compactions.map((t) => (
            <ReferenceDot key={t.turn} x={t.turn} y={t.context_tokens} r={5} fill={MANAGER_COLOR} stroke="#09090b" />
          ))}
          {full?.overflow_turn && lastFull && (
            <ReferenceDot x={lastFull.turn} y={lastFull.context_tokens} r={6} fill="#ef4444" stroke="#09090b"
              label={{ value: `overflow · turn ${full.overflow_turn}`, position: "top", fill: "#fca5a5", fontSize: 11 }} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function CostChart({ summary }: { summary: ConversationSummary[] }) {
  const rows = summary.map((s) => ({ name: STRATEGY_LABEL[s.strategy], strategy: s.strategy, main: s.main_cost_usd, manager: s.manager_cost_usd }));
  return (
    <div style={{ height: 260 }} role="img" aria-label="Estimated total cost per strategy, split into main model and manager model">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#27272a" />
          <XAxis dataKey="name" tick={AXIS_TICK} axisLine={{ stroke: "#3f3f46" }} tickLine={false} />
          <YAxis tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} width={52} tickFormatter={(v: number) => `$${v.toFixed(2)}`} />
          <Tooltip {...TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v, name) => [typeof v === "number" ? usd(v) : "—", name]} />
          <Bar dataKey="main" name="Main model" stackId="cost" isAnimationActive={false} maxBarSize={64}>
            {rows.map((r) => <Cell key={r.strategy} fill={STRATEGY_COLOR[r.strategy]} />)}
          </Bar>
          <Bar dataKey="manager" name="Manager model" stackId="cost" fill={MANAGER_COLOR} radius={[4, 4, 0, 0]} isAnimationActive={false} maxBarSize={64} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RecallChart({ summary }: { summary: ConversationSummary[] }) {
  const rows = summary.map((s) => ({ name: STRATEGY_LABEL[s.strategy], strategy: s.strategy, recall: s.recall_accuracy }));
  return (
    <div style={{ height: 260 }} role="img" aria-label="Share of recall questions answered correctly per strategy">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#27272a" />
          <XAxis dataKey="name" tick={AXIS_TICK} axisLine={{ stroke: "#3f3f46" }} tickLine={false} />
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => fmtPct(v)} />
          <Tooltip {...TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v) => [typeof v === "number" ? fmtPct(v) : "—", "Recall"]} />
          <Bar dataKey="recall" name="Recall" radius={[4, 4, 0, 0]} isAnimationActive={false} maxBarSize={64}>
            {rows.map((r) => <Cell key={r.strategy} fill={STRATEGY_COLOR[r.strategy]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatusCard({ status }: { status: ConversationStatus | null }) {
  if (!status) return <Card title="Models"><Spinner label="Loading model status…" /></Card>;
  const ctx = status.context;
  return (
    <Card title="Models">
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-zinc-500 uppercase">Manager (context only)</dt>
          <dd className="mt-0.5 text-zinc-200">{status.manager.model} <span className="text-zinc-500">via {status.manager.backend}</span></dd>
          <dd className="text-xs text-zinc-400">{status.manager.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 uppercase">Main model (answers)</dt>
          <dd className="mt-0.5 text-zinc-200">{status.main_model.model} <span className="text-zinc-500">via {status.main_model.backend}</span></dd>
          <dd className="text-xs text-zinc-400">{status.main_model.status}</dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-zinc-500">
        Compacts at {fmtPct(ctx.compact_threshold)} of the budget down to {fmtPct(ctx.compact_target)} · keeps the last {ctx.keep_recent_turns} turns verbatim ·
        {" "}{ctx.cooldown_turns}-turn cooldown · settings from <code>config.yaml</code>
      </p>
    </Card>
  );
}

export function ConversationPage() {
  const [status, setStatus] = useState<ConversationStatus | null>(null);
  const [budget, setBudget] = useState(4000);
  const [mode, setMode] = useState<"dry-run" | "live">("dry-run");
  const [results, setResults] = useState<ConversationResults | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.conversationStatus()
      .then((s) => { setStatus(s); setBudget(s.default_budget_tokens); })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, []);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setResults(await api.runConversationBenchmark(mode, budget));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const summary = results?.summary ?? [];
  const by = Object.fromEntries(summary.map((s) => [s.strategy, s])) as Partial<Record<ConversationStrategy, ConversationSummary>>;
  const acwm = by.acwm;
  const trunc = by.truncation;
  const dry = results?.mode.startsWith("dry-run");
  const compactions = results?.per_turn.acwm.filter((t) => t.compaction) ?? [];
  const questions = results?.answers.acwm ?? [];

  return (
    <div>
      <PageHeader
        title="Conversation manager"
        subtitle="One 80-turn conversation with facts planted early, run through three strategies at the same token budget: no management, naive truncation, and ACWM's hybrid manager (heuristics every turn, a small manager model past the threshold)."
        actions={
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="label" htmlFor="conv-budget">Token budget</label>
              <input id="conv-budget" type="number" min={1000} max={16000} step={500} className="input w-28 tabular-nums"
                value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
            </div>
            <div>
              <label className="label" htmlFor="conv-mode">Mode</label>
              <select id="conv-mode" className="input w-56" value={mode} onChange={(e) => setMode(e.target.value as "dry-run" | "live")}>
                <option value="dry-run">Dry run (mock models)</option>
                <option value="live" disabled={!status?.live_available}>
                  Live{status && !status.live_available ? " (disabled on this server)" : ""}
                </option>
              </select>
            </div>
            <button className="btn-primary" disabled={running || budget < 1000 || budget > 16000} onClick={() => void run()}>
              <Play className="size-4" /> Run benchmark
            </button>
          </div>
        }
      />

      <div className="space-y-6">
        <StatusCard status={status} />
        {error && <Notice tone="warn">{error}</Notice>}
        {running && <Card><Spinner label={mode === "live" ? "Running live: real model calls, this can take a few minutes…" : "Running the dry-run benchmark…"} /></Card>}

        {!results && !running ? (
          <Empty title="No conversation benchmark yet">
            Click <b>Run benchmark</b>. The dry run uses mock models, needs no API keys and finishes in a few seconds.
          </Empty>
        ) : results && (
          <>
            {dry && (
              <Notice>
                Dry run: the main model is a mock that echoes its context, and the manager is a mock built on the same heuristics as the fallback.
                &ldquo;Recall&rdquo; here means the planted fact was still in the context sent to the model. Costs are estimates from token counts and the prices in <code>config.yaml</code>.
              </Notice>
            )}
            {acwm && trunc && (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label="ACWM recall" value={fmtPct(acwm.recall_accuracy)} hint={`vs ${fmtPct(trunc.recall_accuracy)} with naive truncation`} />
                <Stat label="ACWM cost" value={usd(acwm.total_cost_usd)} hint={`vs ${usd(trunc.total_cost_usd)} with naive truncation`} />
                <Stat label="Main-model input saved" value={fmtPct(1 - acwm.main_input_tokens / Math.max(1, trunc.main_input_tokens))} hint={`${fmtInt(acwm.main_input_tokens)} vs ${fmtInt(trunc.main_input_tokens)}`} />
                <Stat label="Manager compactions" value={fmtInt(acwm.manager_calls)} hint={`${fmtInt(acwm.manager_input_tokens + acwm.manager_output_tokens)} manager tokens · ${usd(acwm.manager_cost_usd)}`} />
              </div>
            )}

            <Card title={`Context size per turn · budget ${fmtInt(results.budget_tokens)} tokens · ${results.mode.startsWith("dry-run") ? "dry run" : "live"}`}>
              <TokensChart results={results} />
              <p className="mt-2 text-xs text-zinc-500">
                <span className="mr-1 inline-block size-2.5 rounded-full align-middle" style={{ background: MANAGER_COLOR }} /> manager compaction
                <span className="mr-1 ml-4 inline-block size-2.5 rounded-full bg-red-500 align-middle" /> no-management context overflows the budget
              </p>
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card title={`Estimated total cost over ${results.turns} turns`}><CostChart summary={summary} /></Card>
              <Card title={`Recall of early facts (${results.recall_questions} questions)`}><RecallChart summary={summary} /></Card>
            </div>

            <Card title="Summary">
              <div className="overflow-x-auto">
                <table className="w-full text-sm tabular-nums">
                  <thead className="text-left text-xs text-zinc-500 uppercase">
                    <tr><th className="py-2 pr-4">Strategy</th><th className="pr-4 text-right">Turns</th><th className="pr-4 text-right">Main tokens</th><th className="pr-4 text-right">Manager tokens</th><th className="pr-4 text-right">Manager latency</th><th className="pr-4 text-right">Cost</th><th className="text-right">Recall</th></tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/70">
                    {summary.map((s) => (
                      <tr key={s.strategy}>
                        <td className="py-2 pr-4 text-zinc-200"><span className="mr-2 inline-block size-2.5 rounded-sm" style={{ background: STRATEGY_COLOR[s.strategy] }} />{STRATEGY_LABEL[s.strategy]}</td>
                        <td className="pr-4 text-right">{s.turns_completed}{s.overflow_turn ? <span className="text-red-300"> (overflow at {s.overflow_turn})</span> : null}</td>
                        <td className="pr-4 text-right">{fmtInt(s.main_input_tokens + s.main_output_tokens)}</td>
                        <td className="pr-4 text-right">{fmtInt(s.manager_input_tokens + s.manager_output_tokens)}</td>
                        <td className="pr-4 text-right">{s.manager_calls ? `${fmtInt(s.manager_latency_ms)} ms` : "—"}</td>
                        <td className="pr-4 text-right">{usd(s.total_cost_usd)}</td>
                        <td className="text-right">{s.recall_correct}/{s.recall_total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="ACWM compaction events">
              {compactions.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm tabular-nums">
                    <thead className="text-left text-xs text-zinc-500 uppercase">
                      <tr><th className="py-2 pr-4">Turn</th><th className="pr-4">Mode</th><th className="pr-4 text-right">Context after</th><th className="pr-4 text-right">Usage</th><th className="pr-4 text-right">Manager in / out</th><th className="pr-4 text-right">Latency</th><th className="text-right">Manager cost</th></tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/70">
                      {compactions.map((t) => (
                        <tr key={t.turn}>
                          <td className="py-2 pr-4 text-zinc-200">{t.turn}</td>
                          <td className="pr-4"><Badge tone={t.compaction === "llm" ? "high" : "medium"}>{t.compaction === "llm" ? "manager LLM" : "heuristic"}</Badge></td>
                          <td className="pr-4 text-right">{fmtInt(t.context_tokens)}</td>
                          <td className="pr-4 text-right">{fmtPct(t.usage_ratio)}</td>
                          <td className="pr-4 text-right">{fmtInt(t.manager_input_tokens)} / {fmtInt(t.manager_output_tokens)}</td>
                          <td className="pr-4 text-right">{fmtInt(t.manager_latency_ms)} ms</td>
                          <td className="text-right">{usd(t.manager_cost_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-zinc-500">The context never reached the compaction threshold at this budget.</p>
              )}
            </Card>

            <Card title="Recall questions">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-zinc-500 uppercase">
                    <tr><th className="py-2 pr-4">Turn</th><th className="pr-4">Question</th><th className="pr-4">Expected</th><th className="pr-4 text-right">Fact from turn</th>{STRATEGIES.map((s) => <th key={s} className="pr-4 text-center">{STRATEGY_LABEL[s]}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/70">
                    {questions.map((q) => (
                      <tr key={q.question_id}>
                        <td className="py-2 pr-4 tabular-nums text-zinc-400">{q.turn}</td>
                        <td className="max-w-sm pr-4 text-zinc-300">{q.question}</td>
                        <td className="pr-4 text-zinc-400">{q.expected_keywords.join(" + ")}</td>
                        <td className="pr-4 text-right tabular-nums text-zinc-400">{q.fact_turn}</td>
                        {STRATEGIES.map((s) => {
                          const a = results.answers[s].find((x) => x.question_id === q.question_id);
                          return (
                            <td key={s} className="pr-4 text-center">
                              {a?.correct
                                ? <CheckCircle2 className="inline size-4 text-emerald-400" aria-label="correct" />
                                : <XCircle className="inline size-4 text-zinc-600" aria-label={a ? "wrong" : "not reached (overflow)"} />}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
