import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import { RoleBadge } from "../components/ui/Badge";
import { PageLoader } from "../components/ui/Spinner";
import "./Dashboard.css";

export default function Dashboard() {
  const [stats, setStats] = useState({ users: 0, uploads: 0, jobs: 0, recentLogs: [] });
  const [loading, setLoading] = useState(true);
  const user = JSON.parse(localStorage.getItem("user") || "{}");

  useEffect(() => {
    async function load() {
      try {
        const [usersRes, uploadsRes, jobsRes, logsRes] = await Promise.all([
          api.get("/admin/users?page_size=1"),
          api.get("/admin/uploads?page_size=1"),
          api.get("/admin/jobs?page_size=1"),
          api.get("/admin/audit-logs?page_size=5"),
        ]);
        setStats({
          users: usersRes.data.total || 0,
          uploads: uploadsRes.data.total || 0,
          jobs: jobsRes.data.total || 0,
          recentLogs: logsRes.data.items || [],
        });
      } catch (err) {
        console.error("Failed to load stats:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <PageLoader message="Loading dashboard..." />;

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Welcome back, {user.email?.split("@")[0] || "User"}</p>
        </div>
      </div>

      <div className="stats-grid">
        <Link to="/ui/users" className="stat-card">
          <div className="stat-icon">👥</div>
          <div className="stat-content">
            <div className="stat-value">{stats.users}</div>
            <div className="stat-label">Total Users</div>
          </div>
        </Link>
        <Link to="/ui/uploads" className="stat-card">
          <div className="stat-icon">📁</div>
          <div className="stat-content">
            <div className="stat-value">{stats.uploads}</div>
            <div className="stat-label">Total Uploads</div>
          </div>
        </Link>
        <Link to="/ui/jobs" className="stat-card">
          <div className="stat-icon">⚙️</div>
          <div className="stat-content">
            <div className="stat-value">{stats.jobs}</div>
            <div className="stat-label">Total Jobs</div>
          </div>
        </Link>
        <div className="stat-card">
          <div className="stat-icon">🔐</div>
          <div className="stat-content">
            <div className="stat-value"><RoleBadge role={user.role} /></div>
            <div className="stat-label">Your Role</div>
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        <Card>
          <CardHeader title="Recent Activity" subtitle="Latest system actions" />
          <CardBody>
            {stats.recentLogs.length === 0 ? (
              <p className="empty-text">No recent activity</p>
            ) : (
              <div className="activity-list">
                {stats.recentLogs.map((log) => (
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
