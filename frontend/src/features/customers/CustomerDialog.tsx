import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, Field, Input, Select, Button, InlineError } from "@/components/ui/controls";
import { api, ApiError } from "@/lib/api";
import type { CustomerRow } from "@/lib/pageQueries";

/**
 * One dialog for create and edit.
 *
 * `customer === null` with `open` means create; a customer means edit. Two
 * near-identical dialogs would drift the moment a field was added to one.
 */
export function CustomerDialog({
  open,
  customer,
  onClose,
}: {
  open: boolean;
  customer: CustomerRow | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const isEdit = customer !== null;

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [chatId, setChatId] = useState("");
  const [status, setStatus] = useState("active");
  const [dnc, setDnc] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(customer?.full_name ?? "");
    setPhone(customer?.phone ?? "");
    setEmail(customer?.email ?? "");
    setAddress(customer?.address ?? "");
    setChatId(customer?.telegram_chat_id ? String(customer.telegram_chat_id) : "");
    setStatus(customer?.status ?? "active");
    setDnc(customer?.do_not_contact ?? false);
    setError(null);
    setConfirmDelete(false);
  }, [open, customer]);

  const refresh = () => {
    for (const key of ["customers", "jobs", "job-options", "dashboard-metrics",
                       "invoices", "leads", "ai-decisions"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };

  const trimmedChat = chatId.trim();
  const chatIdValid = trimmedChat === "" || /^-?\d+$/.test(trimmedChat);

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        full_name: name.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        address: address.trim() || null,
        telegram_chat_id: trimmedChat ? Number(trimmedChat) : null,
      };
      return isEdit
        ? api.updateCustomer(customer.id, { ...payload, do_not_contact: dnc, status })
        : api.createCustomer(payload as never);
    },
    onSuccess: () => { refresh(); onClose(); },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not save the customer."),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteCustomer(customer!.id),
    onSuccess: () => { refresh(); onClose(); },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not delete the customer."),
  });

  const hasHistory = (customer?.jobs_completed ?? 0) + (customer?.jobs_upcoming ?? 0) > 0;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEdit ? `Edit ${customer.full_name}` : "New customer"}
      footer={
        <>
          {isEdit ? (
            <Button
              variant="ghost"
              onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
              loading={remove.isPending}
              className={confirmDelete ? "text-critical" : ""}
            >
              {confirmDelete ? "Confirm delete" : "Delete"}
            </Button>
          ) : null}
          <span className="flex-1" />
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending}
            disabled={!name.trim() || !chatIdValid} onClick={() => save.mutate()}>
            {isEdit ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <Field label="Name">
        <Input value={name} onChange={setName} placeholder="Full name" />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Phone">
          <Input value={phone} onChange={setPhone} placeholder="+91 …" />
        </Field>
        <Field label="Email">
          <Input value={email} onChange={setEmail} type="email" placeholder="optional" />
        </Field>
      </div>

      <Field label="Address">
        <Input value={address} onChange={setAddress} placeholder="optional" />
      </Field>

      <Field
        label="Telegram chat ID"
        hint="Set this and the customer becomes contactable. Leave blank to unlink."
      >
        <Input value={chatId} onChange={setChatId} placeholder="e.g. 123456789" />
      </Field>
      {!chatIdValid ? <InlineError message="Chat ID must be a number." /> : null}

      {isEdit ? (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Status">
            <Select value={status} onChange={setStatus}>
              <option value="active">Active</option>
              <option value="dormant">Dormant</option>
              <option value="archived">Archived</option>
            </Select>
          </Field>
          <Field label="Contact preference">
            <label className="flex h-8 items-center gap-2 text-[13px]">
              <input type="checkbox" className="accent-ink" checked={dnc}
                onChange={(e) => setDnc(e.target.checked)} />
              Do not contact
            </label>
          </Field>
        </div>
      ) : null}

      {confirmDelete ? (
        <p className="text-[12px] text-critical">
          {hasHistory
            ? `This also deletes ${customer!.jobs_completed + customer!.jobs_upcoming} job(s), their invoices and reviews.`
            : "This removes the customer permanently."}
        </p>
      ) : null}

      <InlineError message={error} />
    </Dialog>
  );
}
