import { useState, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { Dialog, Field, Select, Input, Button, InlineError } from "@/components/ui/controls";

/**
 * India does not observe daylight saving, so the offset is a fixed +05:30.
 * Appending it explicitly means a datetime-local value is interpreted in the
 * business's timezone rather than the browser's — a technician opening this on
 * a laptop still set to another zone books the slot the customer was promised.
 */
const IST_OFFSET = "+05:30";

function toBusinessIso(localValue: string): string {
  return new Date(`${localValue}:00${IST_OFFSET}`).toISOString();
}

function defaultSlot(): string {
  const d = new Date(Date.now() + 24 * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T10:00`;
}

export function NewJobDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();

  const options = useQuery({
    queryKey: ["job-options"],
    queryFn: api.jobOptions,
    enabled: open,
  });

  const [customer, setCustomer] = useState("");
  const [service, setService] = useState("");
  const [technician, setTechnician] = useState("");
  const [startsAt, setStartsAt] = useState(defaultSlot);
  const [error, setError] = useState<string | null>(null);

  // Preselect once the lists arrive so the form is submittable immediately.
  useEffect(() => {
    const o = options.data;
    if (!o) return;
    setCustomer((c) => c || o.customers[0]?.id || "");
    setService((s) => s || o.services[0]?.id || "");
    setTechnician((t) => t || o.technicians[0]?.id || "");
  }, [options.data]);

  // Stable across retries, so a resubmit after a network blip returns the
  // existing job instead of creating a second one.
  const idempotencyKey = useMemo(
    () => (open ? crypto.randomUUID() : ""),
    [open],
  );

  const create = useMutation({
    mutationFn: () =>
      api.createJob({
        customer_id: customer,
        service_id: service,
        technician_id: technician,
        starts_at: toBusinessIso(startsAt),
        idempotency_key: idempotencyKey,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
      setError(null);
      onClose();
    },
    onError: (e: unknown) => {
      // Input is deliberately preserved — the usual cause is a slot clash and
      // the owner only needs to change the time.
      setError(e instanceof ApiError ? e.message : "Could not create the job.");
    },
  });

  const ready = customer && service && technician && startsAt;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New job"
      footer={
        <>
          <Button onClick={onClose} variant="ghost">
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={create.isPending}
            disabled={!ready}
            onClick={() => create.mutate()}
          >
            Create job
          </Button>
        </>
      }
    >
      {options.isPending ? (
        <p className="t-label">Loading…</p>
      ) : options.isError ? (
        <InlineError message="Could not load customers and services." />
      ) : (
        <>
          <Field label="Customer">
            <Select value={customer} onChange={setCustomer}>
              {options.data?.customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.reachable ? "" : " · no Telegram"}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Service">
            <Select value={service} onChange={setService}>
              {options.data?.services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.duration_minutes}m · ₹{s.price.toLocaleString("en-IN")}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Technician">
            <Select value={technician} onChange={setTechnician}>
              {options.data?.technicians.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Starts at" hint="Asia/Kolkata">
            <Input type="datetime-local" value={startsAt} onChange={setStartsAt} />
          </Field>

          <InlineError message={error} />
        </>
      )}
    </Dialog>
  );
}
