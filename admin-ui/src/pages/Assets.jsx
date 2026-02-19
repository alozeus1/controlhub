import { useEffect, useState, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Assets.css";

const TYPE_OPTIONS = [
  { value: "server", label: "Server", icon: "🖥️" },
  { value: "laptop", label: "Laptop", icon: "💻" },
  { value: "desktop", label: "Desktop", icon: "🖳" },
  { value: "network", label: "Network", icon: "🌐" },
  { value: "mobile", label: "Mobile", icon: "📱" },
  { value: "software", label: "Software", icon: "📀" },
  { value: "other", label: "Other", icon: "📦" },
];

const STATUS_OPTIONS = [
  { value: "active", label: "Active", color: "success" },
  { value: "inactive", label: "Inactive", color: "default" },
  { value: "maintenance", label: "Maintenance", color: "warning" },
  { value: "retired", label: "Retired", color: "error" },
  { value: "disposed", label: "Disposed", color: "error" },
];

export default function Assets() {
  const navigate = useNavigate();
  const toast = useToast();

  const [assets, setAssets] = useState([]);
  const [stats, setStats] = useState(null);
  const [metadata, setMetadata] = useState({ departments: [], tags: [] });
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [filters, setFilters] = useState({ type: "", status: "", search: "" });
  const [formData, setFormData] = useState({
    name: "",
    type: "laptop",
    description: "",
    location: "",
    department: "",
    manufacturer: "",
    model: "",
    serial_number: "",
    ip_address: "",
    mac_address: "",
    purchase_date: "",
    warranty_expiry: "",
    tags: [],
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page, page_size: 20 });
      if (filters.type) params.append("type", filters.type);
      if (filters.status) params.append("status", filters.status);
      if (filters.search) params.append("search", filters.search);

      const [assetsRes, statsRes, metaRes] = await Promise.all([
        api.get(`/admin/assets?${params}`),
        api.get("/admin/assets/stats"),
        api.get("/admin/assets/metadata"),
      ]);
      setAssets(assetsRes.data.items || []);
      setTotalPages(assetsRes.data.pages || 1);
      setStats(statsRes.data);
      setMetadata(metaRes.data);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Assets feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load assets");
    } finally {
      setLoading(false);
    }
  }, [page, filters, toast, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const resetForm = () => {
    setFormData({
      name: "",
      type: "laptop",
      description: "",
      location: "",
      department: "",
      manufacturer: "",
      model: "",
      serial_number: "",
      ip_address: "",
      mac_address: "",
      purchase_date: "",
      warranty_expiry: "",
      tags: [],
    });
  };

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      toast.error("Asset name is required");
      return;
    }

    try {
      setSaving(true);
      const payload = { ...formData };
      if (!payload.purchase_date) delete payload.purchase_date;
      if (!payload.warranty_expiry) delete payload.warranty_expiry;
      if (payload.tags.length === 0) delete payload.tags;

      const res = await api.post("/admin/assets", payload);
      toast.success(`Asset ${res.data.asset.asset_tag} created`);
      setShowCreateModal(false);
      resetForm();
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to create asset");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;

    try {
      setSaving(true);
      await api.delete(`/admin/assets/${deleteConfirm.id}`);
      toast.success("Asset deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to delete asset");
    } finally {
      setSaving(false);
    }
  };

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const getTypeIcon = (type) => {
    const t = TYPE_OPTIONS.find((o) => o.value === type);
    return t ? t.icon : "📦";
  };

  const getStatusBadge = (status) => {
    const s = STATUS_OPTIONS.find((o) => o.value === status);
    return <Badge variant={s?.color || "default"}>{status}</Badge>;
  };

  if (loading && assets.length === 0) {
    return <PageLoader message="Loading assets..." />;
  }

  return (
    <div className="assets-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Asset Inventory</h1>
          <p className="page-subtitle">Manage IT assets and equipment</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreateModal(true)}>
          + Add Asset
        </Button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value">{stats.total}</div>
            <div className="stat-label">Total Assets</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.by_status?.active || 0}</div>
            <div className="stat-label">Active</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.by_status?.maintenance || 0}</div>
            <div className="stat-label">In Maintenance</div>
          </div>
          <div className="stat-card warning">
            <div className="stat-value">{stats.warranty_expiring_soon || 0}</div>
            <div className="stat-label">Warranty Expiring</div>
          </div>
        </div>
      )}

      <Card>
        <CardHeader
          title="Assets"
          action={
            <div className="filters">
              <Input
                placeholder="Search..."
                value={filters.search}
                onChange={(e) => handleFilterChange("search", e.target.value)}
                style={{ width: 200 }}
              />
              <Select
                value={filters.type}
                onChange={(e) => handleFilterChange("type", e.target.value)}
              >
                <option value="">All Types</option>
                {TYPE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.icon} {t.label}
                  </option>
                ))}
              </Select>
              <Select
                value={filters.status}
                onChange={(e) => handleFilterChange("status", e.target.value)}
              >
                <option value="">All Statuses</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </div>
          }
        />
        <CardBody>
          {assets.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🖥️</div>
              <p className="empty-state-title">No assets found</p>
              <p className="empty-state-text">Add your first asset to start tracking inventory</p>
              <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                Add Asset
              </Button>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Asset Tag</th>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Location</th>
                    <th>Assigned To</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map((asset) => (
                    <tr key={asset.id}>
                      <td>
                        <Link to={`/ui/assets/${asset.id}`} className="asset-tag-link">
                          <code>{asset.asset_tag}</code>
                        </Link>
                      </td>
                      <td>
                        <div className="asset-name">
                          <span className="asset-icon">{getTypeIcon(asset.asset_type)}</span>
                          <span>{asset.name}</span>
                        </div>
                      </td>
                      <td className="asset-type">{asset.asset_type}</td>
                      <td>{getStatusBadge(asset.status)}</td>
                      <td className="text-muted">{asset.location || "-"}</td>
                      <td className="text-muted">{asset.assigned_to_email || "-"}</td>
                      <td>
                        <div className="action-buttons">
                          <Link to={`/ui/assets/${asset.id}`}>
                            <Button variant="ghost" size="sm">View</Button>
                          </Link>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="danger"
                            onClick={() => setDeleteConfirm(asset)}
                          >
                            Delete
                          </Button>
                        </div>
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

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
        title="Add New Asset"
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
              label="Asset Name *"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g., MacBook Pro - Engineering"
            />
            <Select
              label="Type *"
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
            >
              {TYPE_OPTIONS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.icon} {t.label}
                </option>
              ))}
            </Select>
          </div>
          <Input
            label="Description"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Brief description"
          />
          <div className="form-row">
            <Input
              label="Location"
              value={formData.location}
              onChange={(e) => setFormData({ ...formData, location: e.target.value })}
              placeholder="e.g., Building A, Floor 3"
            />
            <Input
              label="Department"
              value={formData.department}
              onChange={(e) => setFormData({ ...formData, department: e.target.value })}
              placeholder="e.g., Engineering"
            />
          </div>
          <div className="form-row">
            <Input
              label="Manufacturer"
              value={formData.manufacturer}
              onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
              placeholder="e.g., Apple"
            />
            <Input
              label="Model"
              value={formData.model}
              onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              placeholder="e.g., MacBook Pro 16 (2023)"
            />
          </div>
          <div className="form-row">
            <Input
              label="Serial Number"
              value={formData.serial_number}
              onChange={(e) => setFormData({ ...formData, serial_number: e.target.value })}
              placeholder="e.g., C02XL1YZJGH5"
            />
            <Input
              label="IP Address"
              value={formData.ip_address}
              onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
              placeholder="e.g., 192.168.1.100"
            />
          </div>
          <div className="form-row">
            <Input
              label="Purchase Date"
              type="date"
              value={formData.purchase_date}
              onChange={(e) => setFormData({ ...formData, purchase_date: e.target.value })}
            />
            <Input
              label="Warranty Expiry"
              type="date"
              value={formData.warranty_expiry}
              onChange={(e) => setFormData({ ...formData, warranty_expiry: e.target.value })}
            />
          </div>
        </div>
      </Modal>

      {/* Delete Confirm */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Asset"
        message={`Are you sure you want to delete "${deleteConfirm?.asset_tag} - ${deleteConfirm?.name}"? This will also delete all history.`}
        confirmText="Delete"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
