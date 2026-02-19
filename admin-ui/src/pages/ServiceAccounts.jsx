import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Pagination from "../components/ui/Pagination";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./ServiceAccounts.css";

export default function ServiceAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formData, setFormData] = useState({ name: "", description: "" });
  const [saving, setSaving] = useState(false);
  const [toggleConfirm, setToggleConfirm] = useState(null);
  const toast = useToast();
  const navigate = useNavigate();

  const fetchAccounts = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/service-accounts?page=${page}&page_size=20`);
      setAccounts(res.data.items || []);
      setPagination({
        page: res.data.page,
        pages: res.data.pages,
        total: res.data.total,
        page_size: res.data.page_size,
      });
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Service accounts feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load service accounts");
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [toast, navigate]);

  useEffect(() => {
    fetchAccounts(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      toast.error("Name is required");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/service-accounts", formData);
      toast.success("Service account created");
      setShowCreateModal(false);
      setFormData({ name: "", description: "" });
      fetchAccounts(pagination.page);
    } catch (err) {
      toast.error(err.message || "Failed to create service account");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!toggleConfirm) return;
    try {
      setSaving(true);
      await api.patch(`/admin/service-accounts/${toggleConfirm.id}`, {
        is_active: !toggleConfirm.is_active,
      });
      toast.success(`Service account ${toggleConfirm.is_active ? "deactivated" : "activated"}`);
      setToggleConfirm(null);
      fetchAccounts(pagination.page);
    } catch (err) {
      toast.error(err.message || "Failed to update service account");
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString();
  };

  return (
    <div className="service-accounts-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Service Accounts</h1>
          <p className="page-subtitle">Manage service accounts for API access</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreateModal(true)}>
          + Create Service Account
        </Button>
      </div>

      <Card>
        <CardHeader title={`${pagination.total} Service Account${pagination.total !== 1 ? "s" : ""}`} />
        <CardBody>
          {loading ? (
            <PageLoader message="Loading service accounts..." />
          ) : accounts.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔑</div>
              <p className="empty-state-title">No service accounts</p>
              <p className="empty-state-text">Create a service account to enable API access</p>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Description</th>
                    <th>Keys</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((account) => (
                    <tr key={account.id}>
                      <td>
                        <Link to={`/ui/service-accounts/${account.id}`} className="account-name-link">
                          {account.name}
                        </Link>
                      </td>
                      <td className="description-cell">
                        {account.description || <span className="text-muted">-</span>}
                      </td>
                      <td>
                        <Badge variant="default">{account.key_count} key{account.key_count !== 1 ? "s" : ""}</Badge>
                      </td>
                      <td>
                        <Badge variant={account.is_active ? "success" : "error"}>
                          {account.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      <td className="text-muted">{formatDate(account.created_at)}</td>
                      <td>
                        <div className="action-buttons">
                          <Link to={`/ui/service-accounts/${account.id}`}>
                            <Button variant="ghost" size="sm">Manage Keys</Button>
                          </Link>
                          <Button
                            variant="ghost"
                            size="sm"
                            className={account.is_active ? "danger" : ""}
                            onClick={() => setToggleConfirm(account)}
                          >
                            {account.is_active ? "Deactivate" : "Activate"}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchAccounts}
              />
            </>
          )}
        </CardBody>
      </Card>

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Service Account"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="e.g., CI/CD Pipeline"
          />
          <TextArea
            label="Description (optional)"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="What this service account is used for..."
          />
        </div>
      </Modal>

      {/* Toggle Status Confirm */}
      <ConfirmModal
        isOpen={!!toggleConfirm}
        onClose={() => setToggleConfirm(null)}
        onConfirm={handleToggleStatus}
        title={toggleConfirm?.is_active ? "Deactivate Service Account" : "Activate Service Account"}
        message={
          toggleConfirm?.is_active
            ? `Are you sure you want to deactivate "${toggleConfirm?.name}"? All API keys will stop working.`
            : `Are you sure you want to activate "${toggleConfirm?.name}"?`
        }
        confirmText={toggleConfirm?.is_active ? "Deactivate" : "Activate"}
        confirmVariant={toggleConfirm?.is_active ? "danger" : "primary"}
        loading={saving}
      />
    </div>
  );
}
