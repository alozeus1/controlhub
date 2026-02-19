import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Deployments.css";

const ENV_OPTIONS = [
  { value: "", label: "All Environments" },
  { value: "dev", label: "Development" },
  { value: "staging", label: "Staging" },
  { value: "prod", label: "Production" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "success", label: "Success" },
  { value: "failed", label: "Failed" },
  { value: "in_progress", label: "In Progress" },
  { value: "rolled_back", label: "Rolled Back" },
];

export default function Deployments() {
  const toast = useToast();

  const [deployments, setDeployments] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [filters, setFilters] = useState({ service: "", environment: "", status: "" });
  const [formData, setFormData] = useState({
    service_name: "",
    version: "",
    environment: "dev",
    status: "success",
    is_rollback: false,
    notes: "",
    pipeline_url: "",
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page, page_size: 25 });
      if (filters.service) params.append("service_name", filters.service);
      if (filters.environment) params.append("environment", filters.environment);
      if (filters.status) params.append("status", filters.status);

      const [deploymentsRes, statsRes] = await Promise.all([
        api.get(`/admin/deployments?${params}`),
        api.get("/admin/deployments/stats"),
      ]);
      setDeployments(deploymentsRes.data.items || deploymentsRes.data || []);
      setTotalPages(deploymentsRes.data.pages || 1);
      setStats(statsRes.data);
    } catch {
      toast.error("Failed to load deployments");
    } finally {
      setLoading(false);
    }
  }, [page, filters, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const resetForm = () => {
    setFormData({
      service_name: "",
      version: "",
      environment: "dev",
      status: "success",
      is_rollback: false,
      notes: "",
      pipeline_url: "",
    });
  };

  const handleCreate = async () => {
    if (!formData.service_name.trim() || !formData.version.trim()) {
      toast.error("Service name and version are required");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/deployments", formData);
      toast.success("Deployment logged");
      setShowCreateModal(false);
      resetForm();
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to log deployment");
    } finally {
      setSaving(false);
    }
  };

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const getStatusBadge = (status) => {
    const variants = {
      success: "success",
      failed: "error",
      in_progress: "info",
      rolled_back: "warning",
    };
    return <Badge variant={variants[status] || "default"}>{status?.replace("_", " ")}</Badge>;
  };

  const getEnvBadge = (env) => {
    const variants = { prod: "error", staging: "warning", dev: "default" };
    return <Badge variant={variants[env] || "default"}>{env}</Badge>;
  };

  const getRowClass = (deployment) => {
    if (deployment.status === "failed") return "row-failed";
    if (deployment.status === "rolled_back" || deployment.is_rollback) return "row-rollback";
    return "";
  };

  if (loading && deployments.length === 0) {
    return <PageLoader message="Loading deployments..." />;
  }

  return (
    <div className="deployments-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Deployment Tracker</h1>
          <p className="page-subtitle">Track service deployments across environments</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreateModal(true)}>
          + Log Deployment
        </Button>
      </div>

      {/* Stats Row */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value">{stats.total ?? 0}</div>
            <div className="stat-label">Total Deployments</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">
              {stats.success_rate != null ? `${Math.round(stats.success_rate)}%` : "-"}
            </div>
            <div className="stat-label">Success Rate</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.unique_services ?? 0}</div>
            <div className="stat-label">Unique Services</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.environments ?? 0}</div>
            <div className="stat-label">Environments</div>
          </div>
        </div>
      )}

      <Card>
        <CardHeader
          title="Deployments"
          action={
            <div className="filters">
              <Input
                placeholder="Service name..."
                value={filters.service}
                onChange={(e) => handleFilterChange("service", e.target.value)}
                style={{ width: 180 }}
              />
              <Select
                value={filters.environment}
                onChange={(e) => handleFilterChange("environment", e.target.value)}
              >
                {ENV_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
              <Select
                value={filters.status}
                onChange={(e) => handleFilterChange("status", e.target.value)}
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
          {deployments.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🚀</div>
              <p className="empty-state-title">No deployments found</p>
              <p className="empty-state-text">Log your first deployment to start tracking</p>
              <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                Log Deployment
              </Button>
            </div>
          ) : (
            <>
              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Service</th>
                      <th>Version</th>
                      <th>Environment</th>
                      <th>Status</th>
                      <th>Rollback</th>
                      <th>Deployed By</th>
                      <th>Deployed At</th>
                      <th>Pipeline</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deployments.map((dep) => (
                      <tr key={dep.id} className={getRowClass(dep)}>
                        <td className="service-name">{dep.service_name}</td>
                        <td className="version-cell">
                          <code>{dep.version}</code>
                        </td>
                        <td>{getEnvBadge(dep.environment)}</td>
                        <td>{getStatusBadge(dep.status)}</td>
                        <td className="rollback-cell">
                          {dep.is_rollback ? (
                            <span className="rollback-icon" title="Rollback">&#10226;</span>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td className="text-muted">{dep.deployed_by || "-"}</td>
                        <td className="timestamp">{formatDate(dep.deployed_at || dep.created_at)}</td>
                        <td>
                          {dep.pipeline_url ? (
                            <a
                              href={dep.pipeline_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="pipeline-link"
                            >
                              View
                            </a>
                          ) : (
                            "-"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

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

      {/* Log Deployment Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
        title="Log Deployment"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Log</Button>
          </>
        }
      >
        <div className="form-stack">
          <div className="form-row">
            <Input
              label="Service Name *"
              value={formData.service_name}
              onChange={(e) => setFormData({ ...formData, service_name: e.target.value })}
              placeholder="e.g., api-gateway"
            />
            <Input
              label="Version *"
              value={formData.version}
              onChange={(e) => setFormData({ ...formData, version: e.target.value })}
              placeholder="e.g., v2.3.1"
            />
          </div>
          <div className="form-row">
            <Select
              label="Environment *"
              value={formData.environment}
              onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
            >
              <option value="dev">Development</option>
              <option value="staging">Staging</option>
              <option value="prod">Production</option>
            </Select>
            <Select
              label="Status *"
              value={formData.status}
              onChange={(e) => setFormData({ ...formData, status: e.target.value })}
            >
              <option value="success">Success</option>
              <option value="failed">Failed</option>
              <option value="in_progress">In Progress</option>
              <option value="rolled_back">Rolled Back</option>
            </Select>
          </div>
          <Input
            label="Notes"
            value={formData.notes}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            placeholder="Any notes about this deployment"
          />
          <Input
            label="Pipeline URL"
            value={formData.pipeline_url}
            onChange={(e) => setFormData({ ...formData, pipeline_url: e.target.value })}
            placeholder="e.g., https://ci.example.com/builds/123"
          />
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={formData.is_rollback}
              onChange={(e) => setFormData({ ...formData, is_rollback: e.target.checked })}
            />
            This is a rollback deployment
          </label>
        </div>
      </Modal>
    </div>
  );
}
