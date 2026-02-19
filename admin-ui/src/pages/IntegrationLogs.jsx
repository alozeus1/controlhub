import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./IntegrationLogs.css";

export default function IntegrationLogs() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [integration, setIntegration] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [intRes, logsRes] = await Promise.all([
        api.get(`/admin/integrations/${id}`),
        api.get(`/admin/integrations/${id}/logs?page=${page}&page_size=50${statusFilter ? `&status=${statusFilter}` : ""}`),
      ]);
      setIntegration(intRes.data);
      setLogs(logsRes.data.items || []);
      setTotalPages(logsRes.data.pages || 1);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Integrations feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load integration logs");
      navigate("/ui/integrations");
    } finally {
      setLoading(false);
    }
  }, [id, page, statusFilter, toast, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const getStatusBadge = (status) => {
    const colors = {
      success: "success",
      failed: "error",
      skipped: "default",
    };
    return <Badge variant={colors[status] || "default"}>{status}</Badge>;
  };

  if (loading && !integration) {
    return <PageLoader message="Loading integration logs..." />;
  }

  if (!integration) {
    return null;
  }

  return (
    <div className="integration-logs-page">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            <Link to="/ui/integrations">Integrations</Link>
            <span>/</span>
            <span>{integration.name}</span>
            <span>/</span>
            <span>Logs</span>
          </div>
          <h1 className="page-title">{integration.name} - Delivery Logs</h1>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Delivery Logs"
          action={
            <Select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Statuses</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
              <option value="skipped">Skipped</option>
            </Select>
          }
        />
        <CardBody>
          {logs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📋</div>
              <p className="empty-state-title">No logs yet</p>
              <p className="empty-state-text">Delivery logs will appear here when events are sent</p>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Event Type</th>
                    <th>Status</th>
                    <th>Response Code</th>
                    <th>Duration</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td className="timestamp">{formatDate(log.created_at)}</td>
                      <td className="event-type">{log.event_type}</td>
                      <td>{getStatusBadge(log.status)}</td>
                      <td className="response-code">
                        {log.response_code ? (
                          <code className={log.response_code < 400 ? "success" : "error"}>
                            {log.response_code}
                          </code>
                        ) : (
                          "-"
                        )}
                      </td>
                      <td className="duration">
                        {log.duration_ms ? `${log.duration_ms}ms` : "-"}
                      </td>
                      <td className="error-cell">
                        {log.error_message && (
                          <span className="error-message" title={log.error_message}>
                            {log.error_message.length > 50
                              ? log.error_message.substring(0, 50) + "..."
                              : log.error_message}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {totalPages > 1 && (
                <div className="pagination">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    Previous
                  </Button>
                  <span className="page-info">
                    Page {page} of {totalPages}
                  </span>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                  >
                    Next
                  </Button>
                </div>
              )}
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
