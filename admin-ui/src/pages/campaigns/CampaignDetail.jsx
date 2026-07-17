import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../../utils/api";
import AppIcon from "../../components/ui/AppIcon";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import Badge from "../../components/ui/Badge";
import Modal, { ConfirmModal } from "../../components/ui/Modal";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import "./campaigns.css";

const statusVariant = (s) => ({ sent: "success", sending: "info", scheduled: "primary",
  draft: "default", failed: "error", paused: "warning" }[s] || "default");

const Metric = ({ label, value, accent }) => (
  <div className="cm-stat">
    <span className={`cm-stat-accent cm-accent-${accent}`} />
    <div className="cm-stat-label">{label}</div>
    <div className="cm-stat-value" style={{ fontSize: 22 }}>{value}</div>
  </div>
);

export default function CampaignDetail() {
  const { id } = useParams();
  const [c, setC] = useState(null);
  const [tab, setTab] = useState("overview");
  const [html, setHtml] = useState("");
  const [loading, setLoading] = useState(true);
  const [testOpen, setTestOpen] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [confirmSend, setConfirmSend] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/email/campaigns/${id}`);
      setC(res.data); setHtml(res.data.html || "");
    } catch (err) { toast.error("Failed to load campaign"); }
    finally { setLoading(false); }
  }, [id, toast]);

  useEffect(() => { load(); }, [load]);

  const saveHtml = async () => {
    try { setBusy(true); await api.patch(`/admin/email/campaigns/${id}`, { html }); toast.success("Saved"); load(); }
    catch (err) { toast.error(err.message || "Save failed"); } finally { setBusy(false); }
  };

  const sendTest = async () => {
    if (!testEmail.trim()) return toast.error("Enter an email");
    try { setBusy(true); const r = await api.post(`/admin/email/campaigns/${id}/test`, { email: testEmail });
      r.data.sent ? toast.success("Test sent") : toast.error(r.data.error || "Test failed");
      setTestOpen(false); }
    catch (err) { toast.error(err.message || "Test failed"); } finally { setBusy(false); }
  };

  const sendCampaign = async () => {
    try { setBusy(true); const r = await api.post(`/admin/email/campaigns/${id}/send`);
      toast.success(`Send ${r.data.mode === "sync" ? "completed" : "queued"} — ${r.data.recipients} recipients`);
      setConfirmSend(false); load(); }
    catch (err) { toast.error(err.message || "Send failed"); } finally { setBusy(false); }
  };

  if (loading || !c) return <PageLoader message="Loading campaign…" />;
  const editable = c.status === "draft" || c.status === "scheduled";

  return (
    <div className="cm-page">
      <div className="cm-head">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate("/ui/email/campaigns")}>← Campaigns</Button>
          <h1 style={{ marginTop: 6 }}>{c.name} <Badge variant={statusVariant(c.status)}>{c.status}</Badge></h1>
          <p>{c.subject}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" onClick={() => setTestOpen(true)}>Send test</Button>
          {editable && <Button variant="primary" icon={<AppIcon name="bell" size={16} />} onClick={() => setConfirmSend(true)}>Send campaign</Button>}
        </div>
      </div>

      <div className="cm-tabs">
        <button className={`cm-tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>Overview</button>
        <button className={`cm-tab ${tab === "design" ? "active" : ""}`} onClick={() => setTab("design")}>Design</button>
      </div>

      {tab === "overview" && (
        <>
          <div className="cm-stats">
            <Metric label="Recipients" value={c.total_recipients} accent="blue" />
            <Metric label="Sent" value={c.sent_count} accent="violet" />
            <Metric label="Delivered" value={c.delivered_count} accent="green" />
            <Metric label="Open rate" value={`${c.open_rate}%`} accent="green" />
            <Metric label="Click rate" value={`${c.click_rate}%`} accent="amber" />
            <Metric label="Bounce rate" value={`${c.bounce_rate}%`} accent="red" />
          </div>
          <Card>
            <CardHeader title="Deliverability" subtitle="Reputation-critical signals" />
            <CardBody>
              <div className="cm-health">
                <div className="cm-health-item">Bounces<b>{c.bounce_count}</b></div>
                <div className="cm-health-item">Complaints<b>{c.complaint_count}</b></div>
                <div className="cm-health-item">Failed<b>{c.failed_count}</b></div>
                <div className="cm-health-item">Complaint rate<b>{c.complaint_rate}%</b></div>
              </div>
            </CardBody>
          </Card>
        </>
      )}

      {tab === "design" && (
        <Card>
          <CardHeader title="Email content" action={editable &&
            <Button variant="primary" size="sm" loading={busy} onClick={saveHtml}>Save</Button>} />
          <CardBody>
            <div className="cm-editor-grid">
              <div>
                <textarea className="cm-code" value={html} disabled={!editable}
                          onChange={(e) => setHtml(e.target.value)} />
                <p style={{ color: "#6b7280", fontSize: 12 }}>
                  {editable ? "Merge tags: {{name}}, {{email}}. Unsubscribe footer is added automatically."
                            : "This campaign has been sent and is read-only."}
                </p>
              </div>
              <div>
                <label className="cm-field" style={{ display: "block" }}>Preview</label>
                {/* Sandboxed preview — untrusted HTML cannot execute in the dashboard. */}
                <iframe className="cm-preview" title="Email preview" sandbox="" srcDoc={html} />
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      <Modal isOpen={testOpen} onClose={() => setTestOpen(false)} title="Send a test email"
             footer={<>
               <Button variant="ghost" onClick={() => setTestOpen(false)}>Cancel</Button>
               <Button variant="primary" loading={busy} onClick={sendTest}>Send test</Button>
             </>}>
        <div className="cm-field">
          <Input label="Recipient" type="email" value={testEmail}
                 onChange={(e) => setTestEmail(e.target.value)} placeholder="you@webforx.tech" />
        </div>
      </Modal>

      <ConfirmModal isOpen={confirmSend} onClose={() => setConfirmSend(false)} onConfirm={sendCampaign}
        title="Send this campaign?" confirmText="Send now" confirmVariant="primary" loading={busy}
        message={`This will send "${c.name}" to all subscribed members of the target list. Suppressed contacts are automatically excluded.`} />
    </div>
  );
}
