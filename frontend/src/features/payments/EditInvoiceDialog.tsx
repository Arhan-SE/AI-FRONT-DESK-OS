import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, Field, Input, Select, Button, InlineError } from "@/components/ui/controls";
import { api, ApiError } from "@/lib/api";
import type { Invoice } from "@/lib/pageQueries";

/** `invoice === null` while open means create. One dialog, so the two cannot drift. */
export function EditInvoiceDialog({
  open,
  invoice,
  onClose,
}: {
  open: boolean;
  invoice: Invoice | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const isEdit = invoice !== null;

  const options = useQuery({
    queryKey: ["job-options"],
    queryFn: api.jobOptions,
    enabled: open && !isEdit,
  });

  const [customerId, setCustomerId] = useState("");
  const [amount, setAmount] = useState("");
  const [dueOn, setDueOn] = useState("");
  const [status, setStatus] = useState("sent");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAmount(invoice ? String(invoice.amount) : "");
    setStatus(invoice?.status ?? "sent");
    setDueOn(
      invoice?.due_on ??
        new Date(Date.now() + 7 * 86400_000).toISOString().slice(0, 10),
    );
    setError(null);
    setConfirmDelete(false);
  }, [open, invoice]);

  useEffect(() => {
    const o = options.data;
    if (o) setCustomerId((c) => c || o.customers[0]?.id || "");
  }, [options.data]);

  const refresh = () => {
    for (const key of ["invoices", "jobs", "customers", "dashboard-metrics",
                       "ai-decisions", "automation-queue", "daily-activity"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };

  const save = useMutation({
    // Returns void: create and edit resolve to different shapes and neither
    // result is used.
    mutationFn: async (): Promise<void> => {
      await (isEdit
        ? api.updateInvoice(invoice.id, {
            amount: Number(amount), due_on: dueOn, status,
          })
        : api.createInvoice({
            customer_id: customerId, amount: Number(amount),
            due_on: dueOn, status,
          }));
    },
    onSuccess: () => { refresh(); onClose(); },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not save the invoice."),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteInvoice(invoice!.id),
    onSuccess: () => { refresh(); onClose(); },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not delete the invoice."),
  });

  const amountValid = amount !== "" && Number(amount) >= 0 && !Number.isNaN(Number(amount));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEdit ? `Invoice ${invoice.invoice_number}` : "New invoice"}
      footer={
        <>
          {isEdit ? (
            <Button
              variant="ghost"
              loading={remove.isPending}
              className={confirmDelete ? "text-critical" : ""}
              onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
            >
              {confirmDelete ? "Confirm delete" : "Delete"}
            </Button>
          ) : null}
          <span className="flex-1" />
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending}
            disabled={!amountValid || (!isEdit && !customerId)}
            onClick={() => save.mutate()}>
            {isEdit ? "Save" : "Raise invoice"}
          </Button>
        </>
      }
    >
      {isEdit ? (
        <p className="t-body">
          <span className="font-medium">{invoice.customer_name}</span>
          {invoice.service_name ? ` · ${invoice.service_name}` : ""}
        </p>
      ) : (
        <Field label="Customer">
          <Select value={customerId} onChange={setCustomerId}>
            {options.data?.customers.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
        </Field>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount (₹)">
          <Input value={amount} onChange={setAmount} type="number" placeholder="1499" />
        </Field>
        <Field label="Due date">
          <Input value={dueOn} onChange={setDueOn} type="date" />
        </Field>
      </div>

      <Field
        label="Status"
        hint="Marking paid records a payment and stops reminders. Un-marking removes it."
      >
        <Select value={status} onChange={setStatus}>
          <option value="draft">Draft</option>
          <option value="sent">Awaiting payment</option>
          <option value="overdue">Overdue</option>
          <option value="paid">Paid</option>
          <option value="void">Void</option>
        </Select>
      </Field>

      {isEdit && invoice.reminders_sent > 0 ? (
        <p className="t-meta">
          {invoice.reminders_sent} reminder{invoice.reminders_sent === 1 ? "" : "s"} already
          sent — those cannot be recalled.
        </p>
      ) : null}

      {!isEdit ? (
        <p className="t-meta">
          A reminder is queued for the day after the due date, and chased like
          any other invoice.
        </p>
      ) : null}

      {confirmDelete ? (
        <p className="text-[12px] text-critical">
          This removes the invoice, its payment record, and any pending reminders.
          The job itself stays.
        </p>
      ) : null}

      <InlineError message={error} />
    </Dialog>
  );
}
