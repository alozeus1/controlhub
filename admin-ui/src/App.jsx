import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import MainLayout from "./components/MainLayout";
import ProtectedRoute from "./components/ProtectedRoute";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import Uploads from "./pages/Uploads";
import Jobs from "./pages/Jobs";
import AuditLogs from "./pages/AuditLogs";
import Settings from "./pages/Settings";
import Privacy from "./pages/Privacy";
import Support from "./pages/Support";
import Logout from "./pages/Logout";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Root redirects to login */}
        <Route path="/" element={<Navigate to="/ui/login" replace />} />

        {/* Public Route */}
        <Route path="/ui/login" element={<Login />} />

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
          <Route path="/ui/settings" element={<Settings />} />
          <Route path="/ui/privacy" element={<Privacy />} />
          <Route path="/ui/support" element={<Support />} />
          <Route path="/ui/logout" element={<Logout />} />
        </Route>

        {/* Catch-all redirects to login */}
        <Route path="*" element={<Navigate to="/ui/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
