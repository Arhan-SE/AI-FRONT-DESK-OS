import { useMemo, useState } from "react";
import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, StatusDot, EmptyState, ErrorState, TableSkeleton, Tag, type Tone,
} from "@/components/ui/primitives";
import { Button, Dialog } from "@/components/ui/controls";
import { useAppointments, type JobRow } from "@/lib/pageQueries";
import { formatTime, formatCurrency, BUSINESS_TZ } from "@/lib/format";
import { ChevronLeft, ChevronRight, CalendarDays, Mic, List, Columns3 } from "lucide-react";

/* The grid covers business hours. Anything outside would be dead space on
   every single day, which is a lot of screen for an edge case. */
const DAY_START = 9;
const DAY_END = 18;
const HOUR_PX = 56;
const HOURS = Array.from({ length: DAY_END - DAY_START }, (_, i) => DAY_START + i);

const STAGE_TONE: Record<string, Tone> = {
  overdue: "critical", no_show: "warning", paid: "success",
  cancelled: "neutral", completed: "success",
};

const STAGE_LABEL: Record<string, string> = {
  scheduled: "Scheduled", confirmed: "Confirmed", in_progress: "In progress",
  completed: "Completed", invoice_sent: "Invoice sent", paid: "Paid",
  overdue: "Overdue", cancelled: "Cancelled", no_show: "No show",
};

/** Local parts of an instant, in the business timezone rather than the browser's. */
function businessParts(iso: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: BUSINESS_TZ,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(iso));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  return {
    key: `${get("year")}-${String(get("month")).padStart(2, "0")}-${String(get("day")).padStart(2, "0")}`,
    hour: get("hour"),
    minute: get("minute"),
  };
}

function startOfWeek(d: Date) {
  const copy = new Date(d);
  const day = (copy.getDay() + 6) % 7; // Monday = 0
  copy.setDate(copy.getDate() - day);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function AppointmentsPage() {
  const appts = useAppointments();
  const [weekOffset, setWeekOffset] = useState(0);
  const [view, setView] = useState<"calendar" | "list">("calendar");
  const [selected, setSelected] = useState<JobRow | null>(null);

  const all = appts.data ?? [];

  const week = useMemo(() => {
    const base = startOfWeek(new Date());
    base.setDate(base.getDate() + weekOffset * 7);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(base);
      d.setDate(base.getDate() + i);
      return d;
    });
  }, [weekOffset]);

  const byDay = useMemo(() => {
    const map = new Map<string, JobRow[]>();
    for (const a of all) {
      const { key } = businessParts(a.starts_at);
      const list = map.get(key);
      if (list) list.push(a);
      else map.set(key, [a]);
    }
    return map;
  }, [all]);

  const todayKey = dayKey(new Date());
  const monthLabel = new Intl.DateTimeFormat("en-IN", {
    month: "long", year: "numeric",
  }).format(week[0]);

  return (
    <Page
      title="Appointments"
      action={
        <div className="flex items-center gap-2">
          <Button
            onClick={() => setView(view === "calendar" ? "list" : "calendar")}
            title={view === "calendar" ? "Switch to list" : "Switch to calendar"}
          >
            {view === "calendar" ? <List className="size-3.5" strokeWidth={2} />
                                 : <Columns3 className="size-3.5" strokeWidth={2} />}
            {view === "calendar" ? "List" : "Calendar"}
          </Button>
        </div>
      }
    >
      {appts.isPending ? (
        <Panel><TableSkeleton rows={6} cols={4} /></Panel>
      ) : appts.isError ? (
        <Panel><ErrorState onRetry={() => void appts.refetch()} /></Panel>
      ) : view === "list" ? (
        <ListView rows={all} onSelect={setSelected} />
      ) : (
        <Panel>
          <PanelHeader
            title={monthLabel}
            description={`Business hours ${DAY_START}:00–${DAY_END}:00 · ${BUSINESS_TZ}`}
            action={
              <div className="flex items-center gap-1">
                <Button onClick={() => setWeekOffset((w) => w - 1)} title="Previous week">
                  <ChevronLeft className="size-3.5" strokeWidth={2} />
                </Button>
                <Button onClick={() => setWeekOffset(0)}>Today</Button>
                <Button onClick={() => setWeekOffset((w) => w + 1)} title="Next week">
                  <ChevronRight className="size-3.5" strokeWidth={2} />
                </Button>
              </div>
            }
          />

          <div className="overflow-x-auto">
            <div className="min-w-[860px]">
              {/* ------------------------------------------- day headers */}
              <div className="grid grid-cols-[56px_repeat(7,1fr)] border-b border-line">
                <div />
                {week.map((d) => {
                  const isToday = dayKey(d) === todayKey;
                  const isSunday = d.getDay() === 0;
                  return (
                    <div
                      key={d.toISOString()}
                      className={[
                        "border-l border-line px-2 py-2 text-center",
                        isSunday ? "bg-surface" : "",
                      ].join(" ")}
                    >
                      <div className="t-label">{d.toLocaleDateString("en-IN", { weekday: "short" })}</div>
                      <div className={[
                        "mt-0.5 text-[15px] font-semibold tabular-nums",
                        isToday ? "text-ink" : "text-ink-muted",
                      ].join(" ")}>
                        {isToday ? (
                          <span className="inline-grid size-6 place-items-center rounded-full bg-accent text-accent-ink">
                            {d.getDate()}
                          </span>
                        ) : d.getDate()}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* ----------------------------------------------- the grid */}
              <div className="relative grid grid-cols-[56px_repeat(7,1fr)]">
                {/* hour gutter */}
                <div>
                  {HOURS.map((h) => (
                    <div key={h} className="relative border-b border-line" style={{ height: HOUR_PX }}>
                      <span className="absolute -top-[7px] right-2 t-meta">
                        {h > 12 ? h - 12 : h}{h >= 12 ? "pm" : "am"}
                      </span>
                    </div>
                  ))}
                </div>

                {week.map((d) => {
                  const key = dayKey(d);
                  const isSunday = d.getDay() === 0;
                  const items = byDay.get(key) ?? [];
                  return (
                    <div
                      key={key}
                      className={["relative border-l border-line", isSunday ? "bg-surface" : ""].join(" ")}
                    >
                      {HOURS.map((h) => (
                        <div key={h} className="border-b border-line" style={{ height: HOUR_PX }} />
                      ))}

                      {items.map((a) => {
                        const s = businessParts(a.starts_at);
                        const e = businessParts(a.ends_at);
                        const top = (s.hour - DAY_START) * HOUR_PX + (s.minute / 60) * HOUR_PX;
                        const mins =
                          (e.hour * 60 + e.minute) - (s.hour * 60 + s.minute);
                        const height = Math.max(22, (mins / 60) * HOUR_PX - 2);
                        const cancelled = a.stage === "cancelled" || a.stage === "no_show";

                        return (
                          <button
                            key={a.id}
                            type="button"
                            onClick={() => setSelected(a)}
                            style={{ top, height }}
                            className={[
                              "absolute inset-x-1 overflow-hidden rounded-[4px] border px-1.5 py-1 text-left",
                              "transition-opacity duration-150 hover:opacity-80",
                              cancelled
                                ? "border-line bg-surface opacity-55 line-through"
                                : "border-line-strong bg-raised",
                            ].join(" ")}
                          >
                            <span className="flex items-center gap-1">
                              <StatusDot tone={STAGE_TONE[a.stage] ?? "neutral"} />
                              <span className="truncate text-[11px] font-medium">
                                {formatTime(a.starts_at)}
                              </span>
                              {a.source === "voice" ? (
                                <Mic className="size-2.5 shrink-0 text-ink-subtle" strokeWidth={2.5} />
                              ) : null}
                            </span>
                            <span className="block truncate text-[11px] text-ink">
                              {a.customer_name}
                            </span>
                            {height > 44 ? (
                              <span className="block truncate text-[10px] text-ink-muted">
                                {a.service_name}
                              </span>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {all.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="Nothing scheduled"
              description="Create a job, or let the voice agent book one."
            />
          ) : null}
        </Panel>
      )}

      <DetailDialog job={selected} onClose={() => setSelected(null)} />
    </Page>
  );
}

function ListView({ rows, onSelect }: { rows: JobRow[]; onSelect: (j: JobRow) => void }) {
  const now = Date.now();
  const upcoming = rows.filter((r) => new Date(r.starts_at).getTime() >= now);
  const past = rows.filter((r) => new Date(r.starts_at).getTime() < now).reverse();

  const Section = ({ title, items }: { title: string; items: JobRow[] }) => (
    <Panel>
      <PanelHeader title={title} description={`${items.length} appointment${items.length === 1 ? "" : "s"}`} />
      {items.length === 0 ? (
        <EmptyState title="Nothing here" />
      ) : (
        <ul className="divide-y divide-line">
          {items.map((a) => (
            <li key={a.id}>
              <button type="button" onClick={() => onSelect(a)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-surface">
                <span className="w-[132px] shrink-0 font-mono text-[12px] text-ink-muted">
                  {new Date(a.starts_at).toLocaleDateString("en-IN", {
                    timeZone: BUSINESS_TZ, day: "2-digit", month: "short" })}
                  {" · "}{formatTime(a.starts_at)}
                </span>
                <StatusDot tone={STAGE_TONE[a.stage] ?? "neutral"} />
                <span className="t-cell font-medium">{a.customer_name}</span>
                <span className="t-cell text-ink-muted">{a.service_name}</span>
                <span className="ml-auto t-meta">{a.technician_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );

  return (
    <div className="space-y-6">
      <Section title="Upcoming" items={upcoming} />
      <Section title="Past" items={past} />
    </div>
  );
}

function DetailDialog({ job, onClose }: { job: JobRow | null; onClose: () => void }) {
  return (
    <Dialog open={job !== null} onClose={onClose} title={job?.customer_name ?? "Appointment"}>
      {job ? (
        <dl className="space-y-2.5 text-[13px]">
          {[
            ["Service", job.service_name],
            ["Technician", job.technician_name],
            ["When", `${new Date(job.starts_at).toLocaleDateString("en-IN", {
              timeZone: BUSINESS_TZ, weekday: "long", day: "numeric", month: "long" })}, ${formatTime(job.starts_at)} – ${formatTime(job.ends_at)}`],
            ["Stage", STAGE_LABEL[job.stage] ?? job.stage],
            ["Booked via", job.source === "voice" ? "AI voice agent" : job.source],
            ...(job.invoice_number
              ? [["Invoice", `${job.invoice_number} · ${formatCurrency(job.invoice_amount)}`]]
              : []),
          ].map(([label, value]) => (
            <div key={label as string} className="flex gap-3">
              <dt className="w-[92px] shrink-0 t-label">{label}</dt>
              <dd className="min-w-0 flex-1">{value}</dd>
            </div>
          ))}
          <div className="pt-1">
            <Tag>Change the stage from the Jobs board</Tag>
          </div>
        </dl>
      ) : null}
    </Dialog>
  );
}
