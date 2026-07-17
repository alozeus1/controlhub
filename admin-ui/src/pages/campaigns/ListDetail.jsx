import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../../utils/api";
import AppIcon from "../../components/ui/AppIcon";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import Badge from "../../components/ui/Badge";
import Modal from "../../components/ui/Modal";
import Pagination from "../../components/ui/Pagination";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import { countLabel } from "../../utils/plural";
import "./campaigns.css";

export default function ListDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [list, setList] = useState(null);
  const [members, setMembers] = useState([]);
  const [meta, setMeta] = useState({ page: 1, page_size: 25, total: 0 });
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState({});   // id -> true
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    try {
      const res = await api.get("/admin/email/lists");
      setList((res.data.lists || []).find((l) => String(l.id) === String(id)) || null);
    } catch { /* ignore */ }
  }, [id]);

  const loadMembers = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/email/lists/${id}/members?page=${page}&page_size=25`);
      setMembers(res.data.members || []);
      setMeta({ page: res.data.page, page_size: res.data.page_size, total: res.data.total });
    } catch { toast.error("Failed to load members"); }
    finally { setLoading(false); }
  }, [id, toast]);

  useEffect(() => { loadList(); loadMembers(1); }, [loadList, loadMembers]);

  const searchCandidates = useCallback(async (term) => {
    try {
      const params = new URLSearchParams({ page: 1, page_size: 25 });
      if (term) params.set("search", term);
      const res = await api.get(`/admin/email/subscribers?${params}`);
      const memberIds = new Set(members.map((m) => m.id));
      setCandidates((res.data.subscribers || []).filter((s) => !memberIds.has(s.id)));
    } catch { /* ignore */ }
  }, [members]);

  useEffect(() => {
    if (!addOpen) return;
    const t = setTimeout(() => searchCandidates(search), 200);
    return () => clearTimeout(t);
  }, [search, addOpen, searchCandidates]);

  const addPicked = async () => {
    const ids = Object.keys(picked).filter((k) => picked[k]).map(Number);
    if (!ids.length) return toast.error("Select at least one contact");
    try {
      setBusy(true);
      await api.post(`/admin/email/lists/${id}/members`, { subscriber_ids: ids });
      toast.success(`Added ${countLabel(ids.length, "contact")}`);
      setAddOpen(false); setPicked({}); setSearch("");
      loadMembers(1); loadList();
    } catch (err) { toast.error(err.message || "Failed to add"); }
    finally { setBusy(false); }
  };

  const removeMember = async (subId) => {
    try {
      await api.delete(`/admin/email/lists/${id}/members/${subId}`);
      toast.success("Removed from list");
      loadMembers(meta.page); loadList();
    } catch (err) { toast.error(err.message || "Failed to remove"); }
  };

  const pages = Math.max(1, Math.ceil(meta.total / meta.page_size));

  return (
    <div className="cm-page">
      <div className="cm-head">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate("/ui/email/lists")}>← Lists</Button>
          <h1 style={{ marginTop: 6 }}>{list ? list.name : "List"}</h1>
          <p>{countLabel(meta.total, "member")}{list?.description ? ` · ${list.description}` : ""}</p>
        </div>
        <Button variant="primary" icon={<AppIcon name="users" size={16} />} onClick={() => { setPicked({}); setSearch(""); setAddOpen(true); }}>
          Add members
        </Button>
      </div>

      <Card>
        <CardHeader title={countLabel(meta.total, "member")} />
        <CardBody>
          {loading ? <PageLoader message="Loading members…" /> : members.length === 0 ? (
            <div className="cm-empty"><h3>No members yet</h3>
              <p>Add contacts to this list so you can send targeted campaigns.</p></div>
          ) : (
            <>
              <div className="table-scroll">
                <table className="cm-table">
                  <thead><tr><th>Email</th><th>Name</th><th>Status</th><th></th></tr></thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.id}>
                        <td className="cm-mono">{m.email}</td>
                        <td>{m.name || "—"}</td>
                        <td><Badge variant={m.status === "subscribed" ? "success" : "default"}>{m.status}</Badge></td>
                        <td style={{ textAlign: "right" }}>
                          <Button variant="ghost" size="sm" onClick={() => removeMember(m.id)}>Remove</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={meta.page} pages={pages} total={meta.total}
                          pageSize={meta.page_size} onPageChange={(p) => loadMembers(p)} />
            </>
          )}
        </CardBody>
      </Card>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)} title="Add members to list" size="lg"
             footer={<>
               <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
               <Button variant="primary" loading={busy} onClick={addPicked}>
                 Add {Object.values(picked).filter(Boolean).length || ""}
               </Button>
             </>}>
        <Input placeholder="Search contacts by email or name…" value={search}
               onChange={(e) => setSearch(e.target.value)} />
        <div className="cm-picklist">
          {candidates.length === 0 ? (
            <p className="cm-muted">No matching contacts not already in this list.</p>
          ) : candidates.map((s) => (
            <label key={s.id} className="cm-pick-row">
              <input type="checkbox" checked={!!picked[s.id]}
                     onChange={(e) => setPicked({ ...picked, [s.id]: e.target.checked })} />
              <span className="cm-mono">{s.email}</span>
              <span className="cm-muted">{s.name || ""}</span>
            </label>
          ))}
        </div>
      </Modal>
    </div>
  );
}
