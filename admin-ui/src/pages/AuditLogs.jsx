import { useState, useEffect } from "react";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Pagination from "../components/ui/Pagination";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import api from "../utils/api";
import "./AuditLogs.css";

const actionColors = {
  "user.login": "info",
  "user.login_failed": "error",
  "user.logout": "default",
  "user.created": "success",
  "user.role_changed": "warning",
  "user.enabled": "success",
  "user.disabled": "error",
};

export default function AuditLogs() {
  const [logs, setLogs] = useState([]);
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [filters, setFilters] = useState({ action: "", search: "" });
  const toast = useToast();

  const fetchLogs = async (page = 1) => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page, page_size: 20 });
      if (filters.action) params.append("action", filters.action);
      if (filters.search) params.append("search", filters.search);

      const res = await api.get(`/admin/audit-logs?${params}`);
      setLogs(res.data.items);
      setPagination({
        page: res.data.page,
        pages: res.data.pages,
        total: res.data.total,
        page_size: res.data.page_size,
      });
    } catch (err) {
      toast.error("Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  };

  const fetchActions = async () => {
    try {
      const res = await api.get("/admin/audit-logs/actions");
      setActions(res.data);
    } catch {}
  };

  useEffect(() => {
    fetchActions();
  }, []);

  useEffect(() => {
    fetchLogs(1);
  }, [filters]);

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  return (
    <div className="audit-logs-page">
      <div className="page-header">
        <h1 className="page-title">Audit Logs</h1>
        <p className="page-subtitle">Track all system actions and user activities</p>
      </div>

      <Card>
        <CardHeader title={`${pagination.total} Log Entries`}>
          <div className="audit-filters">
            <Select
              value={filters.action}
              onChange={(e) => setFilters({ ...filters, action: e.target.value })}
              style={{ width: 200 }}
            >
              <option value="">All Actions</option>
              {actions.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </Select>
            <input
              type="text"
              className="input"
              placeholder="Search by email..."
              value={filters.search}
              onChange={(e) => setFilters({ ...filters, search: e.target.value })}
              style={{ width: 250 }}
            />
          </div>
        </CardHeader>
        <CardBody>
          {loading ? (
            <PageLoader message="Loading audit logs..." />
          ) : logs.length === 0 ? (
            <div className="empty-state">
              <p>No audit logs found</p>
            </div>
          ) : (
            <>
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Target</th>
                    <th>Details</th>
                    <th>IP Address</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td className="font-mono text-sm">{formatDate(log.created_at)}</td>
                      <td>
                        <Badge variant={actionColors[log.action] || "default"}>
                          {log.action}
                        </Badge>
                      </td>
                      <td>{log.actor_email || "-"}</td>
                      <td>{log.target_label || "-"}</td>
                      <td className="details-cell">
                        {log.details ? (
                          <code>{JSON.stringify(log.details)}</code>
                        ) : "-"}
                      </td>
                      <td className="font-mono text-muted">{log.ip_address || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchLogs}
              />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
