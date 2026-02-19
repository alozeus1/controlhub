import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Incidents.css";

const STATUS_TABS = ["all", "open", "investigating", "resolved", "closed"];

const SEVERITY_OPTIONS = [
  { value: "", label: "All Severities" },
  { value: "p1", label: "P1 - Critical" },
  { value: "p2", label: "P2 - High" },
  { value: "p3", label: "P3 - Medium" },
  { value: "p4", label: "P4 - Low" },
];

export default function Incidents() {
  const navigate = useNavigate();
  const toast = useToast();

  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeStatus, setActiveStatus] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [stats, setStats] = useState({ total: 0, open: 0, p1: 0, p2: 0 });
  const [formData, setFormData] = useState({
    title: "",
    description: "",
    severity: "p3",
    affected_services: "",
    commander: "",
  });

  const fetchIncidents = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (activeStatus !== "all") params.append("status", activeStatus);
      if (severityFilter) params.append("severity", severityFilter);

      const res = await api.get(`/admin/incidents?${params}`);
      const items = res.data.items || res.data || [];
      setIncidents(items);

      // Calculate stats
      const allIncidents = items;
      setStats({
        total: allIncidents.length,
        open: allIncidents.filter((i) => i.status === "open" || i.status === "investigating").length,
        p1: allIncidents.filter((i) => i.severity === "p1").length,
        p2: allIncidents.filter((i) => i.severity === "p2").length,
      });
    } catch {
      toast.error("Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, [activeStatus, severityFilter, toast]);

  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

  const resetForm = () => {
    setFormData({
      title: "",
      description: "",
      severity: "p3",
      affected_services: "",
      commander: "",
    });
  };

  const handleCreate = async () => {
    if (!formData.title.trim()) {
      toast.error("Title is required");
      return;
    }
    try {
      setSaving(true);
      const payload = {
        title: formData.title,
        description: formData.description,
        severity: formData.severity,
        affected_services: formData.affected_services
          ? formData.affected_services.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        commander: formData.commander,
      };
      await api.post("/admin/incidents", payload);
      toast.success("Incident created");
      setShowCreateModal(false);
      resetForm();
      fetchIncidents();
    } catch (err) {
      toast.error(err.message || "Failed to create incident");
    } finally {
      setSaving(false);
    }
  };

  const formatDuration = (incident) => {
    const start = new Date(incident.started_at || incident.created_at);
    const end = incident.resolved_at ? new Date(incident.resolved_at) : new Date();
    const diffMs = end - start;
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

    if (incident.status === "resolved" || incident.status === "closed") {
      return `${hours}h ${minutes}m`;
    }
    return `ongoing ${hours}h ${minutes}m`;
  };

  const getSeverityBadge = (severity) => {
    const variants = { p1: "error", p2: "warning", p3: "default", p4: "default" };
    const labels = { p1: "P1", p2: "P2", p3: "P3", p4: "P4" };
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

  if (loading && incidents.length === 0) {
    return <PageLoader message="Loading incidents..." />;
  }

  return (
    <div className="incidents-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Incident Management</h1>
          <p className="page-subtitle">Track and manage service incidents</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreateModal(true)}>
          + Create Incident
        </Button>
      </div>

      {/* Stats Row */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">Total</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-value">{stats.open}</div>
          <div className="stat-label">Open</div>
        </div>
        <div className="stat-card error">
          <div className="stat-value">{stats.p1}</div>
          <div className="stat-label">P1 Critical</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.p2}</div>
          <div className="stat-label">P2 High</div>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Incidents"
          action={
            <Select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
            >
              {SEVERITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          }
        />
        <CardBody>
          {/* Status Tabs */}
          <div className="status-tabs">
            {STATUS_TABS.map((status) => (
              <button
                key={status}
                className={`status-tab ${activeStatus === status ? "active" : ""}`}
                onClick={() => setActiveStatus(status)}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>

          {incidents.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🚨</div>
              <p className="empty-state-title">No incidents found</p>
              <p className="empty-state-text">No incidents match the current filters</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Affected Services</th>
                    <th>Commander</th>
                    <th>Started</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((incident) => (
                    <tr
                      key={incident.id}
                      className="clickable-row"
                      onClick={() => navigate(`/ui/incidents/${incident.id}`)}
                    >
                      <td className="incident-id">#{incident.id}</td>
                      <td className="incident-title">{incident.title}</td>
                      <td>{getSeverityBadge(incident.severity)}</td>
                      <td>{getStatusBadge(incident.status)}</td>
                      <td className="services-cell">
                        {incident.affected_services?.length > 0
                          ? incident.affected_services.map((s) => (
                              <span key={s} className="service-tag">{s}</span>
                            ))
                          : "-"}
                      </td>
                      <td className="text-muted">{incident.commander || "-"}</td>
                      <td className="timestamp">
                        {formatDate(incident.started_at || incident.created_at)}
                      </td>
                      <td className="duration">{formatDuration(incident)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Create Incident Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
        title="Create Incident"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Title *"
            value={formData.title}
            onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            placeholder="e.g., API gateway latency spike"
          />
          <Input
            label="Description"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Describe the incident"
          />
          <div className="form-row">
            <Select
              label="Severity *"
              value={formData.severity}
              onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
            >
              <option value="p1">P1 - Critical</option>
              <option value="p2">P2 - High</option>
              <option value="p3">P3 - Medium</option>
              <option value="p4">P4 - Low</option>
            </Select>
            <Input
              label="Commander"
              value={formData.commander}
              onChange={(e) => setFormData({ ...formData, commander: e.target.value })}
              placeholder="Incident commander name"
            />
          </div>
          <Input
            label="Affected Services (comma-separated)"
            value={formData.affected_services}
            onChange={(e) => setFormData({ ...formData, affected_services: e.target.value })}
            placeholder="e.g., api-gateway, auth-service, database"
          />
        </div>
      </Modal>
    </div>
  );
}
