import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../../utils/api";
import AppIcon from "../../components/ui/AppIcon";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input, { Select, TextArea } from "../../components/ui/Input";
import Badge from "../../components/ui/Badge";
import Modal from "../../components/ui/Modal";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import { countLabel } from "../../utils/plural";
import "./campaigns.css";

const statusVariant = (s) => ({ sent: "success", sending: "info", scheduled: "primary",
  draft: "default", failed: "error", paused: "warning" }[s] || "default");

const STARTER_HTML = `<div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto">
  <h1 style="color:#111827">Hi {{name}} 👋</h1>
  <p style="color:#374151;line-height:1.6">
    Thanks for being part of Web Forx. Here's what's new this month…
  </p>
  <p><a href="https://webforx.tech" style="background:#3b82f6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none">Read more</a></p>
</div>`;

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [lists, setLists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "", subject: "", from_name: "Web Forx", from_address: "",
    target_list_id: "", html: STARTER_HTML,
  });
  const toast = useToast();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [c, l] = await Promise.all([
        api.get("/admin/email/campaigns?page=1&page_size=50"),
        api.get("/admin/email/lists"),
      ]);
      setCampaigns(c.data.campaigns || []);
      setLists(l.data.lists || []);
    } catch (err) { toast.error("Failed to load campaigns"); }
    finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const resetWizard = () => { setStep(1); setForm({
    name: "", subject: "", from_name: "Web Forx", from_address: "",
    target_list_id: "", html: STARTER_HTML }); };

  const createCampaign = async () => {
    try {
      setSaving(true);
      const payload = { ...form, target_list_id: form.target_list_id ? Number(form.target_list_id) : null };
      const res = await api.post("/admin/email/campaigns", payload);
      toast.success("Campaign created");
      setShowWizard(false); resetWizard();
      navigate(`/ui/email/campaigns/${res.data.id}`);
    } catch (err) { toast.error(err.message || "Failed to create"); }
    finally { setSaving(false); }
  };

  const canNext = () => {
    if (step === 1) return form.name.trim() && form.subject.trim();
    if (step === 2) return !!form.target_list_id;
    return true;
  };

  return (
    <div className="cm-page">
      <div className="cm-head">
        <div><h1>Campaigns</h1><p>Design, review, and send email campaigns.</p></div>
        <Button variant="primary" icon={<AppIcon name="bell" size={16} />} onClick={() => { resetWizard(); setShowWizard(true); }}>
          New campaign
        </Button>
      </div>

      <Card>
        <CardHeader title={countLabel(campaigns.length, "campaign")} />
        <CardBody>
          {loading ? <PageLoader message="Loading…" /> : campaigns.length === 0 ? (
            <div className="cm-empty"><h3>No campaigns yet</h3>
              <p>Create your first campaign and send it to one of your lists.</p></div>
          ) : (
            <table className="cm-table">
              <thead><tr><th>Name</th><th>Subject</th><th>Status</th><th>Recipients</th>
                <th>Opens</th><th>Clicks</th></tr></thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id} className="cm-row-click" onClick={() => navigate(`/ui/email/campaigns/${c.id}`)}>
                    <td>{c.name}</td>
                    <td style={{ color: "#9ca3af" }}>{c.subject}</td>
                    <td><Badge variant={statusVariant(c.status)}>{c.status}</Badge></td>
                    <td>{c.total_recipients}</td>
                    <td>{c.open_rate}%</td>
                    <td>{c.click_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      <Modal isOpen={showWizard} onClose={() => setShowWizard(false)} title="New campaign" size="lg"
             footer={<>
               <Button variant="ghost" onClick={() => setShowWizard(false)}>Cancel</Button>
               {step > 1 && <Button variant="secondary" onClick={() => setStep(step - 1)}>Back</Button>}
               {step < 4
                 ? <Button variant="primary" disabled={!canNext()} onClick={() => setStep(step + 1)}>Next</Button>
                 : <Button variant="primary" loading={saving} onClick={createCampaign}>Create draft</Button>}
             </>}>
        <div className="cm-steps">
          {["Details", "Audience", "Design", "Review"].map((label, i) => {
            const n = i + 1;
            return (
              <div key={label} className={`cm-step ${step === n ? "active" : ""} ${step > n ? "done" : ""}`}>
                <span className="cm-step-num">{step > n ? "✓" : n}</span>{label}
              </div>
            );
          })}
        </div>

        {step === 1 && (
          <>
            <div className="cm-field">
              <Input label="Campaign name" value={form.name}
                     onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="July Newsletter" />
            </div>
            <div className="cm-field">
              <Input label="Subject line" value={form.subject}
                     onChange={(e) => setForm({ ...form, subject: e.target.value })}
                     placeholder="What's new at Web Forx — {{name}}" />
            </div>
            <div className="cm-editor-grid">
              <div className="cm-field">
                <Input label="From name" value={form.from_name}
                       onChange={(e) => setForm({ ...form, from_name: e.target.value })} />
              </div>
              <div className="cm-field">
                <Input label="From address (verified)" value={form.from_address}
                       onChange={(e) => setForm({ ...form, from_address: e.target.value })}
                       placeholder="campaigns@webforx.tech" />
              </div>
            </div>
          </>
        )}

        {step === 2 && (
          <div className="cm-field">
            <Select label="Target list" value={form.target_list_id}
                    onChange={(e) => setForm({ ...form, target_list_id: e.target.value })}>
              <option value="">Select a list…</option>
              {lists.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.member_count})</option>)}
            </Select>
            {lists.length === 0 && <p style={{ color: "#fcd34d", fontSize: 13 }}>
              No lists yet — create one under Lists first.</p>}
          </div>
        )}

        {step === 3 && (
          <div className="cm-editor-grid">
            <div>
              <label className="cm-field" style={{ display: "block" }}>HTML</label>
              <textarea className="cm-code" value={form.html}
                        onChange={(e) => setForm({ ...form, html: e.target.value })} />
              <p style={{ color: "#6b7280", fontSize: 12 }}>Use {"{{name}}"} and {"{{email}}"} for personalization.</p>
            </div>
            <div>
              <label className="cm-field" style={{ display: "block" }}>Preview</label>
              {/* Sandboxed: no scripts/forms/same-origin — HTML can't touch the dashboard. */}
              <iframe className="cm-preview" title="Email preview" sandbox="" srcDoc={form.html} />
            </div>
          </div>
        )}

        {step === 4 && (
          <div>
            <p style={{ color: "#9ca3af", fontSize: 13 }}>Review before creating the draft. You can still test-send and edit after.</p>
            <table className="cm-table">
              <tbody>
                <tr><th>Name</th><td>{form.name}</td></tr>
                <tr><th>Subject</th><td>{form.subject}</td></tr>
                <tr><th>From</th><td>{form.from_name} &lt;{form.from_address || "default sender"}&gt;</td></tr>
                <tr><th>List</th><td>{lists.find((l) => String(l.id) === String(form.target_list_id))?.name || "—"}</td></tr>
              </tbody>
            </table>
          </div>
        )}
      </Modal>
    </div>
  );
}
