import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Mode } from "../lib/types";

/** Fixed entity -> color mapping (never by rank). Dataviz palette slots 1-3, dark mode. */
export const METHOD_COLOR: Record<Mode, string> = {
  acwm: "#3987e5",
  baseline: "#d95926",
  dependency: "#199e70",
};
export const METHOD_LABEL: Record<Mode, string> = {
  baseline: "Baseline (BM25)",
  dependency: "+ Dependency expansion",
  acwm: "Full ACWM",
};
export const METHOD_ORDER: Mode[] = ["baseline", "dependency", "acwm"];

export interface MetricRow {
  metric: string;
  baseline: number | null;
  dependency: number | null;
  acwm: number | null;
}

/** Grouped bars: one group per 0-1 metric, one bar per method. Hover shows exact values. */
export function MethodChart({ rows, height = 280 }: { rows: MetricRow[]; height?: number }) {
  return (
    <div style={{ height }} role="img" aria-label="Metric comparison across retrieval methods; values are listed in the table below">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} barGap={2} barCategoryGap="22%" margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#27272a" />
          <XAxis dataKey="metric" tick={{ fill: "#a1a1aa", fontSize: 12 }} axisLine={{ stroke: "#3f3f46" }} tickLine={false} />
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={{ fill: "#71717a", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "rgba(255,255,255,0.04)" }}
            contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#e4e4e7" }}
            itemStyle={{ color: "#d4d4d8" }}
            formatter={(v, name) => [typeof v === "number" ? v.toFixed(3) : "N/A", name]}
          />
          <Legend
            wrapperStyle={{ fontSize: 12 }}
            iconType="square"
            formatter={(value: string) => <span style={{ color: "#d4d4d8" }}>{value}</span>}
          />
          {METHOD_ORDER.map((m) => (
            <Bar key={m} dataKey={m} name={METHOD_LABEL[m]} fill={METHOD_COLOR[m]} radius={[4, 4, 0, 0]}
              maxBarSize={36} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
