import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, Field, Input, Select, Button, InlineError } from "@/components/ui/controls";
import { api, ApiError } from "@/lib/api";
import type { CustomerRow } from "@/lib/pageQueries";

export function EditCustomerDialog({
  customer,
  onClose,
}: {
  customer: CustomerRow | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [chatId, setChatId] = useState("");
  const [status, setStatus] = useState("active");
  const [dnc, setDnc] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refill whenever a different customer is opened.
  useEffect(() => {
    if (!customer) return;
    setName(customer.full_name);
    setPhone(customer.phone ?? "");
    setEmail(customer.email ?? "");
    setAddress(customer.address ?? "");
    setChatId(customer.telegram_chat_id ? String(customer.telegram_chat_id) : "");
    setStatus(customer.status);
    setDnc(customer.do_not_contact);
    setError(null);
  }, [customer]);

  const save = useMutation({
    mutationFn: () => {
      const trimmed = chatId.trim();
      return api.updateCustomer(customer!.id, {
        full_name: name.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        address: address.trim() || null,
        // Blank clears the link, which also revokes consent server-side.
        telegram_chat_id: trimmed ? Number(trimmed) : null,
        do_not_contact: dnc,
        status,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["customers"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job-options"] });
      onClose();
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not save the changes."),
  });

  const chatIdValid = chatId.trim() === "" || /^-?\d+$/.test(chatId.trim());

  return (
    <Dialog
      open={customer !== null}
      onClose={onClose}
      title={customer ? `Edit ${customer.full_name}` : "Edit customer"}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!name.trim() || !chatIdValid}
            onClick={() => save.mutate()}
          >
            Save
          </Button>
        </>
      }
    >
      <Field label="Name">
        <Input value={name} onChange={setName} />
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
            <input
              type="checkbox"
              className="accent-ink"
              checked={dnc}
              onChange={(e) => setDnc(e.target.checked)}
            />
            Do not contact
          </label>
        </Field>
      </div>

      <InlineError message={error} />
    </Dialog>
  );
}
