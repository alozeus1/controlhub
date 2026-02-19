import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Select } from "../components/ui/Input";
import { TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./IncidentDetail.css";

const STATUS_OPTIONS = ["open", "investigating", "resolved", "closed"];

export default function IncidentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [updateText, setUpdateText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);

  const fetchIncident = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/incidents/${id}`);
      setIncident(res.data);
    } catch {
      toast.error("Failed to load incident");
      navigate("/ui/incidents");
    } finally {
      setLoading(false);
    }
  }, [id, toast, navigate]);

  useEffect(() => {
    fetchIncident();
  }, [fetchIncident]);

  const handlePostUpdate = async () => {
    if (!updateText.trim()) {
      toast.error("Update text is required");
      return;
    }
    try {
      setSubmitting(true);
      await api.post(`/admin/incidents/${id}/updates`, { message: updateText });
      toast.success("Update posted");
      setUpdateText("");
      fetchIncident();
    } catch (err) {
      toast.error(err.message || "Failed to post update");
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusChange = async (newStatus) => {
    try {
      setStatusUpdating(true);
      await api.patch(`/admin/incidents/${id}`, { status: newStatus });
      toast.success(`Status updated to ${newStatus}`);
      fetchIncident();
    } catch (err) {
      toast.error(err.message || "Failed to update status");
    } finally {
      setStatusUpdating(false);
    }
  };

  const getSeverityBadge = (severity) => {
    const variants = { p1: "error", p2: "warning", p3: "default", p4: "default" };
    const labels = { p1: "P1 - Critical", p2: "P2 - High", p3: "P3 - Medium", p4: "P4 - Low" };
    return <Badge variant={variants[severity] || "default"}>{labels[severity] || severity}</Badge>;
  };

  const getStatusBadge = (status) => {
    const variants = {
      open: "error",
      investigating: "warning",
      resolved: "success",
      closed: "default",
    };
    return <Badge variant={variants[status] || "default"}>{status}</Badge>;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const formatDuration = () => {
    if (!incident) return "-";
    const start = new Date(incident.started_at || incident.created_at);
    const end = incident.resolved_at ? new Date(incident.resolved_at) : new Date();
    const diffMs = end - start;
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${minutes}m`;
  };

  if (loading) {
    return <PageLoader message="Loading incident..." />;
  }

  if (!incident) return null;

  return (
    <div className="incident-detail-page">
      <div className="page-header">
        <div>
          <button className="back-link" onClick={() => navigate("/ui/incidents")}>
            &larr; Back to Incidents
          </button>
          <h1 className="page-title">{incident.title}</h1>
          <p className="page-subtitle">Incident #{incident.id}</p>
        </div>
      </div>

      <div className="incident-detail-layout">
        {/* Main Content */}
        <div className="incident-main">
          {/* Description */}
          {incident.description && (
            <Card>
              <CardBody>
                <h3 className="section-title">Description</h3>
                <p className="incident-description">{incident.description}</p>
              </CardBody>
            </Card>
          )}

          {/* Timeline */}
          <Card>
            <CardBody>
              <h3 className="section-title">Timeline</h3>
              {incident.updates?.length > 0 ? (
                <div className="timeline">
                  {incident.updates.map((update, idx) => (
                    <div key={idx} className="timeline-item">
                      <div className="timeline-dot" />
                      <div className="timeline-content">
                        <div className="timeline-time">{formatDate(update.created_at)}</div>
                        <div className="timeline-message">{update.message}</div>
                        {update.author && (
                          <div className="timeline-author">- {update.author}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No updates yet</p>
              )}

              {/* Post Update Form */}
              <div className="update-form">
                <h4 className="update-form-title">Post Update</h4>
                <TextArea
                  value={updateText}
                  onChange={(e) => setUpdateText(e.target.value)}
                  placeholder="Describe the latest status or action taken..."
                  rows={3}
                />
                <Button
                  variant="primary"
                  onClick={handlePostUpdate}
                  loading={submitting}
                  disabled={!updateText.trim()}
                >
                  Post Update
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="incident-sidebar">
          <Card>
            <CardBody>
              <h3 className="section-title">Details</h3>
              <div className="detail-list">
                <div className="detail-item">
                  <span className="detail-label">Status</span>
                  <div className="detail-value">{getStatusBadge(incident.status)}</div>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Severity</span>
                  <div className="detail-value">{getSeverityBadge(incident.severity)}</div>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Commander</span>
                  <div className="detail-value">{incident.commander || "-"}</div>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Started</span>
                  <div className="detail-value">
                    {formatDate(incident.started_at || incident.created_at)}
                  </div>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Duration</span>
                  <div className="detail-value">{formatDuration()}</div>
                </div>
                {incident.affected_services?.length > 0 && (
                  <div className="detail-item">
                    <span className="detail-label">Services</span>
                    <div className="detail-value services-list">
                      {incident.affected_services.map((s) => (
                        <span key={s} className="service-tag">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Status Update */}
              <div className="status-update">
                <span className="detail-label">Update Status</span>
                <Select
                  value={incident.status}
                  onChange={(e) => handleStatusChange(e.target.value)}
                  disabled={statusUpdating}
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </option>
                  ))}
                </Select>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
