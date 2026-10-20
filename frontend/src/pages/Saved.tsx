import { Download, FolderOpen, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, Empty, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { downloadText, fmtInt } from "../lib/format";
import { useStore } from "../lib/store";

export function SavedPage() {
  const { saved, refreshSaved, openSaved, deleteSaved, setPage, user, busy } = useStore();
  const [confirming, setConfirming] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    void refreshSaved().finally(() => setLoaded(true));
  }, [refreshSaved]);

  const download = async (id: number) => {
    const row = await api.getPackage(id);
    const out = await api.exportPackage("markdown", row.package);
    downloadText(out.filename, out.content, out.mime_type);
  };

  return (
    <div>
      <PageHeader
        title="Saved packages"
        subtitle={<>Context packages saved to <b className="text-zinc-200">{user?.display_name}</b>'s account. Only you can see them.</>}
      />
      {!loaded ? null : saved.length === 0 ? (
        <Empty title="No saved packages yet">
          Build a context package, then press <b>Save to my account</b> on the Results page.
          <div className="mt-4"><button className="btn-primary" onClick={() => setPage("build")}>Build context</button></div>
        </Empty>
      ) : (
        <Card>
          <ul className="divide-y divide-zinc-800">
            {saved.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-zinc-100">{p.title}</div>
                  <div className="mt-0.5 truncate text-xs text-zinc-500">
                    {p.repository_name} · {p.item_count} items · {fmtInt(p.rendered_tokens)} tokens ·{" "}
                    {new Date(p.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="btn-ghost px-3 py-1.5 text-xs" disabled={!!busy} onClick={() => void openSaved(p.id)}>
                    <FolderOpen className="size-3.5" /> Open
                  </button>
                  <button className="btn-ghost px-3 py-1.5 text-xs" onClick={() => void download(p.id)}>
                    <Download className="size-3.5" /> Markdown
                  </button>
                  {confirming === p.id ? (
                    <>
                      <button className="btn px-3 py-1.5 text-xs bg-red-500/90 text-white hover:bg-red-500"
                        onClick={() => { void deleteSaved(p.id); setConfirming(null); }}>
                        Confirm delete
                      </button>
                      <button className="btn-ghost px-3 py-1.5 text-xs" onClick={() => setConfirming(null)}>Cancel</button>
                    </>
                  ) : (
                    <button className="btn-ghost px-3 py-1.5 text-xs" aria-label={`Delete ${p.title}`} onClick={() => setConfirming(p.id)}>
                      <Trash2 className="size-3.5" /> Delete
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
