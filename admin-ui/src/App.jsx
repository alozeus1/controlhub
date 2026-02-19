import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import MainLayout from "./components/MainLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import { FeaturesProvider } from "./contexts/FeaturesContext";

import Login from "./pages/Login";
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
import Settings from "./pages/Settings";
import Privacy from "./pages/Privacy";
import Support from "./pages/Support";
import Logout from "./pages/Logout";

export default function App() {
  return (
    <FeaturesProvider>
      <BrowserRouter>
        <Routes>
          {/* Root redirects to login */}
          <Route path="/" element={<Navigate to="/ui/login" replace />} />

          {/* Public Routes */}
          <Route path="/ui/login" element={<Login />} />
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
  );
}
