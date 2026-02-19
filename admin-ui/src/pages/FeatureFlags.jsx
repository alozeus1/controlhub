import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./FeatureFlags.css";

const EMPTY_FORM = {
  project: "",
  name: "",
  key: "",
  description: "",
  flag_type: "boolean",
  value: false,
  is_enabled: false,
};

function generateKey(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
}

export default function FeatureFlags() {
  const toast = useToast();

  const [flags, setFlags] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [projectFilter, setProjectFilter] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingFlag, setEditingFlag] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({ ...EMPTY_FORM });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (projectFilter) params.append("project", projectFilter);

      const [flagsRes, projectsRes] = await Promise.all([
        api.get(`/admin/feature-flags?${params}`),
        api.get("/admin/feature-flags/projects"),
      ]);
      setFlags(flagsRes.data.items || flagsRes.data || []);
      setProjects(projectsRes.data.projects || projectsRes.data || []);
    } catch {
      toast.error("Failed to load feature flags");
    } finally {
      setLoading(false);
    }
  }, [projectFilter, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggle = async (flag) => {
    try {
      await api.post(`/admin/feature-flags/${flag.id}/toggle`);
      toast.success(`Flag "${flag.name}" ${flag.is_enabled ? "disabled" : "enabled"}`);
      fetchData();
    } catch {
      toast.error("Failed to toggle flag");
    }
  };

  const openCreate = () => {
    setEditingFlag(null);
    setFormData({ ...EMPTY_FORM });
    setShowModal(true);
  };

  const openEdit = (flag) => {
    setEditingFlag(flag);
    setFormData({
      project: flag.project || "",
      name: flag.name || "",
      key: flag.key || "",
      description: flag.description || "",
      flag_type: flag.flag_type || "boolean",
      value: flag.value ?? false,
      is_enabled: flag.is_enabled || false,
    });
    setShowModal(true);
  };

  const handleNameChange = (name) => {
    const updates = { ...formData, name };
    if (!editingFlag) {
      updates.key = generateKey(name);
    }
    setFormData(updates);
  };

  const handleSubmit = async () => {
    if (!formData.name || !formData.key || !formData.project) {
      toast.error("Project, name, and key are required");
      return;
    }
    try {
      setSaving(true);
      const payload = { ...formData };
      if (payload.flag_type === "boolean") {
        payload.value = !!payload.value;
      } else {
        payload.value = Number(payload.value) || 0;
      }
      if (editingFlag) {
        await api.patch(`/admin/feature-flags/${editingFlag.id}`, payload);
        toast.success("Flag updated");
      } else {
        await api.post("/admin/feature-flags", payload);
        toast.success("Flag created");
      }
      setShowModal(false);
      fetchData();
    } catch {
      toast.error("Failed to save flag");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      setSaving(true);
      await api.delete(`/admin/feature-flags/${deleteConfirm.id}`);
      toast.success("Flag deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch {
      toast.error("Failed to delete flag");
    } finally {
      setSaving(false);
    }
  };

  if (loading && flags.length === 0) {
    return <PageLoader message="Loading feature flags..." />;
  }

  return (
    <div className="featureflags-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Feature Flags</h1>
          <p className="page-subtitle">Manage feature toggles across projects</p>
        </div>
        <div className="page-header-actions">
          <Button variant="primary" onClick={openCreate}>New Flag</Button>
        </div>
      </div>

      {/* Project filter tabs */}
      <div className="project-tabs">
        <button
          className={`project-tab ${projectFilter === "" ? "active" : ""}`}
          onClick={() => setProjectFilter("")}
        >
          All
        </button>
        {projects.map((p) => (
          <button
            key={p}
            className={`project-tab ${projectFilter === p ? "active" : ""}`}
            onClick={() => setProjectFilter(p)}
          >
            {p}
          </button>
        ))}
      </div>

      <Card>
        <CardBody>
          {flags.length === 0 ? (
            <div className="empty-state">
              <p className="empty-state-title">No feature flags found</p>
              <p className="empty-state-text">Create a feature flag to get started</p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Key</th>
                    <th>Project</th>
                    <th>Description</th>
                    <th>Type</th>
                    <th>Enabled</th>
                    <th>Created By</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {flags.map((flag) => (
                    <tr key={flag.id}>
                      <td className="flag-name">{flag.name}</td>
                      <td><code className="flag-key">{flag.key}</code></td>
                      <td><Badge variant="default">{flag.project}</Badge></td>
                      <td className="flag-desc">{flag.description || "-"}</td>
                      <td>
                        <Badge variant={flag.flag_type === "percentage" ? "warning" : "info"}>
                          {flag.flag_type}
                        </Badge>
                      </td>
                      <td>
                        <button
                          className={`toggle-switch ${flag.is_enabled ? "toggle-on" : "toggle-off"}`}
                          onClick={() => handleToggle(flag)}
                          title={flag.is_enabled ? "Click to disable" : "Click to enable"}
                        >
                          <span className="toggle-knob" />
                          <span className="toggle-label">{flag.is_enabled ? "ON" : "OFF"}</span>
                        </button>
                      </td>
                      <td className="text-muted">{flag.created_by || "-"}</td>
                      <td>
                        <div className="action-buttons">
                          <Button variant="ghost" size="sm" onClick={() => openEdit(flag)}>Edit</Button>
                          <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(flag)}>Delete</Button>
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

      {/* SDK Usage */}
      <Card>
        <CardHeader title="SDK Usage" />
        <CardBody>
          <p className="sdk-text">
            Consume feature flags in your application via the SDK endpoint:
          </p>
          <pre className="sdk-code">{`fetch('/admin/feature-flags/sdk/{project}?env=production')
  .then(res => res.json())
  .then(flags => {
    // flags = { "flag_key": { enabled: true, value: true }, ... }
    if (flags.my_feature?.enabled) {
      // Feature is enabled
    }
  });`}</pre>
        </CardBody>
      </Card>

      {/* Create / Edit Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={editingFlag ? "Edit Flag" : "New Flag"}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)} disabled={saving}>Cancel</Button>
            <Button variant="primary" onClick={handleSubmit} loading={saving}>
              {editingFlag ? "Update" : "Create"}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <Input
            label="Project"
            placeholder="e.g. web-app"
            value={formData.project}
            onChange={(e) => setFormData({ ...formData, project: e.target.value })}
            required
          />
          <Input
            label="Name"
            placeholder="e.g. Dark Mode"
            value={formData.name}
            onChange={(e) => handleNameChange(e.target.value)}
            required
          />
          <Input
            label="Key"
            placeholder="e.g. dark_mode"
            value={formData.key}
            onChange={(e) => setFormData({ ...formData, key: e.target.value })}
            required
          />
          <TextArea
            label="Description"
            placeholder="What does this flag control?"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />
          <Select
            label="Type"
            value={formData.flag_type}
            onChange={(e) => setFormData({ ...formData, flag_type: e.target.value, value: e.target.value === "boolean" ? false : 0 })}
          >
            <option value="boolean">Boolean</option>
            <option value="percentage">Percentage</option>
          </Select>
          {formData.flag_type === "percentage" ? (
            <div className="slider-field">
              <label className="input-label">Value: {formData.value}%</label>
              <input
                type="range"
                min="0"
                max="100"
                value={formData.value}
                onChange={(e) => setFormData({ ...formData, value: Number(e.target.value) })}
                className="percentage-slider"
              />
            </div>
          ) : (
            <div className="checkbox-field">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={!!formData.value}
                  onChange={(e) => setFormData({ ...formData, value: e.target.checked })}
                />
                <span>Default Value (On)</span>
              </label>
            </div>
          )}
          <div className="checkbox-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={formData.is_enabled}
                onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
              />
              <span>Enabled</span>
            </label>
          </div>
        </div>
      </Modal>

      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Flag"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This may affect running applications.`}
        confirmText="Delete"
        loading={saving}
      />
    </div>
  );
}
