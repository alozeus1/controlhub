import { useEffect, useState, useCallback } from "react";
import api from "../../utils/api";
import AppIcon from "../../components/ui/AppIcon";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input, { Select, TextArea } from "../../components/ui/Input";
import Badge from "../../components/ui/Badge";
import Modal, { ConfirmModal } from "../../components/ui/Modal";
import Pagination from "../../components/ui/Pagination";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import { countLabel } from "../../utils/plural";
import "./campaigns.css";

const statusVariant = (s) => ({ subscribed: "success", unsubscribed: "default",
  bounced: "error", complained: "error", pending: "warning" }[s] || "default");

export default function Subscribers() {
  const [subs, setSubs] = useState([]);
  const [lists, setLists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState({ page: 1, page_size: 25, total: 0 });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState({});          // id -> true
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [editRow, setEditRow] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [addToList, setAddToList] = useState(null);       // {ids:[...]} target for add-to-list modal
  const [listChoice, setListChoice] = useState("");
  const [form, setForm] = useState({ email: "", name: "" });
  const [importText, setImportText] = useState("");
  const [importList, setImportList] = useState("");
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const load = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page, page_size: 25 });
      if (search) params.set("search", search);
      if (statusFilter) params.set("status", statusFilter);
      const res = await api.get(`/admin/email/subscribers?${params}`);
      setSubs(res.data.subscribers || []);
      setMeta({ page: res.data.page, page_size: res.data.page_size, total: res.data.total });
      setSelected({});
    } catch (err) {
      toast.error("Failed to load subscribers");
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, toast]);

  const loadLists = useCallback(async () => {
    try { const res = await api.get("/admin/email/lists"); setLists(res.data.lists || []); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => { load(1); }, [statusFilter]); // eslint-disable-line
  useEffect(() => { loadLists(); }, [loadLists]);

  const addSubscriber = async () => {
    if (!form.email.trim()) return toast.error("Email is required");
    try {
      setSaving(true);
      await api.post("/admin/email/subscribers", form);
      toast.success("Subscriber added");
      setShowAdd(false); setForm({ email: "", name: "" });
      load(meta.page);
    } catch (err) { toast.error(err.message || "Failed to add"); }
    finally { setSaving(false); }
  };

  const saveEdit = async () => {
    try {
      setSaving(true);
      await api.patch(`/admin/email/subscribers/${editRow.id}`, { name: editRow.name, status: editRow.status });
      toast.success("Subscriber updated");
      setEditRow(null); load(meta.page);
    } catch (err) { toast.error(err.message || "Failed"); }
    finally { setSaving(false); }
  };

  const deleteSub = async () => {
    try {
      await api.delete(`/admin/email/subscribers/${confirmDelete.id}`);
      toast.success("Subscriber deleted");
      setConfirmDelete(null); load(meta.page);
    } catch (err) { toast.error(err.message || "Failed"); }
  };

  const doAddToList = async () => {
    if (!listChoice) return toast.error("Choose a list");
    try {
      setSaving(true);
      await api.post(`/admin/email/lists/${listChoice}/members`, { subscriber_ids: addToList.ids });
      toast.success(`Added ${countLabel(addToList.ids.length, "contact")} to list`);
      setAddToList(null); setListChoice(""); setSelected({});
      loadLists();
    } catch (err) { toast.error(err.message || "Failed"); }
    finally { setSaving(false); }
  };

  const runImport = async () => {
    const rows = importText.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
      const [email, name] = line.split(",").map((x) => (x || "").trim());
      return { email, name };
    });
    if (!rows.length) return toast.error("Paste at least one email");
    try {
      setSaving(true);
      const payload = { rows };
      if (importList) payload.list_id = Number(importList);
      const res = await api.post("/admin/email/subscribers/import", payload);
      const s = res.data;
      toast.success(`Imported ${s.created} new, ${s.updated} updated, ${s.skipped} skipped`);
      setShowImport(false); setImportText(""); setImportList("");
      load(1); loadLists();
    } catch (err) { toast.error(err.message || "Import failed"); }
    finally { setSaving(false); }
  };

  const selectedIds = Object.keys(selected).filter((k) => selected[k]).map(Number);
  const allChecked = subs.length > 0 && subs.every((s) => selected[s.id]);
  const toggleAll = () => {
    if (allChecked) setSelected({});
    else setSelected(Object.fromEntries(subs.map((s) => [s.id, true])));
  };
  const pages = Math.max(1, Math.ceil(meta.total / meta.page_size));

  return (
    <div className="cm-page">
      <div className="cm-head">
        <div><h1>Subscribers</h1><p>Your marketing contacts and their consent status.</p></div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" icon={<AppIcon name="folder" size={16} />} onClick={() => setShowImport(true)}>Import CSV</Button>
          <Button variant="primary" icon={<AppIcon name="users" size={16} />} onClick={() => setShowAdd(true)}>Add subscriber</Button>
        </div>
      </div>

      <Card>
        <CardHeader title={countLabel(meta.total, "contact")} action={
          <div className="cm-toolbar">
            <form className="cm-search" onSubmit={(e) => { e.preventDefault(); load(1); }}>
              <Input placeholder="Search email or name…" value={search}
                     onChange={(e) => setSearch(e.target.value)} />
            </form>
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              <option value="subscribed">Subscribed</option>
              <option value="unsubscribed">Unsubscribed</option>
              <option value="bounced">Bounced</option>
              <option value="complained">Complained</option>
            </Select>
          </div>
        } />
        <CardBody>
          {selectedIds.length > 0 && (
            <div className="cm-bulkbar">
              <span>{countLabel(selectedIds.length, "contact")} selected</span>
              <Button variant="secondary" size="sm"
                      onClick={() => { setListChoice(""); setAddToList({ ids: selectedIds }); }}>
                Add to list
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setSelected({})}>Clear</Button>
            </div>
          )}
          {loading ? <PageLoader message="Loading…" /> : subs.length === 0 ? (
            <div className="cm-empty"><h3>No subscribers</h3>
              <p>Add a contact or import a CSV to start building your audience.</p></div>
          ) : (
            <>
              <div className="table-scroll">
                <table className="cm-table">
                  <thead><tr>
                    <th style={{ width: 34 }}><input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label="Select all" /></th>
                    <th>Email</th><th>Name</th><th>Status</th><th>Source</th><th>Added</th><th></th>
                  </tr></thead>
                  <tbody>
                    {subs.map((s) => (
                      <tr key={s.id}>
                        <td><input type="checkbox" checked={!!selected[s.id]}
                                   onChange={(e) => setSelected({ ...selected, [s.id]: e.target.checked })}
                                   aria-label={`Select ${s.email}`} /></td>
                        <td className="cm-mono">{s.email}</td>
                        <td>{s.name || "—"}</td>
                        <td><Badge variant={statusVariant(s.status)}>{s.status}</Badge></td>
                        <td>{s.consent_source || "—"}</td>
                        <td>{s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}</td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          <Button variant="ghost" size="sm"
                                  onClick={() => { setListChoice(""); setAddToList({ ids: [s.id] }); }}>Add to list</Button>
                          <Button variant="ghost" size="sm" onClick={() => setEditRow({ ...s })}>Edit</Button>
                          <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(s)}>Delete</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={meta.page} pages={pages} total={meta.total}
                          pageSize={meta.page_size} onPageChange={(p) => load(p)} />
            </>
          )}
        </CardBody>
      </Card>

      {/* Add subscriber */}
      <Modal isOpen={showAdd} onClose={() => setShowAdd(false)} title="Add subscriber"
             footer={<>
               <Button variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Button>
               <Button variant="primary" loading={saving} onClick={addSubscriber}>Add</Button>
             </>}>
        <div className="cm-field">
          <Input label="Email" type="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="person@example.com" />
        </div>
        <div className="cm-field">
          <Input label="Name (optional)" value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Jane Doe" />
        </div>
      </Modal>

      {/* Edit subscriber */}
      <Modal isOpen={!!editRow} onClose={() => setEditRow(null)} title="Edit subscriber"
             footer={<>
               <Button variant="ghost" onClick={() => setEditRow(null)}>Cancel</Button>
               <Button variant="primary" loading={saving} onClick={saveEdit}>Save</Button>
             </>}>
        {editRow && (
          <>
            <div className="cm-field"><Input label="Email" value={editRow.email} disabled /></div>
            <div className="cm-field">
              <Input label="Name" value={editRow.name || ""}
                     onChange={(e) => setEditRow({ ...editRow, name: e.target.value })} />
            </div>
            <div className="cm-field">
              <Select label="Status" value={editRow.status}
                      onChange={(e) => setEditRow({ ...editRow, status: e.target.value })}>
                <option value="subscribed">Subscribed</option>
                <option value="unsubscribed">Unsubscribed</option>
                <option value="pending">Pending</option>
              </Select>
            </div>
          </>
        )}
      </Modal>

      {/* Add to list */}
      <Modal isOpen={!!addToList} onClose={() => setAddToList(null)} title="Add to list"
             footer={<>
               <Button variant="ghost" onClick={() => setAddToList(null)}>Cancel</Button>
               <Button variant="primary" loading={saving} onClick={doAddToList}>Add</Button>
             </>}>
        <p className="cm-muted" style={{ marginTop: 0 }}>
          Add {addToList ? countLabel(addToList.ids.length, "contact") : ""} to:
        </p>
        <Select value={listChoice} onChange={(e) => setListChoice(e.target.value)}>
          <option value="">Choose a list…</option>
          {lists.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.member_count})</option>)}
        </Select>
        {lists.length === 0 && <p className="cm-muted">No lists yet — create one under Lists first.</p>}
      </Modal>

      {/* Import */}
      <Modal isOpen={showImport} onClose={() => setShowImport(false)} title="Import subscribers"
             footer={<>
               <Button variant="ghost" onClick={() => setShowImport(false)}>Cancel</Button>
               <Button variant="primary" loading={saving} onClick={runImport}>Import</Button>
             </>}>
        <p style={{ color: "#9ca3af", fontSize: 13, marginTop: 0 }}>
          One contact per line: <code>email,name</code>. Suppressed addresses are never re-subscribed.
        </p>
        <TextArea rows={7} value={importText} onChange={(e) => setImportText(e.target.value)}
                  placeholder={"ada@example.com,Ada Lovelace\ngrace@example.com,Grace Hopper"} />
        <div className="cm-field" style={{ marginTop: 12 }}>
          <Select label="Add imported contacts to list (optional)" value={importList}
                  onChange={(e) => setImportList(e.target.value)}>
            <option value="">— No list —</option>
            {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </Select>
        </div>
      </Modal>

      <ConfirmModal isOpen={!!confirmDelete} onClose={() => setConfirmDelete(null)} onConfirm={deleteSub}
        title="Delete subscriber?" confirmText="Delete" confirmVariant="danger"
        message={confirmDelete ? `Delete ${confirmDelete.email}? This removes them from all lists.` : ""} />
    </div>
  );
}
