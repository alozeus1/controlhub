import { useEffect, useState, useCallback } from "react";
import api from "../../utils/api";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input, { Select } from "../../components/ui/Input";
import Badge from "../../components/ui/Badge";
import Pagination from "../../components/ui/Pagination";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import "./campaigns.css";

export default function EmailSettings() {
  const [supps, setSupps] = useState([]);
  const [meta, setMeta] = useState({ page: 1, page_size: 25, total: 0 });
  const [ses, setSes] = useState({});
  const [settings, setSettings] = useState(null);
  const [identities, setIdentities] = useState({ available: false, identities: [] });
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [form, setForm] = useState({ email: "", reason: "manual" });
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      const [s, st, cfg, ids] = await Promise.all([
        api.get(`/admin/email/suppressions?page=${page}&page_size=25`),
        api.get("/admin/email/stats"),
        api.get("/admin/email/settings"),
        api.get("/admin/email/identities"),
      ]);
      setSupps(s.data.suppressions || []);
      setMeta({ page: s.data.page, page_size: s.data.page_size, total: s.data.total });
      setSes(st.data.ses || {});
      setSettings(cfg.data);
      setIdentities(ids.data || { available: false, identities: [] });
    } catch (err) { toast.error("Failed to load settings"); }
    finally { setLoading(false); }
  }, [toast]);

  const saveSettings = async () => {
    try {
      setSavingSettings(true);
      await api.put("/admin/email/settings", {
        from_name: settings.from_name, from_address: settings.from_address,
        reply_to: settings.reply_to, footer_org_name: settings.footer_org_name,
        footer_address: settings.footer_address,
      });
      toast.success("Email settings saved");
    } catch (err) { toast.error(err.message || "Save failed"); }
    finally { setSavingSettings(false); }
  };

  useEffect(() => { load(1); }, [load]);

  const addSuppression = async () => {
    if (!form.email.trim()) return toast.error("Email required");
    try { setBusy(true); await api.post("/admin/email/suppressions", form);
      toast.success("Added to suppression list"); setForm({ email: "", reason: "manual" }); load(1); }
    catch (err) { toast.error(err.message || "Failed"); } finally { setBusy(false); }
  };

  const removeSuppression = async (id) => {
    try { await api.delete(`/admin/email/suppressions/${id}`); toast.success("Removed"); load(meta.page); }
    catch (err) { toast.error("Failed to remove"); }
  };

  const pages = Math.max(1, Math.ceil(meta.total / meta.page_size));

  return (
    <div className="cm-page">
      <div className="cm-head">
        <div><h1>Email Settings</h1><p>Deliverability controls and sending health.</p></div>
      </div>

      {settings && (
        <Card>
          <CardHeader title="Sender &amp; compliance footer"
            subtitle="Default from-address and the CAN-SPAM footer added to every email"
            action={<Button variant="primary" size="sm" loading={savingSettings} onClick={saveSettings}>Save</Button>} />
          <CardBody>
            <div className="cm-editor-grid">
              <div className="cm-field">
                <Input label="From name" value={settings.from_name || ""}
                       onChange={(e) => setSettings({ ...settings, from_name: e.target.value })}
                       placeholder="Web Forx" />
              </div>
              <div className="cm-field">
                <Input label="From address" value={settings.from_address || ""}
                       onChange={(e) => setSettings({ ...settings, from_address: e.target.value })}
                       placeholder={settings.ses_from_address || "campaigns@webforx.tech"} />
              </div>
              <div className="cm-field">
                <Input label="Reply-to (optional)" value={settings.reply_to || ""}
                       onChange={(e) => setSettings({ ...settings, reply_to: e.target.value })} />
              </div>
              <div className="cm-field">
                <Input label="Footer organization name" value={settings.footer_org_name || ""}
                       onChange={(e) => setSettings({ ...settings, footer_org_name: e.target.value })}
                       placeholder="Web Forx Technology Limited" />
              </div>
            </div>
            <div className="cm-field">
              <Input label="Footer physical address (required for CAN-SPAM)" value={settings.footer_address || ""}
                     onChange={(e) => setSettings({ ...settings, footer_address: e.target.value })}
                     placeholder="1 Example Ave, Lagos, Nigeria" />
            </div>
            <p className="cm-muted">A one-click unsubscribe link is always appended automatically.</p>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader title="Domain authentication"
          subtitle="Verified sender identities and DKIM status (pair with SPF + DMARC in DNS)" />
        <CardBody>
          {!identities.available ? (
            <p style={{ color: "#9ca3af", fontSize: 13 }}>
              Identity status unavailable in this environment (expected on LocalStack). In production this
              lists each verified sender/domain with its DKIM verification state.
            </p>
          ) : identities.identities.length === 0 ? (
            <p style={{ color: "#9ca3af", fontSize: 13 }}>No SES identities found. Verify a domain in AWS SES.</p>
          ) : (
            <div className="table-scroll">
              <table className="cm-table">
                <thead><tr><th>Identity</th><th>Verification</th><th>DKIM</th></tr></thead>
                <tbody>
                  {identities.identities.map((i) => (
                    <tr key={i.identity}>
                      <td className="cm-mono">{i.identity}</td>
                      <td><Badge variant={i.verification_status === "Success" ? "success" : "warning"}>
                        {i.verification_status}</Badge></td>
                      <td><Badge variant={i.dkim_status === "Success" ? "success" : "default"}>
                        {i.dkim_enabled ? i.dkim_status : "Off"}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="SES sending health" subtitle="Live quota from Amazon SES" />
        <CardBody>
          {ses.available === false ? (
            <p style={{ color: "#9ca3af", fontSize: 13 }}>
              SES status unavailable here (expected on LocalStack). In production this shows your live quota.
            </p>
          ) : (
            <div className="cm-health">
              <div className="cm-health-item">24h sent<b>{ses.sent_last_24_hours ?? "—"}</b></div>
              <div className="cm-health-item">24h limit<b>{ses.max_24_hour_send ?? "—"}</b></div>
              <div className="cm-health-item">Max rate/s<b>{ses.max_send_rate ?? "—"}</b></div>
              <div className="cm-health-item">Sending
                <b><Badge variant={ses.sending_enabled ? "success" : "error"}>
                  {ses.sending_enabled ? "Enabled" : "Paused"}</Badge></b></div>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Suppression list" subtitle="Addresses that will never be emailed — protects sender reputation" />
        <CardBody>
          <div className="cm-toolbar" style={{ marginBottom: 16 }}>
            <Input className="cm-search" placeholder="email to suppress" value={form.email}
                   onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <Select value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}>
              <option value="manual">Manual</option>
              <option value="hard_bounce">Hard bounce</option>
              <option value="complaint">Complaint</option>
              <option value="unsubscribe">Unsubscribe</option>
            </Select>
            <Button variant="primary" loading={busy} onClick={addSuppression}>Add</Button>
          </div>

          {loading ? <PageLoader message="Loading…" /> : supps.length === 0 ? (
            <div className="cm-empty"><h3>Suppression list is empty</h3>
              <p>Bounces and complaints are added here automatically.</p></div>
          ) : (
            <>
              <table className="cm-table">
                <thead><tr><th>Email</th><th>Reason</th><th>Added</th><th></th></tr></thead>
                <tbody>
                  {supps.map((s) => (
                    <tr key={s.id}>
                      <td className="cm-mono">{s.email}</td>
                      <td><Badge variant={s.reason === "complaint" || s.reason === "hard_bounce" ? "error" : "default"}>
                        {s.reason}</Badge></td>
                      <td>{s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}</td>
                      <td><Button variant="ghost" size="sm" onClick={() => removeSuppression(s.id)}>Remove</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination page={meta.page} pages={pages} total={meta.total}
                          pageSize={meta.page_size} onPageChange={(p) => load(p)} />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
