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
import "./AlertRules.css";

const SEVERITY_OPTIONS = [
  { value: "low", label: "Low", color: "default" },
  { value: "medium", label: "Medium", color: "warning" },
  { value: "high", label: "High", color: "error" },
  { value: "critical", label: "Critical", color: "error" },
];

export default function AlertRules() {
  const navigate = useNavigate();
  const toast = useToast();

  const [rules, setRules] = useState([]);
  const [channels, setChannels] = useState([]);
  const [metadata, setMetadata] = useState({ event_types: [], severity_levels: [] });
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editRule, setEditRule] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    event_type: "",
    severity: "medium",
    description: "",
    channel_ids: [],
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [rulesRes, channelsRes, metaRes] = await Promise.all([
        api.get("/admin/alert-rules"),
        api.get("/admin/notification-channels"),
        api.get("/admin/notifications/metadata"),
      ]);
      setRules(rulesRes.data.items || []);
      setChannels(channelsRes.data.items || []);
      setMetadata(metaRes.data);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Notifications feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load alert rules");
    } finally {
      setLoading(false);
    }
  }, [toast, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const resetForm = () => {
    setFormData({
      name: "",
      event_type: "",
      severity: "medium",
      description: "",
      channel_ids: [],
    });
  };

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      toast.error("Rule name is required");
      return;
    }
    if (!formData.event_type) {
      toast.error("Event type is required");
      return;
    }
    if (formData.channel_ids.length === 0) {
      toast.error("At least one channel must be selected");
      return;
    }

    try {
      setSaving(true);
      await api.post("/admin/alert-rules", formData);
      toast.success("Alert rule created");
      setShowCreateModal(false);
      resetForm();
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to create rule");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    if (!editRule) return;

    try {
      setSaving(true);
      await api.patch(`/admin/alert-rules/${editRule.id}`, formData);
      toast.success("Alert rule updated");
      setEditRule(null);
      resetForm();
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to update rule");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;

    try {
      setSaving(true);
      await api.delete(`/admin/alert-rules/${deleteConfirm.id}`);
      toast.success("Alert rule deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to delete rule");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async (rule) => {
    try {
      await api.patch(`/admin/alert-rules/${rule.id}`, {
        is_enabled: !rule.is_enabled,
      });
      toast.success(rule.is_enabled ? "Rule disabled" : "Rule enabled");
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to update rule");
    }
  };

  const openEditModal = (rule) => {
    setEditRule(rule);
    setFormData({
      name: rule.name,
      event_type: rule.event_type,
      severity: rule.severity,
      description: rule.description || "",
      channel_ids: rule.channel_ids || [],
      is_enabled: rule.is_enabled,
    });
  };

  const handleChannelToggle = (channelId) => {
    setFormData((prev) => ({
      ...prev,
      channel_ids: prev.channel_ids.includes(channelId)
        ? prev.channel_ids.filter((id) => id !== channelId)
        : [...prev.channel_ids, channelId],
    }));
  };

  const getSeverityBadge = (severity) => {
    const opt = SEVERITY_OPTIONS.find((s) => s.value === severity);
    return <Badge variant={opt?.color || "default"}>{severity}</Badge>;
  };

  const getChannelNames = (channelIds) => {
    return channelIds
      .map((id) => channels.find((c) => c.id === id)?.name || `#${id}`)
      .join(", ");
  };

  const formatEventType = (type) => {
    return type.replace(".", " → ").replace(/_/g, " ");
  };

  if (loading) {
    return <PageLoader message="Loading alert rules..." />;
  }

  return (
    <div className="alert-rules-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Alert Rules</h1>
          <p className="page-subtitle">Configure when and how alerts are triggered</p>
        </div>
        <div className="header-actions">
          <Link to="/ui/alerts" className="view-alerts-link">
            View Alert History →
          </Link>
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>
            + Create Rule
          </Button>
        </div>
      </div>

      {channels.length === 0 && (
        <div className="warning-banner">
          <span className="warning-icon">⚠️</span>
          <span>No notification channels configured. </span>
          <Link to="/ui/notifications">Create a channel first</Link>
        </div>
      )}

      <Card>
        <CardBody>
          {rules.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">⚡</div>
              <p className="empty-state-title">No alert rules</p>
              <p className="empty-state-text">Create rules to receive notifications when events occur</p>
              <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                Create Rule
              </Button>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Event Type</th>
                  <th>Severity</th>
                  <th>Channels</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.id} className={!rule.is_enabled ? "disabled-row" : ""}>
                    <td>
                      <div className="rule-name">{rule.name}</div>
                      {rule.description && (
                        <div className="rule-desc">{rule.description}</div>
                      )}
                    </td>
                    <td className="event-type">{formatEventType(rule.event_type)}</td>
                    <td>{getSeverityBadge(rule.severity)}</td>
                    <td className="channels-cell">
                      {getChannelNames(rule.channel_ids)}
                    </td>
                    <td>
                      <Badge variant={rule.is_enabled ? "success" : "default"}>
                        {rule.is_enabled ? "Active" : "Disabled"}
                      </Badge>
                    </td>
                    <td>
                      <div className="action-buttons">
                        <Button variant="ghost" size="sm" onClick={() => openEditModal(rule)}>
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleEnabled(rule)}
                        >
                          {rule.is_enabled ? "Disable" : "Enable"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="danger"
                          onClick={() => setDeleteConfirm(rule)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
        title="Create Alert Rule"
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
            label="Rule Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="e.g., Job Failure Alert"
          />
          <Select
            label="Event Type"
            value={formData.event_type}
            onChange={(e) => setFormData({ ...formData, event_type: e.target.value })}
          >
            <option value="">Select event type...</option>
            {metadata.event_types.map((et) => (
              <option key={et} value={et}>
                {formatEventType(et)}
              </option>
            ))}
          </Select>
          <Select
            label="Severity"
            value={formData.severity}
            onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
          >
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
          <Input
            label="Description (optional)"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Brief description of when this rule triggers"
          />
          <div className="form-group">
            <label className="form-label">Notification Channels</label>
            {channels.length === 0 ? (
              <p className="no-channels-msg">No channels available. Create one first.</p>
            ) : (
              <div className="channels-checkboxes">
                {channels.map((channel) => (
                  <label key={channel.id} className="channel-checkbox">
                    <input
                      type="checkbox"
                      checked={formData.channel_ids.includes(channel.id)}
                      onChange={() => handleChannelToggle(channel.id)}
                      disabled={!channel.is_enabled}
                    />
                    <span className={!channel.is_enabled ? "disabled" : ""}>
                      {channel.name} ({channel.type})
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={!!editRule}
        onClose={() => {
          setEditRule(null);
          resetForm();
        }}
        title="Edit Alert Rule"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditRule(null)}>Cancel</Button>
            <Button variant="primary" onClick={handleUpdate} loading={saving}>Save</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Rule Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          />
          <div className="form-group">
            <label className="form-label">Event Type</label>
            <p className="static-value">{formatEventType(editRule?.event_type || "")}</p>
          </div>
          <Select
            label="Severity"
            value={formData.severity}
            onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
          >
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
          <Input
            label="Description (optional)"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />
          <div className="form-group">
            <label className="form-label">Notification Channels</label>
            <div className="channels-checkboxes">
              {channels.map((channel) => (
                <label key={channel.id} className="channel-checkbox">
                  <input
                    type="checkbox"
                    checked={formData.channel_ids.includes(channel.id)}
                    onChange={() => handleChannelToggle(channel.id)}
                    disabled={!channel.is_enabled}
                  />
                  <span className={!channel.is_enabled ? "disabled" : ""}>
                    {channel.name} ({channel.type})
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>
      </Modal>

      {/* Delete Confirm */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Alert Rule"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This cannot be undone.`}
        confirmText="Delete"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
