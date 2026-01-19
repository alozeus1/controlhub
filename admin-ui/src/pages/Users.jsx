import { useEffect, useState } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import { RoleBadge, StatusBadge } from "../components/ui/Badge";
import Pagination from "../components/ui/Pagination";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Users.css";

export default function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [filters, setFilters] = useState({ role: "", is_active: "", search: "" });
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null);
  const [formData, setFormData] = useState({ email: "", password: "", role: "user" });
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const currentUser = JSON.parse(localStorage.getItem("user") || "{}");
  const canManage = ["admin", "superadmin"].includes(currentUser.role);

  const fetchUsers = async (page = 1) => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page, page_size: 20 });
      if (filters.role) params.append("role", filters.role);
      if (filters.is_active) params.append("is_active", filters.is_active);
      if (filters.search) params.append("search", filters.search);

      const res = await api.get(`/admin/users?${params}`);
      setUsers(res.data.items);
      setPagination({
        page: res.data.page,
        pages: res.data.pages,
        total: res.data.total,
        page_size: res.data.page_size,
      });
    } catch (err) {
      toast.error("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(1);
  }, [filters]);

  const handleCreate = async () => {
    try {
      setSaving(true);
      await api.post("/admin/users", formData);
      toast.success("User created successfully");
      setShowCreateModal(false);
      setFormData({ email: "", password: "", role: "user" });
      fetchUsers(pagination.page);
    } catch (err) {
      toast.error(err.response?.data?.error || "Failed to create user");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    try {
      setSaving(true);
      await api.patch(`/admin/users/${selectedUser.id}`, {
        role: formData.role,
        is_active: formData.is_active,
      });
      toast.success("User updated successfully");
      setShowEditModal(false);
      fetchUsers(pagination.page);
    } catch (err) {
      toast.error(err.response?.data?.error || "Failed to update user");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = async () => {
    try {
      setSaving(true);
      const endpoint = confirmAction.user.is_active ? "disable" : "enable";
      await api.put(`/admin/users/${confirmAction.user.id}/${endpoint}`);
      toast.success(`User ${endpoint}d successfully`);
      setConfirmAction(null);
      fetchUsers(pagination.page);
    } catch (err) {
      toast.error(err.response?.data?.error || "Failed to update user");
    } finally {
      setSaving(false);
    }
  };

  const openEditModal = (user) => {
    setSelectedUser(user);
    setFormData({ role: user.role, is_active: user.is_active });
    setShowEditModal(true);
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString();
  };

  return (
    <div className="users-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Users</h1>
          <p className="page-subtitle">Manage user accounts and permissions</p>
        </div>
        {canManage && (
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>
            + Add User
          </Button>
        )}
      </div>

      <Card>
        <CardHeader title={`${pagination.total} Users`}>
          <div className="users-filters">
            <Select
              value={filters.role}
              onChange={(e) => setFilters({ ...filters, role: e.target.value })}
              style={{ width: 150 }}
            >
              <option value="">All Roles</option>
              <option value="superadmin">Superadmin</option>
              <option value="admin">Admin</option>
              <option value="viewer">Viewer</option>
              <option value="user">User</option>
            </Select>
            <Select
              value={filters.is_active}
              onChange={(e) => setFilters({ ...filters, is_active: e.target.value })}
              style={{ width: 150 }}
            >
              <option value="">All Status</option>
              <option value="true">Active</option>
              <option value="false">Disabled</option>
            </Select>
            <input
              type="text"
              className="input"
              placeholder="Search by email..."
              value={filters.search}
              onChange={(e) => setFilters({ ...filters, search: e.target.value })}
              style={{ width: 250 }}
            />
          </div>
        </CardHeader>
        <CardBody>
          {loading ? (
            <PageLoader message="Loading users..." />
          ) : users.length === 0 ? (
            <div className="empty-state">
              <p>No users found</p>
            </div>
          ) : (
            <>
              <table className="users-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Created</th>
                    {canManage && <th>Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <div className="user-cell">
                          <div className="user-avatar">
                            {user.email[0].toUpperCase()}
                          </div>
                          <span>{user.email}</span>
                        </div>
                      </td>
                      <td><RoleBadge role={user.role} /></td>
                      <td><StatusBadge active={user.is_active} /></td>
                      <td className="text-muted">{formatDate(user.created_at)}</td>
                      {canManage && (
                        <td>
                          <div className="action-buttons">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openEditModal(user)}
                              disabled={user.id === currentUser.id}
                            >
                              Edit
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirmAction({ type: "toggle", user })}
                              disabled={user.id === currentUser.id}
                            >
                              {user.is_active ? "Disable" : "Enable"}
                            </Button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchUsers}
              />
            </>
          )}
        </CardBody>
      </Card>

      {/* Create User Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create User"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>
              Create User
            </Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Email"
            type="email"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            placeholder="user@example.com"
          />
          <Input
            label="Password"
            type="password"
            value={formData.password}
            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            placeholder="Min 8 characters"
          />
          <Select
            label="Role"
            value={formData.role}
            onChange={(e) => setFormData({ ...formData, role: e.target.value })}
          >
            <option value="user">User</option>
            <option value="viewer">Viewer</option>
            {currentUser.role === "superadmin" && <option value="admin">Admin</option>}
          </Select>
        </div>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title={`Edit User: ${selectedUser?.email}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowEditModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleUpdate} loading={saving}>
              Save Changes
            </Button>
          </>
        }
      >
        <div className="form-stack">
          <Select
            label="Role"
            value={formData.role}
            onChange={(e) => setFormData({ ...formData, role: e.target.value })}
          >
            <option value="user">User</option>
            <option value="viewer">Viewer</option>
            {currentUser.role === "superadmin" && <option value="admin">Admin</option>}
          </Select>
        </div>
      </Modal>

      {/* Confirm Toggle Status */}
      <ConfirmModal
        isOpen={!!confirmAction}
        onClose={() => setConfirmAction(null)}
        onConfirm={handleToggleStatus}
        title={confirmAction?.user?.is_active ? "Disable User" : "Enable User"}
        message={`Are you sure you want to ${confirmAction?.user?.is_active ? "disable" : "enable"} ${confirmAction?.user?.email}?`}
        confirmText={confirmAction?.user?.is_active ? "Disable" : "Enable"}
        confirmVariant={confirmAction?.user?.is_active ? "danger" : "primary"}
        loading={saving}
      />
    </div>
  );
}
