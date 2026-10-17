import { AlertTriangle, Info, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-zinc-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, children, className = "", actions }: { title?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode }) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs font-medium tracking-wide text-zinc-400 uppercase">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-zinc-50">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-zinc-500">{hint}</div>}
    </div>
  );
}

const BADGE_STYLES: Record<string, string> = {
  full: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30",
  excerpt: "bg-amber-500/10 text-amber-300 ring-amber-500/30",
  outline: "bg-violet-500/10 text-violet-300 ring-violet-500/30",
  summary: "bg-pink-500/10 text-pink-300 ring-pink-500/30",
  source: "bg-sky-500/10 text-sky-300 ring-sky-500/30",
  test: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30",
  config: "bg-amber-500/10 text-amber-300 ring-amber-500/30",
  docs: "bg-violet-500/10 text-violet-300 ring-violet-500/30",
  high: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30",
  medium: "bg-amber-500/10 text-amber-300 ring-amber-500/30",
  low: "bg-zinc-500/10 text-zinc-300 ring-zinc-500/30",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const style = BADGE_STYLES[tone ?? String(children)] ?? "bg-zinc-500/10 text-zinc-300 ring-zinc-500/30";
  return (
    <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${style}`}>
      {children}
    </span>
  );
}

/** Horizontal score bar for a single 0-1 value; the number is always printed beside it. */
export function ScoreBar({ value, label, color = "var(--color-acwm)" }: { value: number; label?: string; color?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-2" title={label ? `${label}: ${value.toFixed(2)}` : value.toFixed(2)}>
      {label && <span className="w-20 shrink-0 text-xs text-zinc-400">{label}</span>}
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-9 shrink-0 text-right text-xs tabular-nums text-zinc-300">{value.toFixed(2)}</span>
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  const warn = tone === "warn";
  const Icon = warn ? AlertTriangle : Info;
  return (
    <div className={`flex gap-2 rounded-lg border px-3 py-2 text-sm ${warn ? "border-amber-500/30 bg-amber-500/5 text-amber-200" : "border-sky-500/30 bg-sky-500/5 text-sky-200"}`}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="text-base font-medium text-zinc-200">{title}</div>
      {children && <div className="max-w-md text-sm text-zinc-400">{children}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-zinc-300">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </span>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[] }) {
  return (
    <div role="tablist" className="mb-4 flex flex-wrap gap-1 border-b border-zinc-800">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${value === it.value ? "border-sky-400 text-zinc-50" : "border-transparent text-zinc-400 hover:text-zinc-200"}`}
        >
          {it.label}
          {it.count !== undefined && <span className="ml-1.5 text-xs text-zinc-500">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}
