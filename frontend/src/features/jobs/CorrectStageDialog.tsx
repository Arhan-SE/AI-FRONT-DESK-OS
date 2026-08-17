import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, Field, Select, Button, InlineError } from "@/components/ui/controls";
import { api, ApiError, type Job, type Stage } from "@/lib/api";

/** Correctable stages, in pipeline order. Cancelled is reached by cancelling. */
const STAGES: { value: Stage; label: string }[] = [
  { value: "scheduled", label: "Scheduled" },
  { value: "confirmed", label: "Confirmed" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "invoice_sent", label: "Invoice sent" },
];

const ORDER: Stage[] = ["scheduled", "confirmed", "in_progress", "completed", "invoice_sent", "paid"];

/** What moving back to each stage will undo, stated before it happens. */
function consequences(from: Stage, to: Stage): string[] {
  const fromIdx = ORDER.indexOf(from);
  const toIdx = ORDER.indexOf(to);
  if (toIdx < 0 || fromIdx < 0) return [];

  const out: string[] = [];
  if (fromIdx >= ORDER.indexOf("paid") && toIdx <= ORDER.indexOf("invoice_sent")) {
    out.push("Removes the payment and reopens the invoice");
    out.push("Re-queues the next payment reminder");
  }
  if (toIdx <= ORDER.indexOf("completed") && fromIdx > ORDER.indexOf("completed")) {
    out.push("Deletes the invoice and any payment against it");
  }
  if (toIdx < ORDER.indexOf("completed") && fromIdx >= ORDER.indexOf("completed")) {
    out.push("Cancels the pending follow-up and review request");
  }
  if (toIdx === 0 && fromIdx > 0) {
    out.push("Cancels every queued message for this job");
  }
  return out;
}

export function CorrectStageDialog({
  job,
  onClose,
}: {
  job: Job | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<Stage>("completed");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!job) return;
    // Default to one step back — the common case is undoing the last click.
    const idx = ORDER.indexOf(job.stage);
    setTarget(idx > 0 ? ORDER[idx - 1] : "scheduled");
    setError(null);
    setConfirmDelete(false);
  }, [job]);

  const correct = useMutation({
    mutationFn: () => api.correct(job!.id, target),
    onSuccess: () => {
      for (const key of ["jobs", "invoices", "customers", "ai-decisions",
                         "dashboard-metrics", "automation-queue", "reviews"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
      onClose();
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not correct the stage."),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteJob(job!.id),
    onSuccess: () => {
      for (const key of ["jobs", "invoices", "customers", "ai-decisions",
                         "dashboard-metrics", "daily-activity", "appointments"]) {
        qc.invalidateQueries({ queryKey: [key] });
      }
      onClose();
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not delete the job."),
  });

  const undone = job ? consequences(job.stage, target) : [];

  return (
    <Dialog
      open={job !== null}
      onClose={onClose}
      title="Correct stage"
      footer={
        <>
          {/* Deleting says the job should never have been recorded; correcting
              says its stage was wrong. Different intents, different buttons. */}
          <Button
            variant="ghost"
            loading={remove.isPending}
            className={confirmDelete ? "text-critical" : ""}
            onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
          >
            {confirmDelete ? "Confirm delete" : "Delete job"}
          </Button>
          <span className="flex-1" />
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={correct.isPending} onClick={() => correct.mutate()}>
            Move to {STAGES.find((s) => s.value === target)?.label}
          </Button>
        </>
      }
    >
      {job ? (
        <>
          <p className="t-body">
            <span className="font-medium">{job.customer_name}</span> · {job.service_name} is
            currently <span className="font-medium">{job.stage.replace("_", " ")}</span>.
          </p>

          <Field label="Set stage to" hint="Use this to fix a stage set by mistake.">
            <Select value={target} onChange={(v) => setTarget(v as Stage)}>
              {STAGES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </Select>
          </Field>

          {undone.length > 0 ? (
            <div className="rounded-[4px] border border-line bg-surface px-3 py-2">
              <p className="t-label mb-1">This will:</p>
              <ul className="space-y-0.5">
                {undone.map((c) => (
                  <li key={c} className="flex gap-1.5 text-[12px] text-ink-muted">
                    <span className="mt-[7px] inline-block size-1 shrink-0 rounded-full bg-ink-subtle" />
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {/* Said plainly rather than buried: undoing state is possible,
              unsending a message is not. */}
          <p className="t-meta">
            Messages already sent cannot be recalled — only pending work is cancelled.
          </p>

          {confirmDelete ? (
            <p className="text-[12px] text-critical">
              This removes the job, its invoice and any queued messages entirely.
            </p>
          ) : null}

          <InlineError message={error} />
        </>
      ) : null}
    </Dialog>
  );
}
