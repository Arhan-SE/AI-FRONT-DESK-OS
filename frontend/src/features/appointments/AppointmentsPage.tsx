import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, StatusDot, EmptyState, ErrorState, TableSkeleton, type Tone,
} from "@/components/ui/primitives";
import { useAppointments, type JobRow } from "@/lib/pageQueries";
import { formatTime, formatRelative, BUSINESS_TZ } from "@/lib/format";
import { CalendarDays, Mic } from "lucide-react";

const TONE: Record<string, Tone> = {
  cancelled: "neutral", no_show: "warning", overdue: "critical", paid: "success",
};

const dayKey = new Intl.DateTimeFormat("en-IN", {
  timeZone: BUSINESS_TZ, weekday: "long", day: "2-digit", month: "short",
});

/** Group by business-local day, so a late-evening slot lands on the right date. */
function groupByDay(rows: JobRow[]) {
  const map = new Map<string, JobRow[]>();
  for (const row of rows) {
    const key = dayKey.format(new Date(row.starts_at));
    (map.get(key) ?? map.set(key, []).get(key)!).push(row);
  }
  return [...map.entries()];
}

export function AppointmentsPage() {
  const appts = useAppointments();
  const all = appts.data ?? [];

  const now = Date.now();
  const upcoming = all.filter(
    (a) => new Date(a.starts_at).getTime() >= now &&
           !["cancelled", "no_show"].includes(a.stage),
  );
  const past = all
    .filter((a) => new Date(a.starts_at).getTime() < now ||
                   ["cancelled", "no_show"].includes(a.stage))
    .reverse();

  return (
    <Page title="Appointments" description={`All times in ${BUSINESS_TZ}`}>
      {appts.isPending ? (
        <Panel><TableSkeleton rows={5} cols={4} /></Panel>
      ) : appts.isError ? (
        <Panel><ErrorState onRetry={() => void appts.refetch()} /></Panel>
      ) : all.length === 0 ? (
        <Panel>
          <EmptyState
            icon={CalendarDays}
            title="Nothing scheduled"
            description="Create a job, or let the voice agent book one."
          />
        </Panel>
      ) : (
        <div className="space-y-6">
          <Section title="Upcoming" rows={upcoming} empty="Nothing scheduled ahead" />
          {past.length > 0 ? <Section title="Past" rows={past} empty="" muted /> : null}
        </div>
      )}
    </Page>
  );
}

function Section({
  title, rows, empty, muted,
}: { title: string; rows: JobRow[]; empty: string; muted?: boolean }) {
  return (
    <Panel>
      <PanelHeader title={title} description={`${rows.length} appointment${rows.length === 1 ? "" : "s"}`} />
      {rows.length === 0 ? (
        <EmptyState title={empty} />
      ) : (
        <div className="divide-y divide-line">
          {groupByDay(rows).map(([day, items]) => (
            <div key={day} className="px-4 py-3">
              <div className="t-label mb-2">{day}</div>
              <ul className="space-y-1.5">
                {items.map((a) => (
                  <li key={a.id} className="flex items-baseline gap-3">
                    <span className="w-[72px] shrink-0 font-mono text-[12px] text-ink-muted">
                      {formatTime(a.starts_at)}
                    </span>
                    <StatusDot tone={TONE[a.stage] ?? "neutral"} className="translate-y-[4px]" />
                    <span className={muted ? "t-cell text-ink-muted" : "t-cell"}>
                      <span className="font-medium text-ink">{a.customer_name}</span>
                      {" · "}{a.service_name}
                      <span className="t-meta ml-2">{a.technician_name}</span>
                    </span>
                    {a.source === "voice" ? (
                      <Mic className="size-3 shrink-0 translate-y-[2px] text-ink-subtle"
                        strokeWidth={2} aria-label="Booked by the voice agent" />
                    ) : null}
                    <span className="ml-auto shrink-0 t-meta">
                      {formatRelative(a.starts_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
