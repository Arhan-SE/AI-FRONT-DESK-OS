import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell, Page } from "@/components/AppShell";
import { Panel, EmptyState } from "@/components/ui/primitives";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { JobsPage } from "@/features/jobs/JobsPage";
import { PaymentsPage } from "@/features/payments/PaymentsPage";
import { CustomersPage } from "@/features/customers/CustomersPage";
import { AppointmentsPage } from "@/features/appointments/AppointmentsPage";
import { CampaignsPage } from "@/features/campaigns/CampaignsPage";
import { ReviewsPage } from "@/features/reviews/ReviewsPage";
import { LeadsPage } from "@/features/leads/LeadsPage";
import { Hammer } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

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
      { path: "jobs", element: <JobsPage /> },
      { path: "activity", element: <Placeholder title="AI Activity" /> },
      { path: "leads", element: <LeadsPage /> },
      { path: "customers", element: <CustomersPage /> },
      { path: "appointments", element: <AppointmentsPage /> },
      { path: "conversations", element: <Placeholder title="Conversations" /> },
      { path: "campaigns", element: <CampaignsPage /> },
      { path: "reviews", element: <ReviewsPage /> },
      { path: "payments", element: <PaymentsPage /> },
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
