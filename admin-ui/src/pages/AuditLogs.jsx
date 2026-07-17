import { useState, useEffect } from "react";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import { Select } from "../components/ui/Input";
import Button from "../components/ui/Button";
import AppIcon from "../components/ui/AppIcon";
import Badge from "../components/ui/Badge";
import Pagination from "../components/ui/Pagination";
import EmptyState from "../components/ui/EmptyState";
import { SkeletonTable } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import api from "../utils/api";
import { formatDateTime } from "../utils/datetime";
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
  const [exporting, setExporting] = useState(false);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [filters, setFilters] = useState({ action: "", search: "", from_date: "", to_date: "" });
  const toast = useToast();

  const buildParams = (extra = {}) => {
    const params = new URLSearchParams({ ...extra });
    if (filters.action) params.append("action", filters.action);
    if (filters.search) params.append("search", filters.search);
    if (filters.from_date) params.append("from_date", filters.from_date);
    if (filters.to_date) params.append("to_date", `${filters.to_date}T23:59:59`);
    return params;
  };

  const fetchLogs = async (page = 1) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/audit-logs?${buildParams({ page, page_size: 20 })}`);
      setLogs(res.data.items || []);
      setPagination({
        page: res.data.page, pages: res.data.pages,
        total: res.data.total, page_size: res.data.page_size,
      });
    } catch (err) {
      toast.error("Failed to load audit logs");
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchActions = async () => {
    try { const res = await api.get("/admin/audit-logs/actions"); setActions(res.data || []); }
    catch { /* ignore */ }
  };

  const exportCsv = async () => {
    try {
      setExporting(true);
      const res = await api.get(`/admin/audit-logs/export?${buildParams()}`, { responseType: "blob" });
      const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error("Export failed");
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => { fetchActions(); }, []);
  useEffect(() => { fetchLogs(1); }, [filters]); // eslint-disable-line

  const formatDate = (dateStr) => formatDateTime(dateStr);

  return (
    <div className="audit-logs-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit Logs</h1>
          <p className="page-subtitle">Full history of actions across the platform</p>
        </div>
        <Button variant="secondary" loading={exporting} onClick={exportCsv} icon={<AppIcon name="document" size={15} />}>
          Export CSV
        </Button>
      </div>

      <Card>
        <CardHeader title={`${pagination.total} log entries`}>
          <div className="audit-filters">
            <Select value={filters.action}
              onChange={(e) => setFilters({ ...filters, action: e.target.value })} style={{ minWidth: 180 }}>
              <option value="">All actions</option>
              {actions.map((a) => <option key={a} value={a}>{a}</option>)}
            </Select>
            <input type="text" className="input" placeholder="Search by email or target…"
              value={filters.search}
              onChange={(e) => setFilters({ ...filters, search: e.target.value })} style={{ minWidth: 200 }} />
            <input type="date" className="input" aria-label="From date"
              value={filters.from_date}
              onChange={(e) => setFilters({ ...filters, from_date: e.target.value })} />
            <input type="date" className="input" aria-label="To date"
              value={filters.to_date}
              onChange={(e) => setFilters({ ...filters, to_date: e.target.value })} />
            {(filters.action || filters.search || filters.from_date || filters.to_date) && (
              <Button variant="ghost" size="sm"
                onClick={() => setFilters({ action: "", search: "", from_date: "", to_date: "" })}>
                Clear
              </Button>
            )}
          </div>
        </CardHeader>
        <CardBody>
          {loading ? (
            <SkeletonTable rows={8} cols={6} />
          ) : logs.length === 0 ? (
            <EmptyState icon="document" title="No audit logs found"
              subtitle="Try widening your filters or date range." />
          ) : (
            <>
              <div className="table-scroll">
                <table className="audit-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th><th>Action</th><th>Actor</th>
                      <th>Target</th><th>Details</th><th>IP Address</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => (
                      <tr key={log.id}>
                        <td className="font-mono text-sm">{formatDate(log.created_at)}</td>
                        <td><Badge variant={actionColors[log.action] || "default"}>{log.action}</Badge></td>
                        <td>{log.actor_email || "-"}</td>
                        <td>{log.target_label || "-"}</td>
                        <td className="details-cell">{log.details ? <code>{JSON.stringify(log.details)}</code> : "-"}</td>
                        <td className="font-mono text-muted">{log.ip_address || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={pagination.page} pages={pagination.pages} total={pagination.total}
                pageSize={pagination.page_size} onPageChange={fetchLogs} />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
