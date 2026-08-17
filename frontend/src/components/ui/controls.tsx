import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import { X, Loader2 } from "lucide-react";

/* -------------------------------------------------------------------------
   Button
   Two weights only. A third would start a hierarchy nobody can remember.
------------------------------------------------------------------------- */

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md";
  disabled?: boolean;
  loading?: boolean;
  type?: "button" | "submit";
  className?: string;
  title?: string;
};

export function Button({
  children,
  onClick,
  variant = "secondary",
  size = "sm",
  disabled,
  loading,
  type = "button",
  className,
  title,
}: ButtonProps) {
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      // A button that is already working must not be clickable again —
      // duplicate submissions are the easiest way to double-book a technician.
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-[4px] font-medium",
        "whitespace-nowrap transition-opacity duration-150",
        "disabled:pointer-events-none disabled:opacity-40",
        size === "sm" ? "h-7 px-2.5 text-[12px]" : "h-8 px-3 text-[13px]",
        variant === "primary" && "bg-accent text-accent-ink hover:opacity-85",
        variant === "secondary" &&
          "border border-line-strong bg-raised text-ink hover:bg-surface",
        variant === "ghost" && "text-ink-muted hover:text-ink",
        className,
      )}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" strokeWidth={2} /> : null}
      {children}
    </button>
  );
}

/* -------------------------------------------------------------------------
   Form fields
------------------------------------------------------------------------- */

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="t-label mb-1 block">{label}</span>
      {children}
      {hint ? <span className="t-meta mt-1 block">{hint}</span> : null}
    </label>
  );
}

const fieldStyles =
  "h-8 w-full rounded-[4px] border border-line-strong bg-raised px-2 text-[13px] " +
  "text-ink outline-none transition-shadow duration-150 " +
  "focus:border-accent disabled:opacity-50";

export function Select({
  value,
  onChange,
  children,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={cn(fieldStyles, "appearance-none pr-6")}
    >
      {children}
    </select>
  );
}

export function Input({
  value,
  onChange,
  type = "text",
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={fieldStyles}
    />
  );
}

/* -------------------------------------------------------------------------
   Dialog
   The one place in the product allowed a shadow.
------------------------------------------------------------------------- */

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/20 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-full max-w-[420px] rounded-[8px] border border-line bg-raised",
          "shadow-[var(--shadow-overlay)] outline-none",
        )}
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="t-section-title">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-ink-subtle transition-colors duration-150 hover:text-ink"
          >
            <X className="size-4" strokeWidth={2} />
          </button>
        </header>
        <div className="space-y-3 px-4 py-4">{children}</div>
        {footer ? (
          <footer className="flex justify-end gap-2 border-t border-line px-4 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

/* -------------------------------------------------------------------------
   Inline error — shown next to the thing that failed, never as a toast that
   disappears before it can be read.
------------------------------------------------------------------------- */

export function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="flex items-start gap-1.5 text-[12px] text-critical">
      <span className="mt-1 inline-block size-1.5 shrink-0 rounded-full bg-critical" />
      {message}
    </p>
  );
}
