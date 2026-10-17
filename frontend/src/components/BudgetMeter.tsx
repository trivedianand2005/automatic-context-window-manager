import type { CSSProperties } from "react";
import { budgetSegments, fmtInt, fmtPct } from "../lib/format";
import type { TokenStats } from "../lib/types";

const SEGMENT_STYLE: Record<string, CSSProperties> = {
  context: { background: "var(--color-acwm)" },
  free: { background: "#3f3f46" },
  // Reserved space is shown with a hatch so it never relies on color alone.
  reserved: { background: "repeating-linear-gradient(45deg, #52525b 0 4px, #3f3f46 4px 8px)" },
};

/** One stacked bar showing how the total token budget is spent. */
export function BudgetMeter({ stats }: { stats: TokenStats }) {
  const segments = budgetSegments(stats);
  return (
    <div>
      <div className="flex h-4 w-full gap-0.5 overflow-hidden rounded-full bg-zinc-900" role="img"
        aria-label={`Budget: ${fmtInt(stats.rendered_context_tokens)} context tokens of ${fmtInt(stats.total_budget)} total`}>
        {segments.map((s) =>
          s.tokens > 0 ? (
            <div key={s.key} className="h-full first:rounded-l-full last:rounded-r-full" title={`${s.label}: ${fmtInt(s.tokens)} tokens (${fmtPct(s.share, 1)})`}
              style={{ width: `${s.share * 100}%`, ...SEGMENT_STYLE[s.key] }} />
          ) : null,
        )}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-400">
        {segments.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <span className="inline-block size-2.5 rounded-sm" style={SEGMENT_STYLE[s.key]} aria-hidden />
            {s.label}: <span className="tabular-nums text-zinc-200">{fmtInt(s.tokens)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
