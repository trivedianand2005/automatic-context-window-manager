export const fmtInt = (n: number | null | undefined): string =>
  n === null || n === undefined ? "N/A" : Math.round(n).toLocaleString("en-US");

export const fmtPct = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined ? "N/A" : `${(v * 100).toFixed(digits)}%`;

export const fmtScore = (v: number | null | undefined, digits = 2): string =>
  v === null || v === undefined ? "N/A" : v.toFixed(digits);

export const basename = (path: string): string => path.split("/").pop() ?? path;

export const dirname = (path: string): string => {
  const parts = path.split("/");
  return parts.length > 1 ? parts.slice(0, -1).join("/") + "/" : "";
};

export function lineRangeLabel(ranges: [number, number][], total: number): string {
  if (!ranges.length) return `0 of ${total} lines`;
  return `lines ${ranges.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(", ")} of ${total}`;
}

/** Budget meter segments, in token units, that always sum to the total budget. */
export function budgetSegments(stats: {
  total_budget: number;
  reserved_system_tokens: number;
  reserved_task_tokens: number;
  reserved_response_tokens: number;
  safety_margin_tokens: number;
  rendered_context_tokens: number;
  usable_tokens: number;
}) {
  const reserved =
    stats.reserved_system_tokens +
    stats.reserved_task_tokens +
    stats.reserved_response_tokens +
    stats.safety_margin_tokens;
  const used = Math.min(stats.rendered_context_tokens, stats.usable_tokens);
  const free = Math.max(0, stats.usable_tokens - used);
  const total = Math.max(stats.total_budget, reserved + used + free, 1);
  return [
    { key: "context", label: "Selected context", tokens: used, share: used / total },
    { key: "free", label: "Unused context budget", tokens: free, share: free / total },
    { key: "reserved", label: "Reserved (system, task, response, margin)", tokens: reserved, share: reserved / total },
  ];
}

export function downloadText(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
