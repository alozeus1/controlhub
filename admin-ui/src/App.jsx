import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import MainLayout from "./components/MainLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import { FeaturesProvider } from "./contexts/FeaturesContext";

import Login from "./pages/Login";
import LandingPage from "./pages/LandingPage";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import Uploads from "./pages/Uploads";
import Jobs from "./pages/Jobs";
import AuditLogs from "./pages/AuditLogs";
import Policies from "./pages/Policies";
import Approvals from "./pages/Approvals";
import ServiceAccounts from "./pages/ServiceAccounts";
import ServiceAccountDetail from "./pages/ServiceAccountDetail";
import Notifications from "./pages/Notifications";
import AlertRules from "./pages/AlertRules";
import Alerts from "./pages/Alerts";
import Integrations from "./pages/Integrations";
import IntegrationLogs from "./pages/IntegrationLogs";
import AuditExport from "./pages/AuditExport";
import Assets from "./pages/Assets";
import AssetDetail from "./pages/AssetDetail";
import Secrets from "./pages/Secrets";
import EnvConfig from "./pages/EnvConfig";
import Incidents from "./pages/Incidents";
import IncidentDetail from "./pages/IncidentDetail";
import Runbooks from "./pages/Runbooks";
import RunbookDetail from "./pages/RunbookDetail";
import Deployments from "./pages/Deployments";
import Certificates from "./pages/Certificates";
import FeatureFlags from "./pages/FeatureFlags";
import Licenses from "./pages/Licenses";
import Workflows from "./pages/Workflows";
import WorkflowRunDetail from "./pages/WorkflowRunDetail";
import Costs from "./pages/Costs";
import People from "./pages/People";
import PersonDetail from "./pages/PersonDetail";
import InternshipProgram from "./pages/InternshipProgram";
import InternOps from "./pages/InternOps";
import TeamLeadAssignments from "./pages/TeamLeadAssignments";
import MyJourney from "./pages/MyJourney";
import ExportsReports from "./pages/ExportsReports";
import AgentRequests from "./pages/AgentRequests";
import Roles from "./pages/admin/Roles";
import Organization from "./pages/admin/Organization";
import Sso from "./pages/admin/Sso";
import SsoCallback from "./pages/SsoCallback";
import CampaignsHome from "./pages/campaigns/CampaignsHome";
import Subscribers from "./pages/campaigns/Subscribers";
import EmailLists from "./pages/campaigns/EmailLists";
import ListDetail from "./pages/campaigns/ListDetail";
import Campaigns from "./pages/campaigns/Campaigns";
import CampaignDetail from "./pages/campaigns/CampaignDetail";
import EmailSettings from "./pages/campaigns/EmailSettings";
import ErrorBoundary from "./components/ErrorBoundary";
import ElevationGate from "./components/ElevationGate";
import Settings from "./pages/Settings";
import Privacy from "./pages/Privacy";
import Support from "./pages/Support";
import Logout from "./pages/Logout";

export default function App() {
  return (
    <ErrorBoundary>
    <FeaturesProvider>
      {/* Mounted once: any 403 ELEVATION_REQUIRED anywhere opens this prompt. */}
      <ElevationGate />
      <BrowserRouter>
        <Routes>
          {/* Public Landing Page */}
          <Route path="/" element={<LandingPage />} />

          {/* Public Routes */}
          <Route path="/ui/login" element={<Login />} />
          <Route path="/ui/sso-callback" element={<SsoCallback />} />
          <Route path="/ui/forgot-password" element={<ForgotPassword />} />
          <Route path="/ui/reset-password" element={<ResetPassword />} />

          {/* Protected Routes inside Dark Cyber Layout */}
          <Route
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/ui/dashboard" element={<Dashboard />} />
            <Route path="/ui/users" element={<Users />} />
            <Route path="/ui/uploads" element={<Uploads />} />
            <Route path="/ui/jobs" element={<Jobs />} />
            <Route path="/ui/audit-logs" element={<AuditLogs />} />
            <Route path="/ui/policies" element={<Policies />} />
            <Route path="/ui/approvals" element={<Approvals />} />
            {/* Enterprise Features */}
            <Route path="/ui/service-accounts" element={<ServiceAccounts />} />
            <Route path="/ui/service-accounts/:id" element={<ServiceAccountDetail />} />
            <Route path="/ui/notifications" element={<Notifications />} />
            <Route path="/ui/alert-rules" element={<AlertRules />} />
            <Route path="/ui/alerts" element={<Alerts />} />
            <Route path="/ui/integrations" element={<Integrations />} />
            <Route path="/ui/integrations/:id/logs" element={<IntegrationLogs />} />
            <Route path="/ui/audit-export" element={<AuditExport />} />
            <Route path="/ui/assets" element={<Assets />} />
            <Route path="/ui/assets/:id" element={<AssetDetail />} />
            {/* New Feature Routes */}
            <Route path="/ui/secrets" element={<Secrets />} />
            <Route path="/ui/env-config" element={<EnvConfig />} />
            <Route path="/ui/incidents" element={<Incidents />} />
            <Route path="/ui/incidents/:id" element={<IncidentDetail />} />
            <Route path="/ui/runbooks" element={<Runbooks />} />
            <Route path="/ui/runbooks/:id" element={<RunbookDetail />} />
            <Route path="/ui/deployments" element={<Deployments />} />
            <Route path="/ui/certificates" element={<Certificates />} />
            <Route path="/ui/feature-flags" element={<FeatureFlags />} />
            {/* Admin platform */}
            <Route path="/ui/roles" element={<Roles />} />
            <Route path="/ui/organization" element={<Organization />} />
            <Route path="/ui/sso" element={<Sso />} />
            <Route path="/ui/licenses" element={<Licenses />} />
            <Route path="/ui/workflows" element={<Workflows />} />
            <Route path="/ui/workflows/runs/:id" element={<WorkflowRunDetail />} />
            <Route path="/ui/costs" element={<Costs />} />
            <Route path="/ui/people" element={<People />} />
            <Route path="/ui/people/:id" element={<PersonDetail />} />
            <Route path="/ui/internship" element={<InternshipProgram />} />
            <Route path="/ui/intern-ops" element={<InternOps />} />
            <Route path="/ui/team-assignments" element={<TeamLeadAssignments />} />
            <Route path="/ui/my-journey" element={<MyJourney />} />
            <Route path="/ui/exports-reports" element={<ExportsReports />} />
            <Route path="/ui/agent-requests" element={<AgentRequests />} />
            {/* Email Campaigns module */}
            <Route path="/ui/email" element={<CampaignsHome />} />
            <Route path="/ui/email/subscribers" element={<Subscribers />} />
            <Route path="/ui/email/lists" element={<EmailLists />} />
            <Route path="/ui/email/lists/:id" element={<ListDetail />} />
            <Route path="/ui/email/campaigns" element={<Campaigns />} />
            <Route path="/ui/email/campaigns/:id" element={<CampaignDetail />} />
            <Route path="/ui/email/settings" element={<EmailSettings />} />
            <Route path="/ui/settings" element={<Settings />} />
            <Route path="/ui/privacy" element={<Privacy />} />
            <Route path="/ui/support" element={<Support />} />
            <Route path="/ui/logout" element={<Logout />} />
          </Route>

          {/* Catch-all redirects to login */}
          <Route path="*" element={<Navigate to="/ui/login" replace />} />
        </Routes>
      </BrowserRouter>
    </FeaturesProvider>
    </ErrorBoundary>
  );
}
