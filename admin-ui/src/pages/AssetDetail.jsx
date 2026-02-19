import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./AssetDetail.css";

const STATUS_OPTIONS = [
  { value: "active", label: "Active", color: "success" },
  { value: "inactive", label: "Inactive", color: "default" },
  { value: "maintenance", label: "Maintenance", color: "warning" },
  { value: "retired", label: "Retired", color: "error" },
  { value: "disposed", label: "Disposed", color: "error" },
];

const TYPE_ICONS = {
  server: "🖥️",
  laptop: "💻",
  desktop: "🖳",
  network: "🌐",
  mobile: "📱",
  software: "📀",
  other: "📦",
};

export default function AssetDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [asset, setAsset] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showEditModal, setShowEditModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({});

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [assetRes, historyRes] = await Promise.all([
        api.get(`/admin/assets/${id}`),
        api.get(`/admin/assets/${id}/history?page_size=20`),
      ]);
      setAsset(assetRes.data);
      setHistory(historyRes.data.items || []);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Assets feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load asset");
      navigate("/ui/assets");
    } finally {
      setLoading(false);
    }
  }, [id, toast, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const openEditModal = () => {
    setFormData({
      name: asset.name,
      description: asset.description || "",
      status: asset.status,
      location: asset.location || "",
      department: asset.department || "",
      assigned_to_id: asset.assigned_to_id || "",
      manufacturer: asset.manufacturer || "",
      model: asset.model || "",
      serial_number: asset.serial_number || "",
      ip_address: asset.ip_address || "",
      mac_address: asset.mac_address || "",
      purchase_date: asset.purchase_date || "",
      warranty_expiry: asset.warranty_expiry || "",
    });
    setShowEditModal(true);
  };

  const handleUpdate = async () => {
    try {
      setSaving(true);
      const payload = { ...formData };
      // Clean up empty strings
      Object.keys(payload).forEach((key) => {
        if (payload[key] === "") payload[key] = null;
      });

      await api.patch(`/admin/assets/${id}`, payload);
      toast.success("Asset updated");
      setShowEditModal(false);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to update asset");
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (newStatus) => {
    try {
      await api.patch(`/admin/assets/${id}`, { status: newStatus });
      toast.success(`Status changed to ${newStatus}`);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to update status");
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString();
  };

  const formatDateTime = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const getStatusBadge = (status) => {
    const s = STATUS_OPTIONS.find((o) => o.value === status);
    return <Badge variant={s?.color || "default"} size="lg">{status}</Badge>;
  };

  const getHistoryActionLabel = (action) => {
    const labels = {
      created: "Created",
      updated: "Updated",
      assigned: "Assigned",
      unassigned: "Unassigned",
      status_changed: "Status Changed",
    };
    return labels[action] || action;
  };

  if (loading) {
    return <PageLoader message="Loading asset..." />;
  }

  if (!asset) {
    return null;
  }

  const isWarrantyExpiring = asset.warranty_expiry && new Date(asset.warranty_expiry) <= new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);

  return (
    <div className="asset-detail-page">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            <Link to="/ui/assets">Assets</Link>
            <span>/</span>
            <span>{asset.asset_tag}</span>
          </div>
          <div className="asset-title">
            <span className="asset-type-icon">{TYPE_ICONS[asset.asset_type] || "📦"}</span>
            <div>
              <h1 className="page-title">{asset.name}</h1>
              <code className="asset-tag">{asset.asset_tag}</code>
            </div>
          </div>
        </div>
        <div className="header-actions">
          {getStatusBadge(asset.status)}
          <Button variant="secondary" onClick={openEditModal}>Edit</Button>
        </div>
      </div>

      <div className="detail-grid">
        {/* Main Info Card */}
        <Card>
          <CardHeader title="Asset Details" />
          <CardBody>
            <div className="detail-list">
              <div className="detail-item">
                <label>Type</label>
                <span className="capitalize">{asset.asset_type}</span>
              </div>
              <div className="detail-item">
                <label>Description</label>
                <span>{asset.description || "-"}</span>
              </div>
              <div className="detail-item">
                <label>Location</label>
                <span>{asset.location || "-"}</span>
              </div>
              <div className="detail-item">
                <label>Department</label>
                <span>{asset.department || "-"}</span>
              </div>
              <div className="detail-item">
                <label>Assigned To</label>
                <span>{asset.assigned_to_email || "Unassigned"}</span>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Technical Details Card */}
        <Card>
          <CardHeader title="Technical Details" />
          <CardBody>
            <div className="detail-list">
              <div className="detail-item">
                <label>Manufacturer</label>
                <span>{asset.manufacturer || "-"}</span>
              </div>
              <div className="detail-item">
                <label>Model</label>
                <span>{asset.model || "-"}</span>
              </div>
              <div className="detail-item">
                <label>Serial Number</label>
                <span className="mono">{asset.serial_number || "-"}</span>
              </div>
              <div className="detail-item">
                <label>IP Address</label>
                <span className="mono">{asset.ip_address || "-"}</span>
              </div>
              <div className="detail-item">
                <label>MAC Address</label>
                <span className="mono">{asset.mac_address || "-"}</span>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Lifecycle Card */}
        <Card>
          <CardHeader title="Lifecycle" />
          <CardBody>
            <div className="detail-list">
              <div className="detail-item">
                <label>Purchase Date</label>
                <span>{formatDate(asset.purchase_date)}</span>
              </div>
              <div className="detail-item">
                <label>Warranty Expiry</label>
                <span className={isWarrantyExpiring ? "warning" : ""}>
                  {formatDate(asset.warranty_expiry)}
                  {isWarrantyExpiring && " ⚠️"}
                </span>
              </div>
              <div className="detail-item">
                <label>Created</label>
                <span>{formatDateTime(asset.created_at)}</span>
              </div>
              <div className="detail-item">
                <label>Last Updated</label>
                <span>{formatDateTime(asset.updated_at)}</span>
              </div>
            </div>

            <div className="status-actions">
              <label>Quick Status Change:</label>
              <div className="status-buttons">
                {STATUS_OPTIONS.map((s) => (
                  <Button
                    key={s.value}
                    variant={asset.status === s.value ? "primary" : "secondary"}
                    size="sm"
                    onClick={() => handleStatusChange(s.value)}
                    disabled={asset.status === s.value}
                  >
                    {s.label}
                  </Button>
                ))}
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Tags Card */}
        {asset.tags && asset.tags.length > 0 && (
          <Card>
            <CardHeader title="Tags" />
            <CardBody>
              <div className="tags-list">
                {asset.tags.map((tag) => (
                  <Badge key={tag} variant="default">{tag}</Badge>
                ))}
              </div>
            </CardBody>
          </Card>
        )}
      </div>

      {/* History Card */}
      <Card className="history-card">
        <CardHeader title="Change History" />
        <CardBody>
          {history.length === 0 ? (
            <p className="no-history">No history recorded</p>
          ) : (
            <div className="history-timeline">
              {history.map((entry) => (
                <div key={entry.id} className="history-item">
                  <div className="history-header">
                    <Badge variant="default" size="sm">{getHistoryActionLabel(entry.action)}</Badge>
                    <span className="history-actor">{entry.actor_email || "System"}</span>
                    <span className="history-time">{formatDateTime(entry.created_at)}</span>
                  </div>
                  {entry.changes && Object.keys(entry.changes).length > 0 && (
                    <div className="history-changes">
                      {Object.entries(entry.changes).map(([field, change]) => (
                        <div key={field} className="change-item">
                          <span className="change-field">{field}:</span>
                          <span className="change-from">{change.from || "(empty)"}</span>
                          <span className="change-arrow">→</span>
                          <span className="change-to">{change.to || "(empty)"}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {/* Edit Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title="Edit Asset"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleUpdate} loading={saving}>Save Changes</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Name"
            value={formData.name || ""}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          />
          <Input
            label="Description"
            value={formData.description || ""}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />
          <Select
            label="Status"
            value={formData.status || ""}
            onChange={(e) => setFormData({ ...formData, status: e.target.value })}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
          <div className="form-row">
            <Input
              label="Location"
              value={formData.location || ""}
              onChange={(e) => setFormData({ ...formData, location: e.target.value })}
            />
            <Input
              label="Department"
              value={formData.department || ""}
              onChange={(e) => setFormData({ ...formData, department: e.target.value })}
            />
          </div>
          <Input
            label="Assigned To (User ID)"
            type="number"
            placeholder="Enter user ID"
            value={formData.assigned_to_id || ""}
            onChange={(e) => setFormData({ ...formData, assigned_to_id: e.target.value ? parseInt(e.target.value, 10) : null })}
          />
          <div className="form-row">
            <Input
              label="Manufacturer"
              value={formData.manufacturer || ""}
              onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
            />
            <Input
              label="Model"
              value={formData.model || ""}
              onChange={(e) => setFormData({ ...formData, model: e.target.value })}
            />
          </div>
          <div className="form-row">
            <Input
              label="Serial Number"
              value={formData.serial_number || ""}
              onChange={(e) => setFormData({ ...formData, serial_number: e.target.value })}
            />
            <Input
              label="IP Address"
              value={formData.ip_address || ""}
              onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
            />
          </div>
          <div className="form-row">
            <Input
              label="Purchase Date"
              type="date"
              value={formData.purchase_date || ""}
              onChange={(e) => setFormData({ ...formData, purchase_date: e.target.value })}
            />
            <Input
              label="Warranty Expiry"
              type="date"
              value={formData.warranty_expiry || ""}
              onChange={(e) => setFormData({ ...formData, warranty_expiry: e.target.value })}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
