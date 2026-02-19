import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Certificates.css";

const ENV_OPTIONS = ["production", "staging", "development", "internal"];

const EMPTY_FORM = {
  domain: "",
  issuer: "",
  environment: "production",
  expires_at: "",
  auto_renew: false,
  notes: "",
};

export default function Certificates() {
  const toast = useToast();

  const [certs, setCerts] = useState([]);
  const [expiring, setExpiring] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [envFilter, setEnvFilter] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingCert, setEditingCert] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({ ...EMPTY_FORM });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (statusFilter) params.append("status", statusFilter);
      if (envFilter) params.append("environment", envFilter);

      const [certsRes, expiringRes] = await Promise.all([
        api.get(`/admin/certificates?${params}`),
        api.get("/admin/certificates/expiring"),
      ]);
      setCerts(certsRes.data.items || certsRes.data || []);
      setExpiring(expiringRes.data.items || expiringRes.data || []);
    } catch {
      toast.error("Failed to load certificates");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, envFilter, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getDaysUntil = (dateStr) => {
    if (!dateStr) return null;
    const diff = new Date(dateStr) - new Date();
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
  };

  const getStatus = (cert) => {
    if (cert.status) return cert.status;
    const days = getDaysUntil(cert.expires_at);
    if (days === null) return "unknown";
    if (days <= 0) return "expired";
    if (days <= 7) return "critical";
    if (days <= 30) return "warning";
    return "ok";
  };

  const getStatusBadgeVariant = (status) => {
    const map = { expired: "error", critical: "error", warning: "warning", ok: "success" };
    return map[status] || "default";
  };

  const getDaysClass = (days) => {
    if (days === null) return "";
    if (days <= 0) return "days-expired";
    if (days <= 7) return "days-critical";
    if (days <= 30) return "days-warning";
    return "days-ok";
  };

  const stats = {
    total: certs.length,
    expired: certs.filter((c) => getStatus(c) === "expired").length,
    critical: certs.filter((c) => getStatus(c) === "critical").length,
    warning: certs.filter((c) => getStatus(c) === "warning").length,
    ok: certs.filter((c) => getStatus(c) === "ok").length,
  };

  const criticalCerts = expiring.filter((c) => getDaysUntil(c.expires_at) <= 7 && getDaysUntil(c.expires_at) > 0);

  const openCreate = () => {
    setEditingCert(null);
    setFormData({ ...EMPTY_FORM });
    setShowModal(true);
  };

  const openEdit = (cert) => {
    setEditingCert(cert);
    setFormData({
      domain: cert.domain || "",
      issuer: cert.issuer || "",
      environment: cert.environment || "production",
      expires_at: cert.expires_at ? cert.expires_at.split("T")[0] : "",
      auto_renew: cert.auto_renew || false,
      notes: cert.notes || "",
    });
    setShowModal(true);
  };

  const handleSubmit = async () => {
    if (!formData.domain || !formData.expires_at) {
      toast.error("Domain and expiry date are required");
      return;
    }
    try {
      setSaving(true);
      if (editingCert) {
        await api.put(`/admin/certificates/${editingCert.id}`, formData);
        toast.success("Certificate updated");
      } else {
        await api.post("/admin/certificates", formData);
        toast.success("Certificate added");
      }
      setShowModal(false);
      fetchData();
    } catch {
      toast.error("Failed to save certificate");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      setSaving(true);
      await api.delete(`/admin/certificates/${deleteConfirm.id}`);
      toast.success("Certificate deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch {
      toast.error("Failed to delete certificate");
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (d) => (d ? new Date(d).toLocaleDateString() : "-");

  if (loading && certs.length === 0) {
    return <PageLoader message="Loading certificates..." />;
  }

  return (
    <div className="certificates-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Certificate Tracker</h1>
          <p className="page-subtitle">Monitor SSL/TLS certificate expiry across environments</p>
        </div>
        <div className="page-header-actions">
          <Button variant="primary" onClick={openCreate}>Add Certificate</Button>
        </div>
      </div>

      {criticalCerts.length > 0 && (
        <div className="alert-banner alert-banner-critical">
          <span className="alert-banner-icon">!</span>
          <span>{criticalCerts.length} certificate(s) expiring within 7 days. Immediate action required.</span>
        </div>
      )}

      <div className="stats-cards">
        <div className="stat-card">
          <div className="stat-value">{stats.total}</div>
          <div className="stat-label">Total</div>
        </div>
        <div className="stat-card stat-card-error">
          <div className="stat-value">{stats.expired}</div>
          <div className="stat-label">Expired</div>
        </div>
        <div className="stat-card stat-card-error">
          <div className="stat-value">{stats.critical}</div>
          <div className="stat-label">Critical (&le;7d)</div>
        </div>
        <div className="stat-card stat-card-warning">
          <div className="stat-value">{stats.warning}</div>
          <div className="stat-label">Warning (&le;30d)</div>
        </div>
        <div className="stat-card stat-card-success">
          <div className="stat-value">{stats.ok}</div>
          <div className="stat-label">OK</div>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Certificates"
          action={
            <div className="filters">
              <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All Statuses</option>
                <option value="ok">OK</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
                <option value="expired">Expired</option>
              </Select>
              <Select value={envFilter} onChange={(e) => setEnvFilter(e.target.value)}>
                <option value="">All Environments</option>
                {ENV_OPTIONS.map((e) => (
                  <option key={e} value={e}>{e}</option>
                ))}
              </Select>
            </div>
          }
        />
        <CardBody>
          {certs.length === 0 ? (
            <div className="empty-state">
              <p className="empty-state-title">No certificates found</p>
              <p className="empty-state-text">Add certificates to start tracking their expiry dates</p>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Domain</th>
                    <th>Issuer</th>
                    <th>Environment</th>
                    <th>Expires At</th>
                    <th>Days Until Expiry</th>
                    <th>Status</th>
                    <th>Auto Renew</th>
                    <th>Notes</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {certs.map((cert) => {
                    const days = getDaysUntil(cert.expires_at);
                    const status = getStatus(cert);
                    return (
                      <tr key={cert.id}>
                        <td className="cert-domain">{cert.domain}</td>
                        <td>{cert.issuer || "-"}</td>
                        <td><Badge variant="default">{cert.environment}</Badge></td>
                        <td className="timestamp">{formatDate(cert.expires_at)}</td>
                        <td>
                          <span className={getDaysClass(days)}>
                            {days !== null ? (days <= 0 ? `${Math.abs(days)}d overdue` : `${days}d`) : "-"}
                          </span>
                        </td>
                        <td><Badge variant={getStatusBadgeVariant(status)}>{status}</Badge></td>
                        <td>
                          <Badge variant={cert.auto_renew ? "success" : "default"}>
                            {cert.auto_renew ? "Yes" : "No"}
                          </Badge>
                        </td>
                        <td className="notes-cell">{cert.notes || "-"}</td>
                        <td>
                          <div className="action-buttons">
                            <Button variant="ghost" size="sm" onClick={() => openEdit(cert)}>Edit</Button>
                            <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(cert)}>Delete</Button>
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
        title={editingCert ? "Edit Certificate" : "Add Certificate"}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)} disabled={saving}>Cancel</Button>
            <Button variant="primary" onClick={handleSubmit} loading={saving}>
              {editingCert ? "Update" : "Add"}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <Input
            label="Domain"
            placeholder="e.g. api.example.com"
            value={formData.domain}
            onChange={(e) => setFormData({ ...formData, domain: e.target.value })}
            required
          />
          <Input
            label="Issuer"
            placeholder="e.g. Let's Encrypt"
            value={formData.issuer}
            onChange={(e) => setFormData({ ...formData, issuer: e.target.value })}
          />
          <Select
            label="Environment"
            value={formData.environment}
            onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
          >
            {ENV_OPTIONS.map((e) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </Select>
          <Input
            label="Expires At"
            type="date"
            value={formData.expires_at}
            onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
            required
          />
          <div className="checkbox-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={formData.auto_renew}
                onChange={(e) => setFormData({ ...formData, auto_renew: e.target.checked })}
              />
              <span>Auto Renew</span>
            </label>
          </div>
          <TextArea
            label="Notes"
            placeholder="Optional notes..."
            value={formData.notes}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
          />
        </div>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Certificate"
        message={`Are you sure you want to delete the certificate for "${deleteConfirm?.domain}"?`}
        confirmText="Delete"
        loading={saving}
      />
    </div>
  );
}
