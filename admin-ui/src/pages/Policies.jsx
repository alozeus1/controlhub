import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Pagination from "../components/ui/Pagination";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Policies.css";

const AVAILABLE_ACTIONS = [
  { value: "upload.delete", label: "Delete Upload" },
  { value: "user.role_change", label: "Change User Role" },
  { value: "user.disable", label: "Disable User" },
  { value: "job.cancel", label: "Cancel Job" },
];

const ENVIRONMENTS = [
  { value: "all", label: "All Environments" },
  { value: "production", label: "Production Only" },
  { value: "staging", label: "Staging Only" },
];

const ROLES = [
  { value: "viewer", label: "Viewer" },
  { value: "admin", label: "Admin" },
  { value: "superadmin", label: "Superadmin" },
];

const defaultFormData = {
  name: "",
  description: "",
  action: "",
  environment: "all",
  required_role: "admin",
  requires_approval: false,
  approvals_required: 1,
  approver_role: "admin",
  is_active: true,
};

export default function Policies() {
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [formData, setFormData] = useState(defaultFormData);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const fetchPolicies = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/policies?page=${page}&page_size=20`);
      setPolicies(res.data.items || []);
      setPagination({
        page: res.data.page,
        pages: res.data.pages,
        total: res.data.total,
        page_size: res.data.page_size,
      });
    } catch (err) {
      toast.error("Failed to load policies");
      setPolicies([]);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchPolicies(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async () => {
    if (!formData.name || !formData.action) {
      toast.error("Name and action are required");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/policies", formData);
      toast.success("Policy created successfully");
      setShowCreateModal(false);
      setFormData(defaultFormData);
      fetchPolicies(pagination.page);
    } catch (err) {
      toast.error(err.message || "Failed to create policy");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    try {
      setSaving(true);
      await api.patch(`/admin/policies/${selectedPolicy.id}`, formData);
      toast.success("Policy updated successfully");
      setShowEditModal(false);
      fetchPolicies(pagination.page);
    } catch (err) {
      toast.error(err.message || "Failed to update policy");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      setSaving(true);
      await api.delete(`/admin/policies/${confirmDelete.id}`);
      toast.success("Policy deactivated");
      setConfirmDelete(null);
      fetchPolicies(pagination.page);
    } catch (err) {
      toast.error(err.message || "Failed to delete policy");
    } finally {
      setSaving(false);
    }
  };

  const openEditModal = (policy) => {
    setSelectedPolicy(policy);
    setFormData({
      name: policy.name,
      description: policy.description || "",
      action: policy.action,
      environment: policy.environment,
      required_role: policy.required_role,
      requires_approval: policy.requires_approval,
      approvals_required: policy.approvals_required,
      approver_role: policy.approver_role,
      is_active: policy.is_active,
    });
    setShowEditModal(true);
  };

  const getActionLabel = (action) => {
    const found = AVAILABLE_ACTIONS.find(a => a.value === action);
    return found ? found.label : action;
  };

  return (
    <div className="policies-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Policies</h1>
          <p className="page-subtitle">Configure governance policies for protected actions</p>
        </div>
        <Button variant="primary" onClick={() => {
          setFormData(defaultFormData);
          setShowCreateModal(true);
        }}>
          + Create Policy
        </Button>
      </div>

      <Card>
        <CardHeader title={`${pagination.total} Policies`} />
        <CardBody>
          {loading ? (
            <PageLoader message="Loading policies..." />
          ) : policies.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📜</div>
              <p className="empty-state-title">No policies configured</p>
              <p className="empty-state-text">Create a policy to require approval for sensitive actions</p>
            </div>
          ) : (
            <>
              <table className="policies-table">
                <thead>
                  <tr>
                    <th>Policy</th>
                    <th>Action</th>
                    <th>Approval</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {policies.map((policy) => (
                    <tr key={policy.id}>
                      <td>
                        <div className="policy-name-cell">
                          <span className="policy-name">{policy.name}</span>
                          {policy.description && (
                            <span className="policy-desc">{policy.description}</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <code className="action-code">{getActionLabel(policy.action)}</code>
                      </td>
                      <td>
                        {policy.requires_approval ? (
                          <div className="approval-info">
                            <Badge variant="warning">Requires Approval</Badge>
                            <span className="approval-count">{policy.approvals_required} approval(s)</span>
                          </div>
                        ) : (
                          <Badge variant="default">No Approval</Badge>
                        )}
                      </td>
                      <td>
                        <Badge variant={policy.is_active ? "success" : "error"}>
                          {policy.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      <td>
                        <div className="action-buttons">
                          <Button variant="ghost" size="sm" onClick={() => openEditModal(policy)}>
                            Edit
                          </Button>
                          {policy.is_active && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="danger"
                              onClick={() => setConfirmDelete(policy)}
                            >
                              Deactivate
                            </Button>
                          )}
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
                onPageChange={fetchPolicies}
              />
            </>
          )}
        </CardBody>
      </Card>

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Policy"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Create Policy</Button>
          </>
        }
      >
        <PolicyForm formData={formData} setFormData={setFormData} />
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title={`Edit Policy: ${selectedPolicy?.name}`}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleUpdate} loading={saving}>Save Changes</Button>
          </>
        }
      >
        <PolicyForm formData={formData} setFormData={setFormData} isEdit />
      </Modal>

      {/* Confirm Delete */}
      <ConfirmModal
        isOpen={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
        title="Deactivate Policy"
        message={`Are you sure you want to deactivate "${confirmDelete?.name}"? This will disable approval requirements for ${confirmDelete?.action}.`}
        confirmText="Deactivate"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}

function PolicyForm({ formData, setFormData, isEdit = false }) {
  return (
    <div className="form-stack">
      <Input
        label="Policy Name"
        value={formData.name}
        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
        placeholder="e.g., Require approval for upload deletion"
      />
      <TextArea
        label="Description (optional)"
        value={formData.description}
        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
        placeholder="Describe what this policy does..."
      />
      <Select
        label="Protected Action"
        value={formData.action}
        onChange={(e) => setFormData({ ...formData, action: e.target.value })}
        disabled={isEdit}
      >
        <option value="">Select an action...</option>
        {AVAILABLE_ACTIONS.map((a) => (
          <option key={a.value} value={a.value}>{a.label}</option>
        ))}
      </Select>
      <Select
        label="Environment"
        value={formData.environment}
        onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
      >
        {ENVIRONMENTS.map((e) => (
          <option key={e.value} value={e.value}>{e.label}</option>
        ))}
      </Select>
      <div className="form-row">
        <Select
          label="Required Role"
          value={formData.required_role}
          onChange={(e) => setFormData({ ...formData, required_role: e.target.value })}
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </Select>
        <Select
          label="Approver Role"
          value={formData.approver_role}
          onChange={(e) => setFormData({ ...formData, approver_role: e.target.value })}
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </Select>
      </div>
      <div className="form-checkbox">
        <label>
          <input
            type="checkbox"
            checked={formData.requires_approval}
            onChange={(e) => setFormData({ ...formData, requires_approval: e.target.checked })}
          />
          <span>Require approval before action is executed</span>
        </label>
      </div>
      {formData.requires_approval && (
        <Input
          label="Approvals Required"
          type="number"
          min="1"
          max="10"
          value={formData.approvals_required}
          onChange={(e) => setFormData({ ...formData, approvals_required: parseInt(e.target.value) || 1 })}
        />
      )}
    </div>
  );
}
