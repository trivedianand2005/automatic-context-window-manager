import { Check, Copy, Download } from "lucide-react";
import { useEffect, useState } from "react";
import { CodeView } from "../components/CodeView";
import { Card, Empty, PageHeader, Spinner, Tabs } from "../components/ui";
import { api } from "../lib/api";
import { downloadText } from "../lib/format";
import { useStore } from "../lib/store";
import type { ExportFormat } from "../lib/types";

const FORMATS: { value: ExportFormat; label: string; hint: string; lang: string }[] = [
  { value: "markdown", label: "Markdown", hint: "Readable report with reasons, tables and code.", lang: "markdown" },
  { value: "json", label: "JSON", hint: "Schema-validated, for tools and pipelines.", lang: "json" },
  { value: "txt", label: "Plain text", hint: "Compact: task + code only, ready to paste into an agent.", lang: "text" },
];

export function ExportPage() {
  const { pkg, setPage, excludedFindings } = useStore();
  const [format, setFormat] = useState<ExportFormat>("markdown");
  const [content, setContent] = useState<string>("");
  const [filename, setFilename] = useState("acwm_context.md");
  const [mime, setMime] = useState("text/markdown");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!pkg) return;
    const filtered = { ...pkg, research_findings: pkg.research_findings.filter((_, i) => !excludedFindings.has(i)) };
    let cancelled = false;
    setLoading(true);
    setErr(null);
    api.exportPackage(format, filtered)
      .then((r) => { if (!cancelled) { setContent(r.content); setFilename(r.filename); setMime(r.mime_type); } })
      .catch((e: Error) => { if (!cancelled) setErr(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [pkg, format, excludedFindings]);

  if (!pkg) {
    return (
      <div>
        <PageHeader title="Export" />
        <Empty title="Nothing to export yet">
          <button className="text-sky-400 underline" onClick={() => setPage("build")}>Build a context package</button> first.
        </Empty>
      </div>
    );
  }
  const fmt = FORMATS.find((f) => f.value === format)!;
  return (
    <div>
      <PageHeader title="Export" subtitle="Preview the context package and download it to hand to a coding agent." actions={
        <>
          <button className="btn-ghost" disabled={!content} onClick={async () => { await navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />} Copy
          </button>
          <button className="btn-primary" disabled={!content || loading} onClick={() => downloadText(filename, content, mime)}>
            <Download className="size-4" /> Download {filename}
          </button>
        </>
      } />
      <Tabs<ExportFormat> value={format} onChange={setFormat} items={FORMATS.map((f) => ({ value: f.value, label: f.label }))} />
      <Card title={fmt.hint} actions={<span className="text-xs text-zinc-500">{content ? `${content.length.toLocaleString()} characters` : ""}</span>}>
        {loading ? <Spinner label="Rendering…" /> : err ? <p className="text-sm text-red-300">{err}</p> : <CodeView code={content} language={fmt.lang} maxHeight={640} />}
      </Card>
    </div>
  );
}
