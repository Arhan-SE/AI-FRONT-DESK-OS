import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, Field, Input, Select, Button, InlineError } from "@/components/ui/controls";
import { api, ApiError } from "@/lib/api";
import type { LeadRow } from "@/lib/pageQueries";

export function LeadDialog({
  open,
  lead,
  onClose,
}: {
  open: boolean;
  lead: LeadRow | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const isEdit = lead !== null;

  const options = useQuery({
    queryKey: ["job-options"],
    queryFn: api.jobOptions,
    enabled: open && !isEdit,
  });

  const [customerId, setCustomerId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [location, setLocation] = useState("");
  const [urgency, setUrgency] = useState("medium");
  const [timing, setTiming] = useState("morning");
  const [status, setStatus] = useState("new");
  const [nextAction, setNextAction] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLocation(lead?.location ?? "");
    setUrgency(lead?.urgency ?? "medium");
    setTiming(lead?.preferred_timing ?? "morning");
    setStatus(lead?.status ?? "new");
    setNextAction(lead?.next_action ?? "");
    setError(null);
    setConfirmDelete(false);
  }, [open, lead]);

  useEffect(() => {
    const o = options.data;
    if (!o) return;
    setCustomerId((c) => c || o.customers[0]?.id || "");
    setServiceId((s) => s || o.services[0]?.id || "");
  }, [options.data]);

  const refresh = () => {
    for (const key of ["leads", "lead-scores", "dashboard-metrics", "ai-decisions"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };

  const save = useMutation({
    // Returns void: create and edit resolve to different shapes and neither
    // result is used, so widening to a union here would be noise.
    mutationFn: async (): Promise<void> => {
      await (isEdit
        ? api.updateLead(lead.id, {
            status,
            urgency,
            location: location.trim(),
            preferred_timing: timing,
            next_action: nextAction.trim(),
          })
        : api.createLead({
            customer_id: customerId || null,
            service_id: serviceId || null,
            location: location.trim() || null,
            urgency,
            preferred_timing: timing,
          }));
    },
    onSuccess: () => { refresh(); onClose(); },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not save the lead."),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteLead(lead!.id),
    onSuccess: () => { refresh(); onClose(); },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not delete the lead."),
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEdit ? "Edit lead" : "New lead"}
      footer={
        <>
          {isEdit ? (
            <Button variant="ghost" loading={remove.isPending}
              className={confirmDelete ? "text-critical" : ""}
              onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}>
              {confirmDelete ? "Confirm delete" : "Delete"}
            </Button>
          ) : null}
          <span className="flex-1" />
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            {isEdit ? "Save" : "Create & score"}
          </Button>
        </>
      }
    >
      {isEdit ? (
        <p className="t-body">
          <span className="font-medium">{lead.customers?.full_name ?? "Unknown caller"}</span>
          {lead.requested_service ? ` · ${lead.requested_service}` : ""}
        </p>
      ) : (
        <>
          <Field label="Customer">
            <Select value={customerId} onChange={setCustomerId}>
              {options.data?.customers.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Service wanted">
            <Select value={serviceId} onChange={setServiceId}>
              {options.data?.services.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </Select>
          </Field>
        </>
      )}

      <Field label="Location" hint="Scored against the areas the business covers.">
        <Input value={location} onChange={setLocation} placeholder="e.g. Indiranagar" />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Urgency">
          <Select value={urgency} onChange={setUrgency}>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </Select>
        </Field>
        <Field label="Preferred time">
          <Select value={timing} onChange={setTiming}>
            <option value="morning">Morning</option>
            <option value="afternoon">Afternoon</option>
            <option value="evening">Evening</option>
          </Select>
        </Field>
      </div>

      {isEdit ? (
        <>
          <Field label="Status">
            <Select value={status} onChange={setStatus}>
              <option value="new">New</option>
              <option value="qualified">Qualified</option>
              <option value="contacted">Contacted</option>
              <option value="converted">Converted</option>
              <option value="lost">Lost</option>
            </Select>
          </Field>
          <Field label="Next action">
            <Input value={nextAction} onChange={setNextAction} placeholder="Call back to confirm" />
          </Field>
        </>
      ) : (
        // Scored through the same path the voice agent uses, so a hand-entered
        // lead is comparable with a captured one.
        <p className="t-meta">
          The lead is scored on creation using service value, location, urgency
          and customer history.
        </p>
      )}

      <InlineError message={error} />
    </Dialog>
  );
}
