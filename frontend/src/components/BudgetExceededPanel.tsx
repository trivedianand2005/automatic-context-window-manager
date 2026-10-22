import { AlertTriangle, RotateCcw, X } from "lucide-react";
import { fmtInt } from "../lib/format";
import type { BudgetIssue } from "../lib/types";

/**
 * Explains a budget-exceeded build: where the budget went, how much was missing, and a
 * one-click retry with the smallest budget that fits (computed by the API).
 */
export function BudgetExceededPanel({
  issue, onRetry, onDismiss, disabled,
}: { issue: BudgetIssue; onRetry: (budget: number) => void; onDismiss: () => void; disabled?: boolean }) {
  const r = issue.reservations;
  const rows: [string, number, string?][] = [
    ["System prompt (reserved)", r.system],
    ["Your task (reserved)", r.task],
    ["Model response (reserved)", r.response],
    ["Safety margin", r.safety_margin],
    ["Left for repository context", issue.available_tokens, "text-zinc-100"],
  ];
  const what = issue.reason === "required_files" ? "Your required files need" : "Repository context needs at least";
  return (
    <section role="alert" aria-label="Budget exceeded" className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-300" aria-hidden />
          <div>
            <h2 className="text-sm font-semibold text-amber-100">Budget exceeded</h2>
            <p className="mt-1 text-sm text-amber-100/80">{issue.message}</p>
          </div>
        </div>
        <button className="rounded p-1 text-amber-200/70 hover:bg-amber-500/10" onClick={onDismiss} aria-label="Dismiss">
          <X className="size-4" />
        </button>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
        <table className="w-full max-w-md text-sm tabular-nums">
          <caption className="sr-only">How the {fmtInt(issue.total_budget)}-token budget is split</caption>
          <tbody className="divide-y divide-amber-500/10">
            <tr><td className="py-1 pr-4 text-zinc-400">Total budget</td><td className="text-right text-zinc-100">{fmtInt(issue.total_budget)}</td></tr>
            {rows.map(([label, n, cls]) => (
              <tr key={label}><td className="py-1 pr-4 text-zinc-400">{label}</td><td className={`text-right ${cls ?? "text-zinc-300"}`}>{fmtInt(n)}</td></tr>
            ))}
            <tr><td className="py-1 pr-4 text-zinc-400">{what}</td><td className="text-right text-zinc-100">{fmtInt(issue.needed_tokens)}</td></tr>
            <tr><td className="py-1 pr-4 font-medium text-amber-200">Short by</td><td className="text-right font-medium text-amber-200">{fmtInt(issue.shortfall_tokens)}</td></tr>
          </tbody>
        </table>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <span className="text-xs text-zinc-400">Smallest budget that fits</span>
          <button className="btn-primary" disabled={disabled} onClick={() => onRetry(issue.suggested_budget)}>
            <RotateCcw className="size-4" /> Use {fmtInt(issue.suggested_budget)} tokens and rebuild
          </button>
          {issue.reason === "required_files" && (
            <span className="text-xs text-zinc-500">Or remove some required files.</span>
          )}
        </div>
      </div>
    </section>
  );
}
