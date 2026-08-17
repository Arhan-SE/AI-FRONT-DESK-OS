import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/AppShell";
import {
  Panel,
  PanelHeader,
  Table,
  Th,
  Td,
  Tr,
  StatusDot,
  EmptyState,
  ErrorState,
  TableSkeleton,
  type Tone,
} from "@/components/ui/primitives";
import { Button, InlineError } from "@/components/ui/controls";
import { NewJobDialog } from "./NewJobDialog";
import { api, ApiError, type Job, type Action, type Stage } from "@/lib/api";
import { formatDateTime, formatCurrency } from "@/lib/format";
import { Plus, Play, Briefcase, MessageSquareOff } from "lucide-react";

/**
 * The pipeline, in order. This array is the page: the strip across the top,
 * the sort order, and which button each row offers all derive from it, so the
 * stages can never disagree with each other.
 */
const PIPELINE: {
  key: Stage;
  label: string;
  next?: { action: Action; label: string };
  tone?: Tone;
}[] = [
  { key: "scheduled", label: "Scheduled", next: { action: "confirm", label: "Confirm" } },
  { key: "confirmed", label: "Confirmed", next: { action: "start", label: "Start job" } },
  { key: "in_progress", label: "In progress", next: { action: "complete", label: "Complete" } },
  { key: "completed", label: "Completed", next: { action: "send_invoice", label: "Send invoice" } },
  { key: "invoice_sent", label: "Invoice sent", next: { action: "mark_paid", label: "Mark paid" } },
  { key: "overdue", label: "Overdue", next: { action: "mark_paid", label: "Mark paid" }, tone: "critical" },
  { key: "paid", label: "Paid", tone: "success" },
];

const STAGE_META = new Map(PIPELINE.map((s) => [s.key, s]));
const CANCELLABLE: Stage[] = ["scheduled", "confirmed", "in_progress"];

/** What each transition sets in motion, shown before the owner commits. */
const CONSEQUENCE: Partial<Record<Action, string>> = {
  confirm: "Sends a confirmation now and a reminder 24h before",
  complete: "Sends a follow-up in 2h and a review request in 24h",
  send_invoice: "Starts the payment clock; reminders begin after the due date",
  mark_paid: "Cancels any pending payment reminders",
};

export function JobsPage() {
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [filter, setFilter] = useState<Stage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.listJobs, refetchInterval: 15_000 });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["jobs"] });
    qc.invalidateQueries({ queryKey: ["ai-decisions"] });
    qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
    qc.invalidateQueries({ queryKey: ["automation-queue"] });
  };

  const move = useMutation({
    mutationFn: ({ id, action }: { id: string; action: Action }) => api.transition(id, action),
    onMutate: ({ id }) => {
      setBusyId(id);
      setError(null);
    },
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "That action could not be completed."),
    onSettled: () => setBusyId(null),
  });

  const runDue = useMutation({
    mutationFn: api.runDue,
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not run the automations."),
  });

  const all = jobs.data ?? [];
  const counts = (stage: Stage) => all.filter((j) => j.stage === stage).length;
  const visible = filter ? all.filter((j) => j.stage === filter) : all;

  return (
    <Page
      title="Jobs"
      action={
        <div className="flex items-center gap-2">
          <Button
            onClick={() => runDue.mutate()}
            loading={runDue.isPending}
            title="Advance scheduled automations to now and run them"
          >
            <Play className="size-3.5" strokeWidth={2} />
            Run due automations
          </Button>
          <Button variant="primary" onClick={() => setDialogOpen(true)}>
            <Plus className="size-3.5" strokeWidth={2} />
            New job
          </Button>
        </div>
      }
    >
      {/* The pipeline strip. Left to right is the real customer journey, so the
          page explains itself without a tutorial. Also the stage filter. */}
      <div className="mb-5 overflow-x-auto">
        <div className="flex min-w-max items-stretch gap-px rounded-[6px] border border-line bg-line">
          {PIPELINE.map((stage, i) => {
            const n = counts(stage.key);
            const active = filter === stage.key;
            return (
              <button
                key={stage.key}
                type="button"
                onClick={() => setFilter(active ? null : stage.key)}
                className={[
                  "group relative flex-1 px-4 py-2.5 text-left transition-colors duration-150",
                  active ? "bg-surface" : "bg-raised hover:bg-surface/60",
                  i === 0 ? "rounded-l-[6px]" : "",
                  i === PIPELINE.length - 1 ? "rounded-r-[6px]" : "",
                ].join(" ")}
              >
                <span className="flex items-center gap-1.5">
                  {stage.tone ? <StatusDot tone={stage.tone} /> : null}
                  <span className="t-label whitespace-nowrap">{stage.label}</span>
                </span>
                <span
                  className={[
                    "mt-0.5 block text-[20px] font-semibold leading-tight",
                    n === 0 ? "text-ink-subtle" : "text-ink",
                  ].join(" ")}
                >
                  {n}
                </span>
              </button>
            );
          })}
        </div>
        <p className="t-meta mt-2">
          The owner updates what happened; the system decides what to send.
          {filter ? (
            <>
              {" · "}
              <button className="underline" onClick={() => setFilter(null)}>
                clear filter
              </button>
            </>
          ) : null}
        </p>
      </div>

      {runDue.data ? (
        <p className="t-meta mb-3">
          Advanced {runDue.data.advanced} · executed {runDue.data.executed} — see AI Activity
        </p>
      ) : null}

      <InlineError message={error} />

      <Panel className={error ? "mt-3" : ""}>
        <PanelHeader
          title={filter ? STAGE_META.get(filter)?.label ?? "Jobs" : "All jobs"}
          description="Each status change triggers the right automation automatically"
        />

        {jobs.isPending ? (
          <TableSkeleton rows={4} cols={5} />
        ) : jobs.isError ? (
          <ErrorState
            description="Could not load jobs. Check that the API is running on port 8000."
            onRetry={() => void jobs.refetch()}
          />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={Briefcase}
            title={filter ? "Nothing at this stage" : "No jobs yet"}
            description={
              filter
                ? "Clear the filter to see the rest."
                : "Create one, or let the voice agent book it."
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Customer</Th>
                <Th>Service</Th>
                <Th>When</Th>
                <Th>Technician</Th>
                <Th>Stage</Th>
                <Th align="right">Action</Th>
              </tr>
            </thead>
            <tbody>
              {visible.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  busy={busyId === job.id}
                  onMove={(action) => move.mutate({ id: job.id, action })}
                />
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <NewJobDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </Page>
  );
}

function JobRow({
  job,
  busy,
  onMove,
}: {
  job: Job;
  busy: boolean;
  onMove: (action: Action) => void;
}) {
  const meta = STAGE_META.get(job.stage);
  const terminal = job.stage === "cancelled" || job.stage === "no_show";

  return (
    <Tr>
      <Td>
        <span className="flex items-center gap-2">
          <span className="font-medium">{job.customer_name}</span>
          {/* Without a linked chat the Guard will block every message for this
              job. Surfacing it here explains the silence before it happens. */}
          {!job.customer_reachable ? (
            <MessageSquareOff
              className="size-3.5 text-ink-subtle"
              strokeWidth={1.75}
              aria-label="No Telegram linked — messages will be blocked"
            />
          ) : null}
        </span>
      </Td>
      <Td className="text-ink-muted">
        {job.service_name}
        {job.invoice_amount ? (
          <span className="t-meta ml-2">{formatCurrency(job.invoice_amount)}</span>
        ) : null}
      </Td>
      <Td>{formatDateTime(job.starts_at)}</Td>
      <Td className="text-ink-muted">{job.technician_name}</Td>
      <Td>
        <span className="flex items-center gap-2">
          <StatusDot tone={meta?.tone ?? (terminal ? "neutral" : "neutral")} />
          <span>{terminal ? "Cancelled" : (meta?.label ?? job.stage)}</span>
        </span>
      </Td>
      <Td align="right">
        <span className="flex items-center justify-end gap-1.5">
          {CANCELLABLE.includes(job.stage) ? (
            <Button variant="ghost" onClick={() => onMove("cancel")} disabled={busy}>
              Cancel
            </Button>
          ) : null}
          {meta?.next ? (
            <Button
              variant="primary"
              loading={busy}
              onClick={() => onMove(meta.next!.action)}
              title={CONSEQUENCE[meta.next.action]}
            >
              {meta.next.label}
            </Button>
          ) : (
            <span className="t-meta">—</span>
          )}
        </span>
      </Td>
    </Tr>
  );
}
