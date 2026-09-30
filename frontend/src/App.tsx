import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { InsightsPage } from "@/features/insights/InsightsPage";
import { JobsPage } from "@/features/jobs/JobsPage";
import { PaymentsPage } from "@/features/payments/PaymentsPage";
import { CustomersPage } from "@/features/customers/CustomersPage";
import { AppointmentsPage } from "@/features/appointments/AppointmentsPage";
import { CampaignsPage } from "@/features/campaigns/CampaignsPage";
import { ReviewsPage } from "@/features/reviews/ReviewsPage";
import { LeadsPage } from "@/features/leads/LeadsPage";
import { VoiceCallPage } from "@/features/voice/VoiceCallPage";
import { JoinCallPage } from "@/features/voice/JoinCallPage";
import { ConversationsPage } from "@/features/conversations/ConversationsPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { AiManagerPage } from "@/features/manager/AiManagerPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "insights", element: <InsightsPage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "leads", element: <LeadsPage /> },
      { path: "customers", element: <CustomersPage /> },
      { path: "appointments", element: <AppointmentsPage /> },
      { path: "conversations", element: <ConversationsPage /> },
      { path: "campaigns", element: <CampaignsPage /> },
      { path: "reviews", element: <ReviewsPage /> },
      { path: "payments", element: <PaymentsPage /> },
      { path: "demo", element: <VoiceCallPage /> },
      { path: "manager", element: <AiManagerPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
  // Outside AppShell on purpose — a customer opening a Telegram call-invite
  // link should see the call, not the internal dashboard nav around it.
  { path: "/call/:purpose/:ref", element: <JoinCallPage /> },
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
