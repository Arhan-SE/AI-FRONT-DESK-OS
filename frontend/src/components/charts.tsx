import type { ReactNode } from "react";
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from "recharts";

/**
 * Charts in this product are single-series and monochrome by design.
 *
 * The design system reserves colour for status, so a categorical palette would
 * be actively wrong here — and a single series needs no legend, because the
 * panel title names it. Magnitude is carried by length and area, which is what
 * the eye reads most accurately anyway.
 */
const INK = "var(--color-ink)";
const LINE = "var(--color-line)";
const SUBTLE = "var(--color-ink-subtle)";

const axis = {
  stroke: LINE,
  tick: { fill: SUBTLE, fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

/** Tooltip styled as a small popover — the one place a shadow is allowed. */
function ChartTooltip({
  active, payload, label, format,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
  format?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const value = payload[0].value;
  return (
    <div className="rounded-[4px] border border-line bg-raised px-2.5 py-1.5 shadow-[var(--shadow-overlay)]">
      <div className="t-meta">{label}</div>
      <div className="text-[15px] font-semibold tabular-nums">
        {format ? format(value) : value}
      </div>
    </div>
  );
}

export function ChartFrame({
  title, hint, children, empty,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  empty?: boolean;
}) {
  return (
    <section className="rounded-[6px] border border-line bg-raised">
      <header className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-3">
        <h3 className="t-section-title">{title}</h3>
        {hint ? <span className="t-meta">{hint}</span> : null}
      </header>
      <div className="px-2 py-3">
        {empty ? (
          <div className="grid h-[168px] place-items-center">
            <span className="t-label">No data yet</span>
          </div>
        ) : (
          <div className="h-[168px]">{children}</div>
        )}
      </div>
    </section>
  );
}

export function TrendArea({
  data, dataKey, xKey = "label", format,
}: {
  data: Record<string, unknown>[];
  dataKey: string;
  xKey?: string;
  format?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
        <defs>
          <linearGradient id="fadeInk" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={INK} stopOpacity={0.14} />
            <stop offset="100%" stopColor={INK} stopOpacity={0.01} />
          </linearGradient>
        </defs>
        {/* Grid is recessive: horizontal only, hairline, no vertical clutter. */}
        <CartesianGrid stroke={LINE} vertical={false} />
        <XAxis dataKey={xKey} {...axis} interval="preserveStartEnd" minTickGap={24} />
        <YAxis {...axis} width={44} allowDecimals={false} />
        <Tooltip
          cursor={{ stroke: LINE, strokeWidth: 1 }}
          content={<ChartTooltip format={format} />}
        />
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={INK}
          strokeWidth={2}
          fill="url(#fadeInk)"
          dot={false}
          activeDot={{ r: 4, fill: INK, stroke: "var(--color-raised)", strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function TrendBars({
  data, dataKey, xKey = "label", format,
}: {
  data: Record<string, unknown>[];
  dataKey: string;
  xKey?: string;
  format?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }} barCategoryGap="28%">
        <CartesianGrid stroke={LINE} vertical={false} />
        <XAxis dataKey={xKey} {...axis} interval="preserveStartEnd" minTickGap={24} />
        <YAxis {...axis} width={44} allowDecimals={false} />
        <Tooltip cursor={{ fill: "var(--color-surface)" }} content={<ChartTooltip format={format} />} />
        {/* 4px rounded data-end, anchored flat to the baseline. */}
        <Bar dataKey={dataKey} fill={INK} radius={[4, 4, 0, 0]} maxBarSize={22}>
          {data.map((row, i) => (
            <Cell
              key={i}
              // Zero-value days stay visible as a faint tick rather than
              // vanishing, so a gap reads as "nothing happened" not "no data".
              fillOpacity={Number(row[dataKey]) === 0 ? 0.12 : 1}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Horizontal magnitude bars. Length carries the value; no axis needed. */
export function MagnitudeBars({
  rows,
}: {
  rows: { label: string; value: number; tone?: "critical" | "warning" | "success" }[];
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  const toneVar = {
    critical: "var(--color-critical)",
    warning: "var(--color-warning)",
    success: "var(--color-success)",
  };
  return (
    <ul className="space-y-2 px-2 py-1">
      {rows.map((r) => (
        <li key={r.label} className="flex items-center gap-3">
          <span className="w-[104px] shrink-0 truncate text-[12px] text-ink-muted">
            {r.label}
          </span>
          <span className="h-3 flex-1 overflow-hidden rounded-[4px] bg-surface">
            <span
              className="block h-full rounded-[4px] transition-[width] duration-300"
              style={{
                width: `${Math.max(r.value === 0 ? 0 : 3, (r.value / max) * 100)}%`,
                background: r.tone ? toneVar[r.tone] : INK,
              }}
            />
          </span>
          <span className="w-8 shrink-0 text-right text-[13px] font-medium tabular-nums">
            {r.value}
          </span>
        </li>
      ))}
    </ul>
  );
}
