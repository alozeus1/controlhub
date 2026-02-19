import { useEffect, useState, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Integrations.css";

const INTEGRATION_TYPES = [
  { value: "webhook", label: "Webhook", icon: "🔗", desc: "Send events to any HTTP endpoint" },
  { value: "siem", label: "SIEM", icon: "🛡️", desc: "Send events in CEF format to SIEM systems" },
];

export default function Integrations() {
  const navigate = useNavigate();
  const toast = useToast();

  const [integrations, setIntegrations] = useState([]);
  const [metadata, setMetadata] = useState({ events: [] });
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editIntegration, setEditIntegration] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    type: "webhook",
    name: "",
    description: "",
    config: {},
    events: null,
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [intRes, metaRes] = await Promise.all([
        api.get("/admin/integrations"),
        api.get("/admin/integrations/metadata"),
      ]);
      setIntegrations(intRes.data.items || []);
      setMetadata(metaRes.data);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Integrations feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }, [toast, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const resetForm = () => {
    setFormData({
      type: "webhook",
      name: "",
      description: "",
      config: {},
      events: null,
    });
  };

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      toast.error("Integration name is required");
      return;
    }
    if (formData.type === "webhook" && !formData.config.url) {
      toast.error("Webhook URL is required");
      return;
    }
    if (formData.type === "siem" && !formData.config.endpoint) {
      toast.error("SIEM endpoint is required");
      return;
    }

    try {
      setSaving(true);
      await api.post("/admin/integrations", formData);
      toast.success("Integration created");
      setShowCreateModal(false);
      resetForm();
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to create integration");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    if (!editIntegration) return;

    try {
      setSaving(true);
      await api.patch(`/admin/integrations/${editIntegration.id}`, {
        name: formData.name,
        description: formData.description,
        config: formData.config,
        events: formData.events,
        is_enabled: formData.is_enabled,
      });
      toast.success("Integration updated");
      setEditIntegration(null);
      resetForm();
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to update integration");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;

    try {
      setSaving(true);
      await api.delete(`/admin/integrations/${deleteConfirm.id}`);
      toast.success("Integration deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to delete integration");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (integration) => {
    try {
      setTestingId(integration.id);
      const res = await api.post(`/admin/integrations/${integration.id}/test`);
      if (res.data.details?.success) {
        toast.success("Test event delivered successfully");
      } else {
        toast.error("Test failed: " + (res.data.details?.error || "Unknown error"));
      }
    } catch (err) {
      toast.error(err.message || "Test failed");
    } finally {
      setTestingId(null);
    }
  };

  const handleToggleEnabled = async (integration) => {
    try {
      await api.patch(`/admin/integrations/${integration.id}`, {
        is_enabled: !integration.is_enabled,
      });
      toast.success(integration.is_enabled ? "Integration disabled" : "Integration enabled");
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to update integration");
    }
  };

  const openEditModal = (integration) => {
    setEditIntegration(integration);
    setFormData({
      type: integration.type,
      name: integration.name,
      description: integration.description || "",
      config: { ...integration.config },
      events: integration.events,
      is_enabled: integration.is_enabled,
    });
  };

  const getTypeInfo = (type) => INTEGRATION_TYPES.find((t) => t.value === type) || {};

  const renderConfigFields = () => {
    switch (formData.type) {
      case "webhook":
        return (
          <>
            <Input
              label="Webhook URL"
              type="url"
              value={formData.config.url || ""}
              onChange={(e) =>
                setFormData({ ...formData, config: { ...formData.config, url: e.target.value } })
              }
              placeholder="https://your-endpoint.com/webhook"
            />
            <Select
              label="Authentication"
              value={formData.config.auth_type || "none"}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  config: { ...formData.config, auth_type: e.target.value },
                })
              }
            >
              <option value="none">None</option>
              <option value="bearer">Bearer Token</option>
              <option value="api_key">API Key Header</option>
            </Select>
            {formData.config.auth_type === "bearer" && (
              <Input
                label="Bearer Token"
                type="password"
                value={formData.config.token || ""}
                onChange={(e) =>
                  setFormData({ ...formData, config: { ...formData.config, token: e.target.value } })
                }
                placeholder="Your bearer token"
              />
            )}
            {formData.config.auth_type === "api_key" && (
              <>
                <Input
                  label="API Key Header Name"
                  value={formData.config.api_key_header || "X-API-Key"}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      config: { ...formData.config, api_key_header: e.target.value },
                    })
                  }
                />
                <Input
                  label="API Key"
                  type="password"
                  value={formData.config.api_key || ""}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      config: { ...formData.config, api_key: e.target.value },
                    })
                  }
                />
              </>
            )}
            <Input
              label="Signing Secret (optional)"
              type="password"
              value={formData.config.secret || ""}
              onChange={(e) =>
                setFormData({ ...formData, config: { ...formData.config, secret: e.target.value } })
              }
              placeholder="HMAC signing secret for payload verification"
            />
          </>
        );
      case "siem":
        return (
          <>
            <Input
              label="SIEM Endpoint"
              type="url"
              value={formData.config.endpoint || ""}
              onChange={(e) =>
                setFormData({ ...formData, config: { ...formData.config, endpoint: e.target.value } })
              }
              placeholder="https://your-siem.com/api/events"
            />
            <Input
              label="Auth Token (optional)"
              type="password"
              value={formData.config.token || ""}
              onChange={(e) =>
                setFormData({ ...formData, config: { ...formData.config, token: e.target.value } })
              }
            />
          </>
        );
      default:
        return null;
    }
  };

  if (loading) {
    return <PageLoader message="Loading integrations..." />;
  }

  return (
    <div className="integrations-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Integrations</h1>
          <p className="page-subtitle">Connect ControlHub to external systems</p>
        </div>
        <div className="header-actions">
          <Link to="/ui/audit-export" className="export-link">
            Audit Export →
          </Link>
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>
            + Add Integration
          </Button>
        </div>
      </div>

      <Card>
        <CardBody>
          {integrations.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔗</div>
              <p className="empty-state-title">No integrations</p>
              <p className="empty-state-text">Connect ControlHub to external systems via webhooks</p>
              <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                Add Integration
              </Button>
            </div>
          ) : (
            <div className="integrations-grid">
              {integrations.map((integration) => {
                const typeInfo = getTypeInfo(integration.type);
                return (
                  <div
                    key={integration.id}
                    className={`integration-card ${!integration.is_enabled ? "disabled" : ""}`}
                  >
                    <div className="integration-header">
                      <span className="integration-icon">{typeInfo.icon}</span>
                      <div className="integration-info">
                        <h3 className="integration-name">{integration.name}</h3>
                        <span className="integration-type">{typeInfo.label}</span>
                      </div>
                      <Badge variant={integration.is_enabled ? "success" : "default"} size="sm">
                        {integration.is_enabled ? "Active" : "Disabled"}
                      </Badge>
                    </div>
                    {integration.description && (
                      <p className="integration-desc">{integration.description}</p>
                    )}
                    <div className="integration-stats">
                      {integration.last_triggered_at && (
                        <span>Last triggered: {new Date(integration.last_triggered_at).toLocaleString()}</span>
                      )}
                      {integration.failure_count > 0 && (
                        <Badge variant="error" size="sm">{integration.failure_count} failures</Badge>
                      )}
                    </div>
                    <div className="integration-actions">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleTest(integration)}
                        loading={testingId === integration.id}
                        disabled={!integration.is_enabled}
                      >
                        Test
                      </Button>
                      <Link to={`/ui/integrations/${integration.id}/logs`}>
                        <Button variant="ghost" size="sm">Logs</Button>
                      </Link>
                      <Button variant="ghost" size="sm" onClick={() => openEditModal(integration)}>
                        Edit
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => handleToggleEnabled(integration)}>
                        {integration.is_enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="danger"
                        onClick={() => setDeleteConfirm(integration)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardBody>
      </Card>

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
        title="Add Integration"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-stack">
          <div className="type-selector">
            {INTEGRATION_TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                className={`type-option ${formData.type === t.value ? "selected" : ""}`}
                onClick={() => setFormData({ ...formData, type: t.value, config: {} })}
              >
                <span className="type-icon">{t.icon}</span>
                <span className="type-label">{t.label}</span>
                <span className="type-desc">{t.desc}</span>
              </button>
            ))}
          </div>
          <Input
            label="Integration Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="e.g., Production SIEM"
          />
          <Input
            label="Description (optional)"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Brief description"
          />
          {renderConfigFields()}
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editIntegration}
        onClose={() => {
          setEditIntegration(null);
          resetForm();
        }}
        title="Edit Integration"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditIntegration(null)}>Cancel</Button>
            <Button variant="primary" onClick={handleUpdate} loading={saving}>Save</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Integration Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          />
          <Input
            label="Description (optional)"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />
          {renderConfigFields()}
        </div>
      </Modal>

      {/* Delete Confirm */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Integration"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This will also delete all delivery logs.`}
        confirmText="Delete"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
