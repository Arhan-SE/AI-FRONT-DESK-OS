import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Lightbulb,
  Activity,
  Briefcase,
  Target,
  Users,
  CalendarDays,
  MessagesSquare,
  Megaphone,
  Star,
  Receipt,
  Settings,
  PhoneCall,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/cn";
import logoMark from "@/assets/logo-mark.png";
import { api } from "@/lib/api";
import { AskBar } from "@/components/AskBar";

/**
 * Live system state, always on screen.
 *
 * Without this, a backend that dies mid-demo shows up as an error on whichever
 * page happens to be open — and looks like that page is broken. One indicator
 * that is always visible turns "something is wrong" into "the API is down".
 */
function SystemStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 10_000,
    retry: 0,
  });

  const down = health.isError;
  const h = health.data as
    | { telegram_configured?: boolean; ai_configured?: boolean }
    | undefined;

  const telegramOff = h ? !h.telegram_configured : false;

  return (
    <div className="space-y-1.5 border-t border-line px-4 py-3">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            down ? "bg-critical" : health.isPending ? "bg-ink-subtle" : "bg-success",
          )}
          aria-hidden
        />
        <span className="t-meta">
          {down ? "API unreachable" : health.isPending ? "Checking…" : "All systems running"}
        </span>
      </div>

      {/* Named explicitly rather than left as a silent gap: outreach not
          arriving is the first thing anyone will ask about. */}
      {telegramOff ? (
        <div className="flex items-center gap-2">
          <span className="size-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
          <span className="t-meta">Telegram not configured</span>
        </div>
      ) : null}
    </div>
  );
}

/** Navigation is grouped, because eleven flat items is a wall. */
const groups = [
  {
    label: null,
    items: [
      { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
      { to: "/insights", label: "Insights", icon: Lightbulb },
    ],
  },
  {
    label: "Pipeline",
    items: [
      { to: "/jobs", label: "Jobs", icon: Briefcase },
      { to: "/leads", label: "Leads", icon: Target },
      { to: "/customers", label: "Customers", icon: Users },
      { to: "/appointments", label: "Appointments", icon: CalendarDays },
      { to: "/conversations", label: "Conversations", icon: MessagesSquare },
    ],
  },
  {
    label: "Revenue",
    items: [
      { to: "/campaigns", label: "Campaigns", icon: Megaphone },
      { to: "/reviews", label: "Reviews", icon: Star },
      { to: "/payments", label: "Payments", icon: Receipt },
    ],
  },
  {
    label: null,
    items: [
      { to: "/demo", label: "Live Call", icon: PhoneCall },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

function SidebarLink({
  to,
  label,
  icon: Icon,
  end,
}: {
  to: string;
  label: string;
  icon: typeof Activity;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "group flex h-8 items-center gap-2.5 rounded-[4px] px-2",
          "text-[13px] transition-colors duration-150",
          // Active state is contrast, not colour. A blue pill here would be the
          // single most "generated template" thing in the product.
          isActive
            ? "bg-raised font-medium text-ink shadow-[inset_0_0_0_1px_var(--color-line)]"
            : "text-ink-muted hover:bg-raised/60 hover:text-ink",
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            className={cn("size-4 shrink-0", isActive ? "text-ink" : "text-ink-subtle")}
            strokeWidth={1.75}
          />
          <span className="truncate">{label}</span>
        </>
      )}
    </NavLink>
  );
}

export function AppShell() {
  return (
    <div className="flex h-dvh overflow-hidden bg-canvas">
      <aside className="flex w-[232px] shrink-0 flex-col border-r border-line bg-surface">
        {/* Business identity. The mark alone, not the full lockup — at 232px the
            horizontal wordmark would either be unreadable or eat the header. The
            name is set in type beside it, which stays crisp at any zoom. */}
        <div className="flex h-14 items-center gap-2.5 border-b border-line px-4">
          <img
            src={logoMark}
            alt=""
            className="size-7 shrink-0 object-contain"
          />
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold leading-tight">
              Apex Climate Care
            </div>
            <div className="t-meta leading-tight">Bengaluru</div>
          </div>
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto px-2.5 py-3">
          {groups.map((group, i) => (
            <div key={i} className="space-y-0.5">
              {group.label ? (
                <div className="px-2 pb-1 pt-1 text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
                  {group.label}
                </div>
              ) : null}
              {group.items.map((item) => (
                <SidebarLink key={item.to} {...item} />
              ))}
            </div>
          ))}
        </nav>

        <div className="border-t border-line px-2.5 py-2.5">
          <AskBar />
        </div>

        <SystemStatus />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}

/** Consistent page chrome: title left, primary action right, content below. */
export function Page({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line px-6">
        <div className="min-w-0">
          <h1 className="t-page-title truncate">{title}</h1>
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-6 py-6">
          {description ? <p className="t-label -mt-1 mb-5">{description}</p> : null}
          {children}
        </div>
      </div>
    </>
  );
}
