import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Secrets.css";

const ENV_OPTIONS = [
  { value: "", label: "All Environments" },
  { value: "dev", label: "Development" },
  { value: "staging", label: "Staging" },
  { value: "prod", label: "Production" },
  { value: "all", label: "All Envs" },
];

export default function Secrets() {
  const toast = useToast();

  const [secrets, setSecrets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [revealModal, setRevealModal] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [filters, setFilters] = useState({ project: "", environment: "" });
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    project: "",
    environment: "dev",
    value: "",
    tags: "",
    expires_at: "",
  });

  const fetchSecrets = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.project) params.append("project", filters.project);
      if (filters.environment) params.append("environment", filters.environment);

      const res = await api.get(`/admin/secrets?${params}`);
      setSecrets(res.data.items || res.data || []);
    } catch {
      toast.error("Failed to load secrets");
    } finally {
      setLoading(false);
    }
  }, [filters, toast]);

  useEffect(() => {
    fetchSecrets();
  }, [fetchSecrets]);

  const resetForm = () => {
    setFormData({
      name: "",
      description: "",
      project: "",
      environment: "dev",
      value: "",
      tags: "",
      expires_at: "",
    });
  };

  const handleCreate = async () => {
    if (!formData.name.trim() || !formData.value.trim()) {
      toast.error("Name and value are required");
      return;
    }

    try {
      setSaving(true);
      const payload = {
        name: formData.name,
        description: formData.description,
        project: formData.project,
        environment: formData.environment,
        value: formData.value,
        tags: formData.tags
          ? formData.tags.split(",").map((t) => t.trim()).filter(Boolean)
          : [],
      };
      if (formData.expires_at) payload.expires_at = formData.expires_at;

      await api.post("/admin/secrets", payload);
      toast.success("Secret created");
      setShowCreateModal(false);
      resetForm();
      fetchSecrets();
    } catch (err) {
      toast.error(err.message || "Failed to create secret");
    } finally {
      setSaving(false);
    }
  };

  const handleReveal = async (secret) => {
    try {
      setRevealing(true);
      const res = await api.post(`/admin/secrets/${secret.id}/reveal`);
      setRevealModal({ ...secret, revealedValue: res.data.value });
    } catch (err) {
      toast.error(err.message || "Failed to reveal secret");
    } finally {
      setRevealing(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;
    try {
      setSaving(true);
      await api.delete(`/admin/secrets/${deleteConfirm.id}`);
      toast.success("Secret deleted");
      setDeleteConfirm(null);
      fetchSecrets();
    } catch (err) {
      toast.error(err.message || "Failed to delete secret");
    } finally {
      setSaving(false);
    }
  };

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString();
  };

  const getExpiryBadge = (expiresAt) => {
    if (!expiresAt) return <Badge variant="default">No expiry</Badge>;
    const now = new Date();
    const exp = new Date(expiresAt);
    const daysLeft = Math.ceil((exp - now) / (1000 * 60 * 60 * 24));
    if (daysLeft < 0) return <Badge variant="error">Expired</Badge>;
    if (daysLeft <= 30) return <Badge variant="warning">Expiring soon</Badge>;
    return <Badge variant="success">OK</Badge>;
  };

  if (loading && secrets.length === 0) {
    return <PageLoader message="Loading secrets..." />;
  }

  return (
    <div className="secrets-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Secrets Manager</h1>
          <p className="page-subtitle">Manage application secrets and credentials</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreateModal(true)}>
          + Add Secret
        </Button>
      </div>

      <Card>
        <CardHeader
          title="Secrets"
          action={
            <div className="filters">
              <Input
                placeholder="Filter by project..."
                value={filters.project}
                onChange={(e) => handleFilterChange("project", e.target.value)}
                style={{ width: 200 }}
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
            </div>
          }
        />
        <CardBody>
          {secrets.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔐</div>
              <p className="empty-state-title">No secrets found</p>
              <p className="empty-state-text">Add your first secret to get started</p>
              <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                Add Secret
              </Button>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Project</th>
                    <th>Environment</th>
                    <th>Tags</th>
                    <th>Expires</th>
                    <th>Created By</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {secrets.map((secret) => (
                    <tr key={secret.id}>
                      <td className="secret-name">{secret.name}</td>
                      <td className="text-muted">{secret.project || "-"}</td>
                      <td>
                        <Badge variant="default">{secret.environment}</Badge>
                      </td>
                      <td className="secret-tags">
                        {secret.tags?.length > 0
                          ? secret.tags.map((tag) => (
                              <span key={tag} className="tag-chip">{tag}</span>
                            ))
                          : "-"}
                      </td>
                      <td>{getExpiryBadge(secret.expires_at)}</td>
                      <td className="text-muted">{secret.created_by || "-"}</td>
                      <td>
                        <div className="action-buttons">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleReveal(secret)}
                            disabled={revealing}
                          >
                            Reveal
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="danger"
                            onClick={() => setDeleteConfirm(secret)}
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Create Secret Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
        title="Add Secret"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-stack">
          <div className="form-row">
            <Input
              label="Name *"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g., DATABASE_PASSWORD"
            />
            <Input
              label="Project"
              value={formData.project}
              onChange={(e) => setFormData({ ...formData, project: e.target.value })}
              placeholder="e.g., my-app"
            />
          </div>
          <Input
            label="Description"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="What is this secret for?"
          />
          <div className="form-row">
            <Select
              label="Environment *"
              value={formData.environment}
              onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
            >
              <option value="dev">Development</option>
              <option value="staging">Staging</option>
              <option value="prod">Production</option>
              <option value="all">All Environments</option>
            </Select>
            <Input
              label="Expires At"
              type="date"
              value={formData.expires_at}
              onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
            />
          </div>
          <Input
            label="Value *"
            type="password"
            value={formData.value}
            onChange={(e) => setFormData({ ...formData, value: e.target.value })}
            placeholder="Enter secret value"
          />
          <Input
            label="Tags (comma-separated)"
            value={formData.tags}
            onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
            placeholder="e.g., database, credentials, api"
          />
        </div>
      </Modal>

      {/* Reveal Secret Modal */}
      <Modal
        isOpen={!!revealModal}
        onClose={() => setRevealModal(null)}
        title="Secret Value"
        size="md"
        footer={
          <Button variant="secondary" onClick={() => setRevealModal(null)}>Close</Button>
        }
      >
        {revealModal && (
          <div className="reveal-content">
            <div className="detail-row">
              <label>Name</label>
              <span>{revealModal.name}</span>
            </div>
            <div className="detail-row">
              <label>Value</label>
              <code className="revealed-value">{revealModal.revealedValue}</code>
            </div>
          </div>
        )}
      </Modal>

      {/* Delete Confirm */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Secret"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
        confirmText="Delete"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
