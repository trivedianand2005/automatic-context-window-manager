import { Bookmark, ChevronRight, ExternalLink, GitCompare } from "lucide-react";
import { useMemo, useState } from "react";
import { BudgetMeter } from "../components/BudgetMeter";
import { CodeView } from "../components/CodeView";
import { DependencyGraph, GraphLegend } from "../components/DependencyGraph";
import { Badge, Card, Empty, Notice, PageHeader, ScoreBar, Stat, Tabs } from "../components/ui";
import { fmtInt, fmtPct, lineRangeLabel } from "../lib/format";
import { useStore } from "../lib/store";
import type { ContextItem } from "../lib/types";

const SIGNALS = ["lexical", "filename", "symbol", "dependency", "test", "config"] as const;

function ItemCard({ item, open, onToggle }: { item: ContextItem; open: boolean; onToggle: () => void }) {
  return (
    <li className="card overflow-hidden">
      <button onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-zinc-900">
        <ChevronRight className={`size-4 shrink-0 text-zinc-500 transition-transform ${open ? "rotate-90" : ""}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <code className="truncate text-sm text-zinc-100">{item.path}</code>
            <Badge>{item.kind}</Badge>
            {item.is_partial && <Badge tone="medium">partial</Badge>}
            {item.required && <Badge tone="high">required</Badge>}
            <Badge>{item.file_type}</Badge>
          </div>
          <div className="mt-1 truncate text-xs text-zinc-500">{item.reasons[0] ?? item.selection_note}</div>
        </div>
        <div className="hidden w-40 shrink-0 sm:block"><ScoreBar value={item.combined_score} /></div>
        <div className="w-20 shrink-0 text-right text-xs tabular-nums text-zinc-400">{fmtInt(item.tokens)} tok</div>
      </button>
      {open && (
        <div className="grid gap-5 border-t border-zinc-800 px-4 py-4 lg:grid-cols-5">
          <div className="space-y-4 lg:col-span-2">
            <div>
              <div className="label">Score components</div>
              <div className="space-y-1.5">
                {SIGNALS.map((s) => <ScoreBar key={s} label={s} value={item.scores[s]} />)}
              </div>
            </div>
            <div>
              <div className="label">Why it was selected</div>
              <ul className="list-disc space-y-1 pl-4 text-xs text-zinc-300">
                {item.reasons.map((r) => <li key={r}>{r}</li>)}
                <li className="text-zinc-400">{item.selection_note}</li>
              </ul>
            </div>
            {item.dependency_path.length > 1 && (
              <div>
                <div className="label">Dependency path</div>
                <div className="flex flex-wrap items-center gap-1 text-xs">
                  {item.dependency_path.map((p, i) => (
                    <span key={p} className="flex items-center gap-1">
                      {i > 0 && <ChevronRight className="size-3 text-zinc-600" />}
                      <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-200">{p.split("/").pop()}</code>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="min-w-0 lg:col-span-3">
            <div className="mb-2 text-xs text-zinc-500">
              {lineRangeLabel(item.line_ranges, item.total_lines)} · {fmtInt(item.tokens)} tokens in the package (incl. header) · full file {fmtInt(item.full_file_tokens)} tokens
            </div>
            <CodeView code={item.content} language={item.language} />
          </div>
        </div>
      )}
    </li>
  );
}

type Tab = "selected" | "graph" | "excluded" | "notes";

export function ResultsPage() {
  const { pkg, details, setPage, excludedFindings, toggleFinding, saveCurrentPackage, busy } = useStore();
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("selected");
  const selected = useMemo(() => new Set(pkg?.items.map((i) => i.path) ?? []), [pkg]);

  if (!pkg) {
    return (
      <div>
        <PageHeader title="Results" />
        <Empty title="No context package yet">
          Go to <button className="text-sky-400 underline" onClick={() => setPage("build")}>Build context</button> or run the demo from the Overview.
        </Empty>
      </div>
    );
  }
  const s = pkg.token_stats;
  return (
    <div>
      <PageHeader
        title="Results"
        subtitle={<>Task: <span className="text-zinc-200">{pkg.task}</span></>}
        actions={<>
          <button className="btn-ghost" onClick={() => setPage("compare")}><GitCompare className="size-4" /> Compare with baseline</button>
          <button className="btn-ghost" onClick={() => setPage("export")}>Export package</button>
          {saving ? (
            <form className="flex gap-2" onSubmit={async (e) => {
              e.preventDefault();
              if (await saveCurrentPackage(title)) { setSaving(false); setTitle(""); }
            }}>
              <input autoFocus className="input w-56 py-1.5" placeholder="Name (optional)" maxLength={200}
                aria-label="Package name" value={title} onChange={(e) => setTitle(e.target.value)} />
              <button type="submit" className="btn-primary" disabled={!!busy}>Save</button>
              <button type="button" className="btn-ghost" onClick={() => setSaving(false)}>Cancel</button>
            </form>
          ) : (
            <button className="btn-primary" onClick={() => setSaving(true)}><Bookmark className="size-4" /> Save to my account</button>
          )}
        </>}
      />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Selected items" value={pkg.items.length} hint={`${pkg.items.filter((i) => i.is_partial).length} partial excerpts`} />
        <Stat label="Context tokens" value={fmtInt(s.rendered_context_tokens)} hint={`of ${fmtInt(s.usable_tokens)} usable`} />
        <Stat label="Utilization" value={fmtPct(s.utilization)} hint={`${fmtInt(s.remaining_tokens)} tokens left`} />
        <Stat label="vs whole repo" value={fmtPct(s.reduction_vs_full_repository)} hint={`${fmtInt(s.total_indexed_tokens)} tokens indexed`} />
        <Stat label="Latency" value={`${Math.round(pkg.latency_ms)} ms`} hint={pkg.configuration.mode.split(" (")[0]} />
      </div>
      <Card title="Token budget" className="mb-6">
        <BudgetMeter stats={s} />
        <p className="mt-3 text-xs text-zinc-500">Counts are {s.tokenizer} estimates; the target model's tokenizer may differ, which is why a safety margin is reserved.</p>
      </Card>

      <Tabs<Tab> value={tab} onChange={setTab} items={[
        { value: "selected", label: "Selected context", count: pkg.items.length },
        { value: "graph", label: "Dependency view" },
        { value: "excluded", label: "Excluded", count: pkg.excluded.length },
        { value: "notes", label: "Omissions & warnings", count: pkg.omissions.length + pkg.warnings.length },
      ]} />

      {tab === "selected" && (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
            <span className="text-zinc-500">Task terms:</span>
            {pkg.analysis.keywords.map((k) => <span key={k} className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-300">{k}</span>)}
            {pkg.analysis.wants_tests && <Badge tone="test">tests requested</Badge>}
          </div>
          <ul className="space-y-2">
            {pkg.items.map((item) => (
              <ItemCard key={item.path} item={item} open={open === item.path} onToggle={() => setOpen(open === item.path ? null : item.path)} />
            ))}
          </ul>
          {pkg.research_findings.length > 0 && (
            <Card title="Documentation findings (external, untrusted)" className="mt-6">
              <ul className="space-y-3">
                {pkg.research_findings.map((f, i) => (
                  <li key={f.url} className="flex gap-3">
                    <input type="checkbox" className="mt-1 accent-sky-500" checked={!excludedFindings.has(i)} onChange={() => toggleFinding(i)} aria-label={`Include ${f.title}`} />
                    <div>
                      <a href={f.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-sm text-sky-400 hover:underline">{f.title} <ExternalLink className="size-3" /></a>
                      <p className="text-xs text-zinc-400">{f.snippet}</p>
                      <p className="text-[11px] text-zinc-500">{f.source} · {f.provider_status}</p>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-zinc-500">Unchecked findings are left out of the export.</p>
            </Card>
          )}
        </>
      )}

      {tab === "graph" && (
        <Card title="Selected files (blue outline) and their neighbours">
          {details?.graph ? (
            <>
              <DependencyGraph nodes={details.graph.nodes} edges={details.graph.edges} focus={selected} highlight={selected} />
              <GraphLegend />
            </>
          ) : <p className="text-sm text-zinc-500">Graph data unavailable.</p>}
          <h3 className="mt-5 mb-2 text-sm font-medium text-zinc-200">Relationships among selected files</h3>
          <ul className="space-y-1 text-xs text-zinc-300">
            {pkg.dependencies.map((d, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2"><code>{d.source}</code><ChevronRight className="size-3 text-zinc-600" /><code>{d.target}</code><Badge tone={d.confidence}>{d.relation}</Badge></li>
            ))}
          </ul>
        </Card>
      )}

      {tab === "excluded" && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-zinc-500 uppercase"><tr><th className="py-2 pr-4">Path</th><th className="pr-4 text-right">Score</th><th className="pr-4 text-right">Tokens</th><th>Reason</th></tr></thead>
              <tbody className="divide-y divide-zinc-800/70">
                {pkg.excluded.map((e) => (
                  <tr key={e.path}>
                    <td className="py-1.5 pr-4 font-mono text-xs text-zinc-200">{e.path}</td>
                    <td className="pr-4 text-right tabular-nums text-zinc-400">{e.combined_score.toFixed(3)}</td>
                    <td className="pr-4 text-right tabular-nums text-zinc-400">{fmtInt(e.tokens)}</td>
                    <td className="text-xs text-zinc-400">{e.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {tab === "notes" && (
        <div className="space-y-2">
          {pkg.omissions.map((o) => <Notice key={o}>{o}</Notice>)}
          {pkg.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
          <Notice>{pkg.disclaimer}</Notice>
        </div>
      )}
    </div>
  );
}
