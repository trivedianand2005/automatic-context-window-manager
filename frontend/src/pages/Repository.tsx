import { FolderSearch } from "lucide-react";
import { useMemo, useState } from "react";
import { DependencyGraph, GraphLegend } from "../components/DependencyGraph";
import { Badge, Card, Empty, Notice, PageHeader, Stat, Tabs } from "../components/ui";
import { fmtInt } from "../lib/format";
import { useStore } from "../lib/store";

type Tab = "files" | "symbols" | "graph" | "excluded" | "warnings";

export function RepositoryPage() {
  const { indexPath, setIndexPath, indexRepo, repo, details, busy, apiStatus, config } = useStore();
  const [tab, setTab] = useState<Tab>("files");
  const [filter, setFilter] = useState("");
  const [symbolFile, setSymbolFile] = useState("");
  const [focus, setFocus] = useState("");

  const files = useMemo(
    () => (details?.files ?? []).filter((f) => f.path.toLowerCase().includes(filter.toLowerCase())),
    [details, filter],
  );
  const pyFiles = useMemo(() => Object.keys(details?.symbols ?? {}).sort(), [details]);
  const activeSymbolFile = symbolFile || pyFiles.find((p) => (details?.symbols?.[p]?.length ?? 0) > 3) || pyFiles[0] || "";
  const edges = details?.graph?.edges ?? [];
  const focusEdges = focus ? edges.filter((e) => e.source === `file:${focus}` || e.target === `file:${focus}`) : [];

  return (
    <div>
      <PageHeader title="Repository explorer" subtitle="Index a repository, then inspect its files, extracted symbols, dependency graph and exclusions." />
      <Card className="mb-6">
        <form className="flex flex-col gap-3 md:flex-row md:items-end" onSubmit={(e) => { e.preventDefault(); void indexRepo(); }}>
          <div className="flex-1">
            <label className="label" htmlFor="repo-path">Repository directory</label>
            <input id="repo-path" className="input font-mono" value={indexPath} onChange={(e) => setIndexPath(e.target.value)} placeholder="Path on the server" />
          </div>
          <button type="submit" className="btn-primary" disabled={!!busy || apiStatus !== "online"}>
            <FolderSearch className="size-4" /> {repo ? "Re-index" : "Index repository"}
          </button>
        </form>
        <p className="mt-2 text-xs text-zinc-500">On the hosted demo only the bundled example repositories are inside the allowed roots; other paths are rejected by design.</p>
        {!!config?.example_repositories?.length && (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {config.example_repositories.map((ex) => {
              const active = repo?.report.root === ex.path;
              return (
                <button key={ex.path} disabled={!!busy || apiStatus !== "online"}
                  onClick={() => { setIndexPath(ex.path); void indexRepo(ex.path); }}
                  className={`rounded-lg border p-3 text-left transition-colors disabled:opacity-50 ${active ? "border-sky-500 bg-sky-500/10" : "border-zinc-800 hover:border-zinc-600"}`}>
                  <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
                    {ex.name} {active && <Badge tone="high">indexed</Badge>}
                  </div>
                  <div className="mt-1 text-xs text-zinc-400">{ex.description}</div>
                  <div className="mt-1 font-mono text-[11px] text-zinc-600">{ex.path.split(/[\\/]/).slice(-2).join("/")}</div>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      {!repo || !details ? (
        <Empty title="Nothing indexed yet">Click <b>Index repository</b> to scan the sample FastAPI project.</Empty>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Discovered" value={repo.report.total_discovered} />
            <Stat label="Indexed" value={repo.report.indexed} />
            <Stat label="Excluded" value={repo.report.excluded.length} />
            <Stat label="Symbols" value={repo.repository.symbol_count} hint={`${repo.repository.module_count} modules`} />
            <Stat label="Tokens" value={fmtInt(repo.report.total_tokens)} hint={`${repo.report.duration_ms} ms`} />
          </div>
          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            items={[
              { value: "files", label: "Files", count: details.files?.length },
              { value: "symbols", label: "Symbols", count: repo.repository.symbol_count },
              { value: "graph", label: "Dependency graph", count: repo.repository.dependency_edges },
              { value: "excluded", label: "Excluded", count: repo.report.excluded.length },
              { value: "warnings", label: "Warnings", count: repo.report.parse_warnings.length },
            ]}
          />

          {tab === "files" && (
            <Card>
              <input className="input mb-3 max-w-sm" placeholder="Filter paths…" value={filter} onChange={(e) => setFilter(e.target.value)} />
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-zinc-500 uppercase">
                    <tr><th className="py-2 pr-4">Path</th><th className="pr-4">Type</th><th className="pr-4">Language</th><th className="pr-4 text-right">Lines</th><th className="pr-4 text-right">Symbols</th><th className="text-right">Tokens</th></tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/70">
                    {files.map((f) => (
                      <tr key={f.path} className="hover:bg-zinc-900">
                        <td className="py-1.5 pr-4 font-mono text-xs text-zinc-200">{f.path}{f.parse_error && <span className="ml-2 text-amber-400" title={f.parse_error}>⚠</span>}</td>
                        <td className="pr-4"><Badge>{f.file_type}</Badge></td>
                        <td className="pr-4 text-zinc-400">{f.language}</td>
                        <td className="pr-4 text-right tabular-nums text-zinc-400">{f.line_count}</td>
                        <td className="pr-4 text-right tabular-nums text-zinc-400">{f.symbol_count || ""}</td>
                        <td className="text-right tabular-nums text-zinc-300">{fmtInt(f.tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {tab === "symbols" && (
            <Card>
              <label className="label" htmlFor="sym-file">Python module</label>
              <select id="sym-file" className="input mb-4 max-w-xl font-mono" value={activeSymbolFile} onChange={(e) => setSymbolFile(e.target.value)}>
                {pyFiles.map((p) => <option key={p} value={p}>{p} ({details.symbols?.[p]?.length ?? 0})</option>)}
              </select>
              <ul className="divide-y divide-zinc-800/70">
                {(details.symbols?.[activeSymbolFile] ?? []).map((s) => (
                  <li key={s.id} className="py-2.5" style={{ paddingLeft: `${(s.qualname.split(".").length - 1) * 20}px` }}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="source">{s.kind}</Badge>
                      <code className="text-sm text-zinc-100">{s.signature}</code>
                      <span className="text-xs text-zinc-500">lines {s.start_line}–{s.end_line}</span>
                    </div>
                    {s.docstring && <p className="mt-1 text-xs text-zinc-400">{s.docstring.split("\n")[0]}</p>}
                  </li>
                ))}
                {!details.symbols?.[activeSymbolFile]?.length && <li className="py-4 text-sm text-zinc-500">No symbols in this module.</li>}
              </ul>
            </Card>
          )}

          {tab === "graph" && details.graph && (
            <Card title="File dependency graph" actions={focus && <button className="btn-ghost py-1 text-xs" onClick={() => setFocus("")}>Show all</button>}>
              <p className="mb-3 text-sm text-zinc-400">Click a file to focus on it and its direct relationships. Drag to pan, scroll to zoom. Static imports only — runtime wiring is not visible.</p>
              <DependencyGraph nodes={details.graph.nodes} edges={details.graph.edges} focus={focus ? new Set([focus]) : undefined} highlight={focus ? new Set([focus]) : undefined} onSelect={setFocus} />
              <GraphLegend />
              {focus && (
                <div className="mt-4">
                  <h3 className="mb-2 text-sm font-medium text-zinc-200"><code>{focus}</code></h3>
                  <ul className="space-y-1 text-xs">
                    {focusEdges.map((e, i) => {
                      const out = e.source === `file:${focus}`;
                      const other = (out ? e.target : e.source).replace(/^file:/, "");
                      return (
                        <li key={i} className="flex flex-wrap items-center gap-2 text-zinc-300">
                          <span className="text-zinc-500">{out ? "depends on" : "used by"}</span>
                          <code>{other}</code> <Badge tone={e.confidence}>{e.relation} · {e.confidence}</Badge>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </Card>
          )}

          {tab === "excluded" && (
            <Card>
              {repo.report.excluded.length ? (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-zinc-500 uppercase"><tr><th className="py-2 pr-4">Path</th><th>Reason</th></tr></thead>
                  <tbody className="divide-y divide-zinc-800/70">
                    {repo.report.excluded.map((e) => (
                      <tr key={e.path}><td className="py-1.5 pr-4 font-mono text-xs text-zinc-200">{e.path}</td><td className="text-zinc-400">{e.reason}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="text-sm text-zinc-500">No files were excluded.</p>}
            </Card>
          )}

          {tab === "warnings" && (
            <div className="space-y-2">
              {repo.report.parse_warnings.length ? repo.report.parse_warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>) : <Card><p className="text-sm text-zinc-500">No parsing or indexing warnings.</p></Card>}
            </div>
          )}
        </>
      )}
    </div>
  );
}
