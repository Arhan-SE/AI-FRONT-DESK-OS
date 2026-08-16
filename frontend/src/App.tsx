import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell, Page } from "@/components/AppShell";
import { Panel, EmptyState } from "@/components/ui/primitives";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { Hammer } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

/** Temporary. Each of these is replaced as its feature lands. */
function Placeholder({ title }: { title: string }) {
  return (
    <Page title={title}>
      <Panel>
        <EmptyState
          icon={Hammer}
          title="Not built yet"
          description="This screen is next in the build order."
        />
      </Panel>
    </Page>
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "activity", element: <Placeholder title="AI Activity" /> },
      { path: "leads", element: <Placeholder title="Leads" /> },
      { path: "customers", element: <Placeholder title="Customers" /> },
      { path: "appointments", element: <Placeholder title="Appointments" /> },
      { path: "conversations", element: <Placeholder title="Conversations" /> },
      { path: "campaigns", element: <Placeholder title="Campaigns" /> },
      { path: "reviews", element: <Placeholder title="Reviews" /> },
      { path: "payments", element: <Placeholder title="Payments" /> },
      { path: "insights", element: <Placeholder title="Insights" /> },
      { path: "demo", element: <Placeholder title="Live Call" /> },
      { path: "settings", element: <Placeholder title="Settings" /> },
    ],
  },
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
