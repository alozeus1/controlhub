import { useEffect, useState, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Alerts.css";

const SEVERITY_OPTIONS = [
  { value: "", label: "All Severities" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "delivered", label: "Delivered" },
  { value: "partial", label: "Partial" },
  { value: "failed", label: "Failed" },
  { value: "pending", label: "Pending" },
];

export default function Alerts() {
  const navigate = useNavigate();
  const toast = useToast();

  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [filters, setFilters] = useState({ severity: "", delivery_status: "" });
  const [selectedAlert, setSelectedAlert] = useState(null);

  const fetchAlerts = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page, page_size: 25 });
      if (filters.severity) params.append("severity", filters.severity);
      if (filters.delivery_status) params.append("delivery_status", filters.delivery_status);

      const res = await api.get(`/admin/alerts?${params}`);
      setAlerts(res.data.items || []);
      setTotalPages(res.data.pages || 1);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Notifications feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load alerts");
    } finally {
      setLoading(false);
    }
  }, [page, filters, toast, navigate]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const getSeverityBadge = (severity) => {
    const colors = {
      low: "default",
      medium: "warning",
      high: "error",
      critical: "error",
    };
    return <Badge variant={colors[severity] || "default"}>{severity}</Badge>;
  };

  const getStatusBadge = (status) => {
    const colors = {
      delivered: "success",
      partial: "warning",
      failed: "error",
      pending: "default",
    };
    return <Badge variant={colors[status] || "default"}>{status}</Badge>;
  };

  const formatEventType = (type) => {
    return type.replace(".", " → ").replace(/_/g, " ");
  };

  if (loading && alerts.length === 0) {
    return <PageLoader message="Loading alerts..." />;
  }

  return (
    <div className="alerts-page">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            <Link to="/ui/alert-rules">Alert Rules</Link>
            <span>/</span>
            <span>Alert History</span>
          </div>
          <h1 className="page-title">Alert History</h1>
          <p className="page-subtitle">View triggered alerts and delivery status</p>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Alerts"
          action={
            <div className="filters">
              <Select
                value={filters.severity}
                onChange={(e) => handleFilterChange("severity", e.target.value)}
              >
                {SEVERITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
              <Select
                value={filters.delivery_status}
                onChange={(e) => handleFilterChange("delivery_status", e.target.value)}
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            </div>
          }
        />
        <CardBody>
          {alerts.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📭</div>
              <p className="empty-state-title">No alerts found</p>
              <p className="empty-state-text">Alerts will appear here when rules are triggered</p>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Title</th>
                    <th>Event Type</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Rule</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert) => (
                    <tr key={alert.id}>
                      <td className="timestamp">{formatDate(alert.created_at)}</td>
                      <td className="alert-title">{alert.title}</td>
                      <td className="event-type">{formatEventType(alert.event_type)}</td>
                      <td>{getSeverityBadge(alert.severity)}</td>
                      <td>{getStatusBadge(alert.delivery_status)}</td>
                      <td className="rule-name">{alert.rule_name || "-"}</td>
                      <td>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedAlert(alert)}
                        >
                          Details
                        </Button>
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

      {/* Alert Detail Modal */}
      <Modal
        isOpen={!!selectedAlert}
        onClose={() => setSelectedAlert(null)}
        title="Alert Details"
        size="lg"
        footer={
          <Button variant="secondary" onClick={() => setSelectedAlert(null)}>
            Close
          </Button>
        }
      >
        {selectedAlert && (
          <div className="alert-detail">
            <div className="detail-row">
              <label>Title</label>
              <span>{selectedAlert.title}</span>
            </div>
            <div className="detail-row">
              <label>Event Type</label>
              <span className="mono">{selectedAlert.event_type}</span>
            </div>
            <div className="detail-row">
              <label>Severity</label>
              {getSeverityBadge(selectedAlert.severity)}
            </div>
            <div className="detail-row">
              <label>Delivery Status</label>
              {getStatusBadge(selectedAlert.delivery_status)}
            </div>
            <div className="detail-row">
              <label>Triggered At</label>
              <span>{formatDate(selectedAlert.created_at)}</span>
            </div>
            <div className="detail-row">
              <label>Rule</label>
              <span>{selectedAlert.rule_name || "Manual / System"}</span>
            </div>
            {selectedAlert.channels_notified?.length > 0 && (
              <div className="detail-row">
                <label>Channels Notified</label>
                <span>{selectedAlert.channels_notified.length} channel(s)</span>
              </div>
            )}
            {selectedAlert.payload && (
              <div className="detail-section">
                <label>Payload</label>
                <pre className="payload-json">
                  {JSON.stringify(selectedAlert.payload, null, 2)}
                </pre>
              </div>
            )}
            {selectedAlert.delivery_details && (
              <div className="detail-section">
                <label>Delivery Details</label>
                <pre className="payload-json">
                  {JSON.stringify(selectedAlert.delivery_details, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
