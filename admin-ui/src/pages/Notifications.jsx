import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Notifications.css";

const CHANNEL_TYPES = [
  { value: "email", label: "Email", icon: "📧" },
  { value: "slack", label: "Slack", icon: "💬" },
  { value: "webhook", label: "Webhook", icon: "🔗" },
];

export default function Notifications() {
  const navigate = useNavigate();
  const toast = useToast();

  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editChannel, setEditChannel] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    type: "email",
    name: "",
    config: {},
  });

  const fetchChannels = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get("/admin/notification-channels");
      setChannels(res.data.items || []);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Notifications feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load notification channels");
    } finally {
      setLoading(false);
    }
  }, [toast, navigate]);

  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);

  const resetForm = () => {
    setFormData({ type: "email", name: "", config: {} });
  };

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      toast.error("Channel name is required");
      return;
    }

    // Validate config based on type
    if (formData.type === "email" && !formData.config.recipients?.length) {
      toast.error("At least one email recipient is required");
      return;
    }
    if (formData.type === "slack" && !formData.config.webhook_url) {
      toast.error("Slack webhook URL is required");
      return;
    }
    if (formData.type === "webhook" && !formData.config.url) {
      toast.error("Webhook URL is required");
      return;
    }

    try {
      setSaving(true);
      await api.post("/admin/notification-channels", formData);
      toast.success("Channel created");
      setShowCreateModal(false);
      resetForm();
      fetchChannels();
    } catch (err) {
      toast.error(err.message || "Failed to create channel");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    if (!editChannel) return;

    try {
      setSaving(true);
      await api.patch(`/admin/notification-channels/${editChannel.id}`, {
        name: formData.name,
        config: formData.config,
        is_enabled: formData.is_enabled,
      });
      toast.success("Channel updated");
      setEditChannel(null);
      resetForm();
      fetchChannels();
    } catch (err) {
      toast.error(err.message || "Failed to update channel");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;

    try {
      setSaving(true);
      await api.delete(`/admin/notification-channels/${deleteConfirm.id}`);
      toast.success("Channel deleted");
      setDeleteConfirm(null);
      fetchChannels();
    } catch (err) {
      toast.error(err.message || "Failed to delete channel");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (channel) => {
    try {
      setTestingId(channel.id);
      const res = await api.post(`/admin/notification-channels/${channel.id}/test`);
      if (res.data.details?.success) {
        toast.success("Test notification sent successfully");
      } else {
        toast.error("Test failed: " + (res.data.details?.error || "Unknown error"));
      }
    } catch (err) {
      toast.error(err.message || "Test failed");
    } finally {
      setTestingId(null);
    }
  };

  const handleToggleEnabled = async (channel) => {
    try {
      await api.patch(`/admin/notification-channels/${channel.id}`, {
        is_enabled: !channel.is_enabled,
      });
      toast.success(channel.is_enabled ? "Channel disabled" : "Channel enabled");
      fetchChannels();
    } catch (err) {
      toast.error(err.message || "Failed to update channel");
    }
  };

  const openEditModal = (channel) => {
    setEditChannel(channel);
    setFormData({
      type: channel.type,
      name: channel.name,
      config: { ...channel.config },
      is_enabled: channel.is_enabled,
    });
  };

  const getTypeIcon = (type) => {
    const t = CHANNEL_TYPES.find((ct) => ct.value === type);
    return t ? t.icon : "📢";
  };

  const renderConfigFields = () => {
    switch (formData.type) {
      case "email":
        return (
          <div className="form-group">
            <label className="form-label">Recipients (comma-separated)</label>
            <Input
              value={(formData.config.recipients || []).join(", ")}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  config: {
                    ...formData.config,
                    recipients: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                  },
                })
              }
              placeholder="admin@example.com, ops@example.com"
            />
          </div>
        );
      case "slack":
        return (
          <div className="form-group">
            <label className="form-label">Webhook URL</label>
            <Input
              type="url"
              value={formData.config.webhook_url || ""}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  config: { ...formData.config, webhook_url: e.target.value },
                })
              }
              placeholder="https://hooks.slack.com/services/..."
            />
          </div>
        );
      case "webhook":
        return (
          <>
            <div className="form-group">
              <label className="form-label">Webhook URL</label>
              <Input
                type="url"
                value={formData.config.url || ""}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    config: { ...formData.config, url: e.target.value },
                  })
                }
                placeholder="https://your-endpoint.com/webhook"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Authorization Header (optional)</label>
              <Input
                value={formData.config.auth_header?.value || ""}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    config: {
                      ...formData.config,
                      auth_header: e.target.value
                        ? { name: "Authorization", value: e.target.value }
                        : null,
                    },
                  })
                }
                placeholder="Bearer your-token"
              />
            </div>
          </>
        );
      default:
        return null;
    }
  };

  if (loading) {
    return <PageLoader message="Loading notification channels..." />;
  }

  return (
    <div className="notifications-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Notification Channels</h1>
          <p className="page-subtitle">Manage how alerts are delivered</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreateModal(true)}>
          + Add Channel
        </Button>
      </div>

      <Card>
        <CardBody>
          {channels.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔔</div>
              <p className="empty-state-title">No notification channels</p>
              <p className="empty-state-text">Create a channel to start receiving alerts</p>
              <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                Add Channel
              </Button>
            </div>
          ) : (
            <div className="channels-grid">
              {channels.map((channel) => (
                <div key={channel.id} className={`channel-card ${!channel.is_enabled ? "disabled" : ""}`}>
                  <div className="channel-header">
                    <span className="channel-icon">{getTypeIcon(channel.type)}</span>
                    <div className="channel-info">
                      <h3 className="channel-name">{channel.name}</h3>
                      <span className="channel-type">{channel.type}</span>
                    </div>
                    <Badge variant={channel.is_enabled ? "success" : "default"} size="sm">
                      {channel.is_enabled ? "Active" : "Disabled"}
                    </Badge>
                  </div>
                  <div className="channel-config">
                    {channel.type === "email" && (
                      <p>{channel.config.recipients?.length || 0} recipient(s)</p>
                    )}
                    {channel.type === "slack" && <p>Slack Webhook</p>}
                    {channel.type === "webhook" && <p>Custom Webhook</p>}
                  </div>
                  <div className="channel-actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleTest(channel)}
                      loading={testingId === channel.id}
                      disabled={!channel.is_enabled}
                    >
                      Test
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openEditModal(channel)}>
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleToggleEnabled(channel)}
                    >
                      {channel.is_enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="danger"
                      onClick={() => setDeleteConfirm(channel)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
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
        title="Add Notification Channel"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-stack">
          <Select
            label="Channel Type"
            value={formData.type}
            onChange={(e) => setFormData({ ...formData, type: e.target.value, config: {} })}
          >
            {CHANNEL_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.icon} {t.label}
              </option>
            ))}
          </Select>
          <Input
            label="Channel Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="e.g., Operations Team"
          />
          {renderConfigFields()}
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editChannel}
        onClose={() => {
          setEditChannel(null);
          resetForm();
        }}
        title="Edit Notification Channel"
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditChannel(null)}>Cancel</Button>
            <Button variant="primary" onClick={handleUpdate} loading={saving}>Save</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Channel Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          />
          {renderConfigFields()}
        </div>
      </Modal>

      {/* Delete Confirm */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Channel"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? Any alert rules using this channel will need to be updated.`}
        confirmText="Delete"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
