import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, Field, Input, Select, Button, InlineError } from "@/components/ui/controls";
import { api, ApiError } from "@/lib/api";
import type { Invoice } from "@/lib/pageQueries";

export function EditInvoiceDialog({
  invoice,
  onClose,
}: {
  invoice: Invoice | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState("");
  const [dueOn, setDueOn] = useState("");
  const [status, setStatus] = useState("sent");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!invoice) return;
    setAmount(String(invoice.amount));
    setDueOn(invoice.due_on);
    setStatus(invoice.status);
    setError(null);
    setConfirmDelete(false);
  }, [invoice]);

  const refresh = () => {
    for (const key of ["invoices", "jobs", "customers", "dashboard-metrics",
                       "ai-decisions", "automation-queue", "daily-activity"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };

  const save = useMutation({
    mutationFn: () =>
      api.updateInvoice(invoice!.id, {
        amount: Number(amount),
        due_on: dueOn,
        status,
      }),
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
      open={invoice !== null}
      onClose={onClose}
      title={invoice ? `Invoice ${invoice.invoice_number}` : "Invoice"}
      footer={
        <>
          {/* Destructive action sits apart from the primary one, and asks
              once before doing anything. */}
          <Button
            variant="ghost"
            onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
            loading={remove.isPending}
            className={confirmDelete ? "text-critical" : ""}
          >
            {confirmDelete ? "Confirm delete" : "Delete"}
          </Button>
          <span className="flex-1" />
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending} disabled={!amountValid}
            onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      {invoice ? (
        <>
          <p className="t-body">
            <span className="font-medium">{invoice.customer_name}</span>
            {invoice.service_name ? ` · ${invoice.service_name}` : ""}
          </p>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Amount (₹)">
              <Input value={amount} onChange={setAmount} type="number" />
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

          {invoice.reminders_sent > 0 ? (
            <p className="t-meta">
              {invoice.reminders_sent} reminder{invoice.reminders_sent === 1 ? "" : "s"} already
              sent — those cannot be recalled.
            </p>
          ) : null}

          {confirmDelete ? (
            <p className="text-[12px] text-critical">
              This removes the invoice, its payment record, and any pending reminders.
              The job itself stays.
            </p>
          ) : null}

          <InlineError message={error} />
        </>
      ) : null}
    </Dialog>
  );
}
