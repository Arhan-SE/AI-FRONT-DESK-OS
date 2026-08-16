import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { AlertCircle, Inbox, RotateCw } from "lucide-react";

/* -------------------------------------------------------------------------
   Status
   Colour appears only here, and only as a 6px dot or a 2px left edge. A filled
   bright pill would put colour everywhere and destroy the signal — on a grey
   screen one red dot is unmissable.
------------------------------------------------------------------------- */

export type Tone = "neutral" | "critical" | "warning" | "success";

const toneDot: Record<Tone, string> = {
  neutral: "bg-ink-subtle",
  critical: "bg-critical",
  warning: "bg-warning",
  success: "bg-success",
};

export function StatusDot({ tone = "neutral", className }: { tone?: Tone; className?: string }) {
  return (
    <span
      className={cn("inline-block size-1.5 shrink-0 rounded-full", toneDot[tone], className)}
      aria-hidden
    />
  );
}

export function StatusLabel({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <StatusDot tone={tone} />
      <span className="t-cell">{children}</span>
    </span>
  );
}

/** Quiet outline chip. Used for categories, never for status. */
export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[4px] border border-line px-1.5 py-0.5",
        "font-mono text-[11px] text-ink-muted",
        className,
      )}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------
   Surfaces
------------------------------------------------------------------------- */

export function Panel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn("rounded-[6px] border border-line bg-raised", className)}
    >
      {children}
    </section>
  );
}

export function PanelHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex items-start justify-between gap-4 border-b border-line px-4 py-3">
      <div className="min-w-0">
        <h2 className="t-section-title">{title}</h2>
        {description ? <p className="t-label mt-0.5">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

/* -------------------------------------------------------------------------
   Metric tile
------------------------------------------------------------------------- */

export function MetricTile({
  label,
  value,
  hint,
  tone = "neutral",
  loading,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  loading?: boolean;
}) {
  return (
    <div className="rounded-[6px] border border-line bg-raised px-4 py-3.5">
      <div className="flex items-center gap-2">
        {tone !== "neutral" ? <StatusDot tone={tone} /> : null}
        <span className="t-label">{label}</span>
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-20" />
      ) : (
        <div className="t-metric mt-1.5">{value}</div>
      )}
      {hint ? <div className="t-meta mt-1">{hint}</div> : null}
    </div>
  );
}

/* -------------------------------------------------------------------------
   Async states — every list must be able to render all four.
------------------------------------------------------------------------- */

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-[4px] bg-surface", className)}
      aria-hidden
    />
  );
}

export function TableSkeleton({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="divide-y divide-line" aria-busy>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex h-10 items-center gap-4 px-4">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cn("h-3", c === 0 ? "w-40" : "w-20")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
}: {
  title: string;
  description?: string;
  icon?: typeof Inbox;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <Icon className="size-5 text-ink-subtle" strokeWidth={1.5} />
      <p className="t-section-title mt-3">{title}</p>
      {description ? (
        <p className="t-label mt-1 max-w-sm">{description}</p>
      ) : null}
    </div>
  );
}

export function ErrorState({
  title = "Could not load this",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <AlertCircle className="size-5 text-critical" strokeWidth={1.5} />
      <p className="t-section-title mt-3">{title}</p>
      {/* Never a raw stack trace. */}
      {description ? <p className="t-label mt-1 max-w-md">{description}</p> : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className={cn(
            "mt-4 inline-flex items-center gap-1.5 rounded-[4px] border border-line-strong",
            "bg-raised px-2.5 py-1.5 text-[13px] font-medium",
            "transition-opacity duration-150 hover:opacity-70",
          )}
        >
          <RotateCw className="size-3.5" strokeWidth={2} />
          Retry
        </button>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------
   Table
   Operational data belongs in tables, not cards. 40px rows, hairline dividers.
------------------------------------------------------------------------- */

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">{children}</table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
  className,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "whitespace-nowrap border-b border-line bg-surface px-4 py-2",
        "text-[12px] font-medium text-ink-muted",
        align === "right" && "text-right",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <td
      className={cn(
        "h-10 whitespace-nowrap border-b border-line px-4 t-cell",
        align === "right" && "text-right",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function Tr({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick?: () => void;
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        "transition-colors duration-120",
        onClick && "cursor-pointer hover:bg-surface",
      )}
    >
      {children}
    </tr>
  );
}
