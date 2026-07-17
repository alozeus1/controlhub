import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../../utils/api";
import AppIcon from "../../components/ui/AppIcon";
import Card, { CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input, { TextArea } from "../../components/ui/Input";
import Modal, { ConfirmModal } from "../../components/ui/Modal";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import { countLabel } from "../../utils/plural";
import "./campaigns.css";

export default function EmailLists() {
  const [lists, setLists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState(null);       // list being renamed
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [form, setForm] = useState({ name: "", description: "" });
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get("/admin/email/lists");
      setLists(res.data.lists || []);
    } catch (err) { toast.error("Failed to load lists"); }
    finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const createList = async () => {
    if (!form.name.trim()) return toast.error("Name is required");
    try {
      setSaving(true);
      await api.post("/admin/email/lists", form);
      toast.success("List created");
      setShowAdd(false); setForm({ name: "", description: "" });
      load();
    } catch (err) { toast.error(err.message || "Failed"); }
    finally { setSaving(false); }
  };

  const saveEdit = async () => {
    if (!editing.name.trim()) return toast.error("Name is required");
    try {
      setSaving(true);
      await api.patch(`/admin/email/lists/${editing.id}`, {
        name: editing.name, description: editing.description,
      });
      toast.success("List updated");
      setEditing(null); load();
    } catch (err) { toast.error(err.message || "Failed"); }
    finally { setSaving(false); }
  };

  const deleteList = async () => {
    try {
      await api.delete(`/admin/email/lists/${confirmDelete.id}`);
      toast.success("List deleted");
      setConfirmDelete(null); load();
    } catch (err) { toast.error(err.message || "Failed"); }
  };

  return (
    <div className="cm-page">
      <div className="cm-head">
        <div><h1>Lists &amp; Segments</h1><p>Group subscribers to target campaigns.</p></div>
        <Button variant="primary" icon={<AppIcon name="folder" size={16} />} onClick={() => setShowAdd(true)}>New list</Button>
      </div>

      {loading ? <PageLoader message="Loading lists…" /> : lists.length === 0 ? (
        <Card><CardBody><div className="cm-empty">
          <h3>No lists yet</h3><p>Create your first list, then add subscribers to it.</p>
        </div></CardBody></Card>
      ) : (
        <div className="cm-list-grid">
          {lists.map((l) => (
            <Card key={l.id} className="cm-list-card">
              <CardBody>
                <div className="cm-list-card-top" onClick={() => navigate(`/ui/email/lists/${l.id}`)}>
                  <div className="cm-stat-label">List</div>
                  <div className="cm-list-card-name">{l.name}</div>
                  <div className="cm-stat-value" style={{ fontSize: 22 }}>{l.member_count}</div>
                  <div className="cm-stat-sub">{countLabel(l.member_count, "member")}</div>
                  {l.description && <p className="cm-list-card-desc">{l.description}</p>}
                </div>
                <div className="cm-list-card-actions">
                  <Button variant="ghost" size="sm" onClick={() => navigate(`/ui/email/lists/${l.id}`)}>Manage</Button>
                  <Button variant="ghost" size="sm" onClick={() => setEditing({ ...l })}>Rename</Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(l)}>Delete</Button>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={showAdd} onClose={() => setShowAdd(false)} title="Create list"
             footer={<>
               <Button variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Button>
               <Button variant="primary" loading={saving} onClick={createList}>Create</Button>
             </>}>
        <div className="cm-field">
          <Input label="List name" value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Newsletter subscribers" />
        </div>
        <div className="cm-field">
          <TextArea label="Description (optional)" rows={3} value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
      </Modal>

      <Modal isOpen={!!editing} onClose={() => setEditing(null)} title="Rename list"
             footer={<>
               <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
               <Button variant="primary" loading={saving} onClick={saveEdit}>Save</Button>
             </>}>
        {editing && (
          <>
            <div className="cm-field">
              <Input label="List name" value={editing.name}
                     onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </div>
            <div className="cm-field">
              <TextArea label="Description" rows={3} value={editing.description || ""}
                        onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
            </div>
          </>
        )}
      </Modal>

      <ConfirmModal isOpen={!!confirmDelete} onClose={() => setConfirmDelete(null)} onConfirm={deleteList}
        title="Delete list?" confirmText="Delete" confirmVariant="danger"
        message={confirmDelete ? `Delete "${confirmDelete.name}"? Members stay as contacts; only the list is removed.` : ""} />
    </div>
  );
}
