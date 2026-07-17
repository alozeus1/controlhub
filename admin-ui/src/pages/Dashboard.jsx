import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import { RoleBadge } from "../components/ui/Badge";
import StatCard from "../components/ui/StatCard";
import EmptyState from "../components/ui/EmptyState";
import { SkeletonStats, SkeletonTable } from "../components/ui/Skeleton";
import dashboardArt from "../assets/dashboard_welcome_art.png";
import "./Dashboard.css";

const safeGet = (obj, path, defaultValue = 0) => {
  try {
    const keys = path.split(".");
    let result = obj;
    for (const key of keys) {
      result = result?.[key];
    }
    return result ?? defaultValue;
  } catch {
    return defaultValue;
  }
};

const safeArray = (val) => {
  if (Array.isArray(val)) return val;
  return [];
};

export default function Dashboard() {
  const [stats, setStats] = useState({ users: 0, uploads: 0, jobs: 0, recentLogs: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("user") || "{}"); } catch { return {}; }
  });

  useEffect(() => {
    async function load() {
      // Refresh the profile from the server so the greeting + role badge are
      // always correct for a valid session (fixes stale/empty "User" display).
      try {
        const meRes = await api.get("/auth/me");
        const me = meRes.data?.user || meRes.data;
        if (me && me.email) {
          setUser(me);
          localStorage.setItem("user", JSON.stringify(me));
          sessionStorage.setItem("user", JSON.stringify(me));
        }
      } catch (err) {
        // A 401 is handled by the API client (redirect to login); anything
        // else we log but don't block the rest of the dashboard.
        console.warn("Could not refresh profile:", err);
      }

      try {
        const [usersRes, uploadsRes, jobsRes, logsRes] = await Promise.all([
          api.get("/admin/users?page_size=1").catch((e) => ({ _err: e, data: {} })),
          api.get("/admin/uploads?page_size=1").catch((e) => ({ _err: e, data: {} })),
          api.get("/admin/jobs?page_size=1").catch((e) => ({ _err: e, data: {} })),
          api.get("/admin/audit-logs?page_size=5").catch((e) => ({ _err: e, data: {} })),
        ]);
        setStats({
          users: safeGet(usersRes, "data.total", 0),
          uploads: safeGet(uploadsRes, "data.total", 0),
          jobs: safeGet(jobsRes, "data.total", 0),
          recentLogs: safeArray(safeGet(logsRes, "data.items", [])),
        });
        // Surface a problem instead of silently showing zeros.
        setError(usersRes._err ? "Some dashboard data could not be loaded. Try refreshing." : null);
      } catch (err) {
        console.error("Failed to load stats:", err);
        setError("Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const recentLogs = safeArray(stats.recentLogs);

  return (
    <div className="dashboard-page">
      <div className="welcome-banner">
        <img src={dashboardArt} alt="Welcome abstract graph" className="welcome-banner-bg" />
        <div className="welcome-banner-content">
          <h1 className="welcome-title">Dashboard</h1>
          <p className="welcome-subtitle">Welcome back, {user.email?.split("@")[0] || "User"}</p>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {loading ? (
        <SkeletonStats count={4} />
      ) : (
        <div className="stats-grid">
          <StatCard to="/ui/users" icon="users" value={stats.users} label="Total Users" accent="cyan" />
          <StatCard to="/ui/uploads" icon="folder" value={stats.uploads} label="Total Uploads" accent="green" />
          <StatCard to="/ui/jobs" icon="automation" value={stats.jobs} label="Total Jobs" accent="amber" />
          <StatCard icon="lock" value={<RoleBadge role={user.role} />} label="Your Role" accent="violet" />
        </div>
      )}

      <div className="dashboard-grid">
        <Card>
          <CardHeader title="Recent Activity" subtitle="Latest system actions" />
          <CardBody>
            {loading ? (
              <SkeletonTable rows={5} cols={2} />
            ) : recentLogs.length === 0 ? (
              <EmptyState icon="document" title="No recent activity"
                subtitle="System actions will appear here as they happen." />
            ) : (
              <div className="activity-list">
                {recentLogs.map((log) => (
                  <div key={log.id} className="activity-item">
                    <div className="activity-icon">
                      {log.action.includes("login") ? "🔑" :
                       log.action.includes("created") ? "➕" :
                       log.action.includes("changed") ? "✏️" : "📝"}
                    </div>
                    <div className="activity-content">
                      <div className="activity-action">
                        <strong>{log.actor_email || "System"}</strong>
                        <span>{log.action.replace("user.", "")}</span>
                      </div>
                      <div className="activity-time">
                        {new Date(log.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <Link to="/ui/audit-logs" className="view-all-link">
              View all activity →
            </Link>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Quick Actions" subtitle="Common tasks" />
          <CardBody>
            <div className="quick-actions">
              <Link to="/ui/users" className="quick-action">
                <span className="quick-action-icon">👥</span>
                <span>Manage Users</span>
              </Link>
              <Link to="/ui/audit-logs" className="quick-action">
                <span className="quick-action-icon">📋</span>
                <span>View Audit Logs</span>
              </Link>
              <Link to="/ui/settings" className="quick-action">
                <span className="quick-action-icon">⚙️</span>
                <span>Settings</span>
              </Link>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
