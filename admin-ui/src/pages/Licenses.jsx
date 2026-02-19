import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Licenses.css";

const TYPE_OPTIONS = ["per-seat", "site", "subscription", "other"];
const STATUS_OPTIONS = ["active", "expired", "cancelled"];

const EMPTY_FORM = {
  vendor: "",
  product: "",
  license_type: "per-seat",
  seats: "",
  seats_used: "",
  cost_monthly: "",
  renewal_date: "",
  owner: "",
  notes: "",
  status: "active",
};

export default function Licenses() {
  const toast = useToast();

  const [licenses, setLicenses] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingLicense, setEditingLicense] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({ ...EMPTY_FORM });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (statusFilter) params.append("status", statusFilter);

      const [licensesRes, statsRes] = await Promise.all([
        api.get(`/admin/licenses?${params}`),
        api.get("/admin/licenses/stats"),
      ]);
      const items = licensesRes.data.items || licensesRes.data || [];
      items.sort((a, b) => new Date(a.renewal_date) - new Date(b.renewal_date));
      setLicenses(items);
      setStats(statsRes.data);
    } catch {
      toast.error("Failed to load licenses");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getDaysUntil = (dateStr) => {
    if (!dateStr) return null;
    const diff = new Date(dateStr) - new Date();
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
  };

  const getDaysClass = (days) => {
    if (days === null) return "";
    if (days <= 0) return "days-expired";
    if (days <= 30) return "days-critical";
    if (days <= 60) return "days-warning";
    return "days-ok";
  };

  const getStatusVariant = (status) => {
    const map = { active: "success", expired: "error", cancelled: "default" };
    return map[status] || "default";
  };

  const formatCurrency = (amount) => {
    if (amount == null) return "-";
    return `$${Number(amount).toFixed(2)}`;
  };

  const formatDate = (d) => (d ? new Date(d).toLocaleDateString() : "-");

  const openCreate = () => {
    setEditingLicense(null);
    setFormData({ ...EMPTY_FORM });
    setShowModal(true);
  };

  const openEdit = (lic) => {
    setEditingLicense(lic);
    setFormData({
      vendor: lic.vendor || "",
      product: lic.product || "",
      license_type: lic.license_type || "per-seat",
      seats: lic.seats ?? "",
      seats_used: lic.seats_used ?? "",
      cost_monthly: lic.cost_monthly ?? "",
      renewal_date: lic.renewal_date ? lic.renewal_date.split("T")[0] : "",
      owner: lic.owner || "",
      notes: lic.notes || "",
      status: lic.status || "active",
    });
    setShowModal(true);
  };

  const handleSubmit = async () => {
    if (!formData.vendor || !formData.product) {
      toast.error("Vendor and product are required");
      return;
    }
    try {
      setSaving(true);
      const payload = {
        ...formData,
        seats: formData.seats ? Number(formData.seats) : null,
        seats_used: formData.seats_used ? Number(formData.seats_used) : null,
        cost_monthly: formData.cost_monthly ? Number(formData.cost_monthly) : null,
      };
      if (editingLicense) {
        await api.put(`/admin/licenses/${editingLicense.id}`, payload);
        toast.success("License updated");
      } else {
        await api.post("/admin/licenses", payload);
        toast.success("License added");
      }
      setShowModal(false);
      fetchData();
    } catch {
      toast.error("Failed to save license");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      setSaving(true);
      await api.delete(`/admin/licenses/${deleteConfirm.id}`);
      toast.success("License deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch {
      toast.error("Failed to delete license");
    } finally {
      setSaving(false);
    }
  };

  if (loading && licenses.length === 0) {
    return <PageLoader message="Loading licenses..." />;
  }

  return (
    <div className="licenses-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">License Tracker</h1>
          <p className="page-subtitle">Track software licenses, costs, and renewals</p>
        </div>
        <div className="page-header-actions">
          <Button variant="primary" onClick={openCreate}>Add License</Button>
        </div>
      </div>

      {/* Stats Banner */}
      <div className="stats-cards">
        <div className="stat-card">
          <div className="stat-value">{stats?.total || licenses.length}</div>
          <div className="stat-label">Total Licenses</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{formatCurrency(stats?.monthly_cost)}</div>
          <div className="stat-label">Monthly Cost</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{formatCurrency(stats?.annual_cost)}</div>
          <div className="stat-label">Annual Cost</div>
        </div>
        <div className="stat-card stat-card-warning">
          <div className="stat-value">{stats?.expiring_soon ?? 0}</div>
          <div className="stat-label">Expiring Soon</div>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Licenses"
          action={
            <div className="filters">
              <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All Statuses</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
              </Select>
            </div>
          }
        />
        <CardBody>
          {licenses.length === 0 ? (
            <div className="empty-state">
              <p className="empty-state-title">No licenses found</p>
              <p className="empty-state-text">Add a software license to start tracking</p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Vendor</th>
                    <th>Product</th>
                    <th>Type</th>
                    <th>Seats</th>
                    <th>Monthly Cost</th>
                    <th>Renewal Date</th>
                    <th>Days Until Renewal</th>
                    <th>Owner</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {licenses.map((lic) => {
                    const days = getDaysUntil(lic.renewal_date);
                    return (
                      <tr key={lic.id}>
                        <td className="vendor-name">{lic.vendor}</td>
                        <td className="product-name">{lic.product}</td>
                        <td><Badge variant="default">{lic.license_type}</Badge></td>
                        <td>
                          {lic.seats != null ? (
                            <span className="seats-info">
                              {lic.seats_used ?? 0}/{lic.seats}
                            </span>
                          ) : "-"}
                        </td>
                        <td>{formatCurrency(lic.cost_monthly)}</td>
                        <td className="timestamp">{formatDate(lic.renewal_date)}</td>
                        <td>
                          <span className={getDaysClass(days)}>
                            {days !== null ? (days <= 0 ? "Overdue" : `${days}d`) : "-"}
                          </span>
                        </td>
                        <td className="text-muted">{lic.owner || "-"}</td>
                        <td><Badge variant={getStatusVariant(lic.status)}>{lic.status}</Badge></td>
                        <td>
                          <div className="action-buttons">
                            <Button variant="ghost" size="sm" onClick={() => openEdit(lic)}>Edit</Button>
                            <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(lic)}>Delete</Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Add / Edit Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={editingLicense ? "Edit License" : "Add License"}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)} disabled={saving}>Cancel</Button>
            <Button variant="primary" onClick={handleSubmit} loading={saving}>
              {editingLicense ? "Update" : "Add"}
            </Button>
          </>
        }
      >
        <div className="form-grid form-grid-2col">
          <Input
            label="Vendor"
            placeholder="e.g. Microsoft"
            value={formData.vendor}
            onChange={(e) => setFormData({ ...formData, vendor: e.target.value })}
            required
          />
          <Input
            label="Product"
            placeholder="e.g. Office 365"
            value={formData.product}
            onChange={(e) => setFormData({ ...formData, product: e.target.value })}
            required
          />
          <Select
            label="License Type"
            value={formData.license_type}
            onChange={(e) => setFormData({ ...formData, license_type: e.target.value })}
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
          <Select
            label="Status"
            value={formData.status}
            onChange={(e) => setFormData({ ...formData, status: e.target.value })}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </Select>
          <Input
            label="Total Seats"
            type="number"
            placeholder="e.g. 50"
            value={formData.seats}
            onChange={(e) => setFormData({ ...formData, seats: e.target.value })}
          />
          <Input
            label="Seats Used"
            type="number"
            placeholder="e.g. 35"
            value={formData.seats_used}
            onChange={(e) => setFormData({ ...formData, seats_used: e.target.value })}
          />
          <Input
            label="Monthly Cost ($)"
            type="number"
            step="0.01"
            placeholder="e.g. 499.99"
            value={formData.cost_monthly}
            onChange={(e) => setFormData({ ...formData, cost_monthly: e.target.value })}
          />
          <Input
            label="Renewal Date"
            type="date"
            value={formData.renewal_date}
            onChange={(e) => setFormData({ ...formData, renewal_date: e.target.value })}
          />
          <Input
            label="Owner (Email)"
            type="email"
            placeholder="owner@company.com"
            value={formData.owner}
            onChange={(e) => setFormData({ ...formData, owner: e.target.value })}
          />
          <div />
          <div className="form-full-width">
            <TextArea
              label="Notes"
              placeholder="Optional notes..."
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            />
          </div>
        </div>
      </Modal>

      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete License"
        message={`Are you sure you want to delete the license for "${deleteConfirm?.product}" from ${deleteConfirm?.vendor}?`}
        confirmText="Delete"
        loading={saving}
      />
    </div>
  );
}
