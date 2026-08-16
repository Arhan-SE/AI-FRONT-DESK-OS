/**
 * Every date in this application is rendered in the business's timezone, never
 * the browser's. A technician in another timezone must still see the slot the
 * customer was promised.
 */
export const BUSINESS_TZ = "Asia/Kolkata";

/** Indian digit grouping (lakh/crore), no decimals — these are whole rupees. */
const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export const formatCurrency = (value: number | string | null | undefined) =>
  value == null ? "—" : inr.format(Number(value));

/** Compact form for metric tiles: ₹3.7L rather than ₹3,70,839. */
export function formatCurrencyCompact(value: number | string | null | undefined) {
  if (value == null) return "—";
  const n = Number(value);
  if (n >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(1)}Cr`;
  if (n >= 1_00_000) return `₹${(n / 1_00_000).toFixed(1)}L`;
  if (n >= 1_000) return `₹${(n / 1_000).toFixed(1)}K`;
  return inr.format(n);
}

export const formatNumber = (value: number | null | undefined) =>
  value == null ? "—" : new Intl.NumberFormat("en-IN").format(value);

const dateFmt = new Intl.DateTimeFormat("en-IN", {
  timeZone: BUSINESS_TZ,
  day: "2-digit",
  month: "short",
});

const dateYearFmt = new Intl.DateTimeFormat("en-IN", {
  timeZone: BUSINESS_TZ,
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const timeFmt = new Intl.DateTimeFormat("en-IN", {
  timeZone: BUSINESS_TZ,
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

const clockFmt = new Intl.DateTimeFormat("en-IN", {
  timeZone: BUSINESS_TZ,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export const formatDate = (v: string | Date | null | undefined) =>
  v == null ? "—" : dateFmt.format(new Date(v));

export const formatDateFull = (v: string | Date | null | undefined) =>
  v == null ? "—" : dateYearFmt.format(new Date(v));

export const formatTime = (v: string | Date | null | undefined) =>
  v == null ? "—" : timeFmt.format(new Date(v));

/** HH:MM:SS — the AI Activity feed's leading column. */
export const formatClock = (v: string | Date | null | undefined) =>
  v == null ? "—" : clockFmt.format(new Date(v));

export const formatDateTime = (v: string | Date | null | undefined) =>
  v == null ? "—" : `${dateFmt.format(new Date(v))}, ${timeFmt.format(new Date(v))}`;

/** "3 days ago", "in 2 hours" — relative to now, in whole units. */
export function formatRelative(v: string | Date | null | undefined) {
  if (v == null) return "—";
  const then = new Date(v).getTime();
  const diffMs = then - Date.now();
  const abs = Math.abs(diffMs);

  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (abs < minute) return "just now";
  if (abs < hour) return rtf.format(Math.round(diffMs / minute), "minute");
  if (abs < day) return rtf.format(Math.round(diffMs / hour), "hour");
  if (abs < 30 * day) return rtf.format(Math.round(diffMs / day), "day");
  return rtf.format(Math.round(diffMs / (30 * day)), "month");
}

/** Voice-friendly slot phrasing. Never read IDs or ISO timestamps aloud. */
export function formatSlotSpoken(v: string | Date) {
  const d = new Date(v);
  const weekday = new Intl.DateTimeFormat("en-IN", {
    timeZone: BUSINESS_TZ,
    weekday: "long",
  }).format(d);
  return `${weekday} at ${timeFmt.format(d)}`;
}
