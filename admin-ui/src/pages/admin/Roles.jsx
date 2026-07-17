import { useEffect, useState, useCallback } from "react";
import api from "../../utils/api";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input, { TextArea } from "../../components/ui/Input";
import Badge from "../../components/ui/Badge";
import Modal, { ConfirmModal } from "../../components/ui/Modal";
import EmptyState from "../../components/ui/EmptyState";
import { SkeletonTable } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import "./admin.css";

export default function Roles() {
  const [roles, setRoles] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);        // role being edited
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ name: "", label: "", description: "" });
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [r, c] = await Promise.all([
        api.get("/admin/roles"),
        api.get("/admin/permissions/catalog"),
      ]);
      setRoles(r.data.roles || []);
      setCatalog(c.data.permissions || []);
    } catch (err) {
      toast.error(err.message || "Failed to load roles");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const groups = catalog.reduce((acc, p) => {
    (acc[p.group] = acc[p.group] || []).push(p);
    return acc;
  }, {});

  const togglePerm = (key) => {
    if (!selected || selected.name === "superadmin") return;
    const has = selected.permissions.includes(key);
    setSelected({
      ...selected,
      permissions: has ? selected.permissions.filter((p) => p !== key)
                       : [...selected.permissions, key],
    });
  };

  const savePerms = async () => {
    try {
      setSaving(true);
      await api.patch(`/admin/roles/${selected.id}`, { permissions: selected.permissions });
      toast.success(`Updated ${selected.label}`);
      setSelected(null);
      load();
    } catch (err) { toast.error(err.message || "Save failed"); }
    finally { setSaving(false); }
  };

  const createRole = async () => {
    if (!createForm.name.trim() || !createForm.label.trim())
      return toast.error("Name and label are required");
    try {
      setSaving(true);
      await api.post("/admin/roles", { ...createForm, permissions: [] });
      toast.success("Role created");
      setShowCreate(false); setCreateForm({ name: "", label: "", description: "" });
      load();
    } catch (err) { toast.error(err.message || "Create failed"); }
    finally { setSaving(false); }
  };

  const deleteRole = async () => {
    try {
      await api.delete(`/admin/roles/${confirmDelete.id}`);
      toast.success("Role deleted");
      setConfirmDelete(null); load();
    } catch (err) { toast.error(err.message || "Delete failed"); }
  };

  return (
    <div className="admin-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Roles &amp; Permissions</h1>
          <p className="page-subtitle">Define what each role can do across ControlHub.</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate(true)}>+ New role</Button>
      </div>

      <Card>
        <CardHeader title={`${roles.length} roles`}
          subtitle="System roles are built in; custom roles can be added and removed." />
        <CardBody>
          {loading ? <SkeletonTable rows={6} cols={4} /> : roles.length === 0 ? (
            <EmptyState icon="lock" title="No roles" subtitle="Create a custom role to get started." />
          ) : (
            <div className="table-scroll">
              <table className="admin-table">
                <thead><tr><th>Role</th><th>Level</th><th>Permissions</th><th>Users</th><th></th></tr></thead>
                <tbody>
                  {roles.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <div className="admin-role-name">{r.label}
                          {r.is_system && <Badge variant="neutral">system</Badge>}</div>
                        <div className="admin-mono">{r.name}</div>
                      </td>
                      <td>{r.level}</td>
                      <td>{r.name === "superadmin" ? "All permissions" : `${r.permissions.length} enabled`}</td>
                      <td>{r.user_count}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <Button variant="ghost" size="sm" onClick={() => setSelected({ ...r })}>Edit</Button>
                        {!r.is_system && (
                          <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(r)}>Delete</Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Edit permissions */}
      <Modal isOpen={!!selected} onClose={() => setSelected(null)} size="lg"
             title={selected ? `Permissions — ${selected.label}` : ""}
             footer={<>
               <Button variant="ghost" onClick={() => setSelected(null)}>Cancel</Button>
               <Button variant="primary" loading={saving} disabled={selected?.name === "superadmin"}
                       onClick={savePerms}>Save</Button>
             </>}>
        {selected?.name === "superadmin" && (
          <p className="admin-note">The Super Admin role always holds every permission and can't be changed.</p>
        )}
        {selected && Object.entries(groups).map(([group, perms]) => (
          <div key={group} className="admin-perm-group">
            <div className="admin-perm-group-title">{group}</div>
            {perms.map((p) => (
              <label key={p.key} className="admin-perm-row">
                <input type="checkbox" disabled={selected.name === "superadmin"}
                       checked={selected.name === "superadmin" || selected.permissions.includes(p.key)}
                       onChange={() => togglePerm(p.key)} />
                <span>{p.label}</span>
                <span className="admin-mono admin-perm-key">{p.key}</span>
              </label>
            ))}
          </div>
        ))}
      </Modal>

      {/* Create role */}
      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="Create custom role"
             footer={<>
               <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
               <Button variant="primary" loading={saving} onClick={createRole}>Create</Button>
             </>}>
        <div className="cm-field">
          <Input label="Slug (lowercase, no spaces)" value={createForm.name}
                 onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} placeholder="ops_analyst" />
        </div>
        <div className="cm-field">
          <Input label="Display label" value={createForm.label}
                 onChange={(e) => setCreateForm({ ...createForm, label: e.target.value })} placeholder="Ops Analyst" />
        </div>
        <div className="cm-field">
          <TextArea label="Description (optional)" rows={2} value={createForm.description}
                    onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })} />
        </div>
        <p className="admin-note">You can toggle its permissions after it's created.</p>
      </Modal>

      <ConfirmModal isOpen={!!confirmDelete} onClose={() => setConfirmDelete(null)} onConfirm={deleteRole}
        title="Delete role?" confirmText="Delete" confirmVariant="danger"
        message={confirmDelete ? `Delete the "${confirmDelete.label}" role? This can't be undone.` : ""} />
    </div>
  );
}
