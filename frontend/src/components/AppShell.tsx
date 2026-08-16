import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Activity,
  Target,
  Users,
  CalendarDays,
  MessagesSquare,
  Megaphone,
  Star,
  Receipt,
  ChartNoAxesColumn,
  Settings,
  PhoneCall,
} from "lucide-react";
import { cn } from "@/lib/cn";

/** Navigation is grouped, because eleven flat items is a wall. */
const groups = [
  {
    label: null,
    items: [
      { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
      { to: "/activity", label: "AI Activity", icon: Activity },
    ],
  },
  {
    label: "Pipeline",
    items: [
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
      { to: "/insights", label: "Insights", icon: ChartNoAxesColumn },
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
        {/* Business identity. A wordmark, not a logo — this is an internal tool. */}
        <div className="flex h-14 items-center gap-2.5 border-b border-line px-4">
          <div className="grid size-6 shrink-0 place-items-center rounded-[4px] bg-accent">
            <span className="font-mono text-[11px] font-semibold text-accent-ink">A</span>
          </div>
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

        <div className="border-t border-line px-4 py-3">
          <div className="t-meta">AI Business Operating System</div>
        </div>
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
