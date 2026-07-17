import { useEffect, useState, useCallback } from "react";
import api from "../../utils/api";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input, { Select } from "../../components/ui/Input";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import "./admin.css";

const TIMEZONES = ["UTC", "America/New_York", "America/Chicago", "America/Los_Angeles",
  "Europe/London", "Europe/Berlin", "Africa/Lagos", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore"];
const LOCALES = ["en-US", "en-GB", "fr-FR", "de-DE", "es-ES", "pt-BR"];

export default function Organization() {
  const [s, setS] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [domains, setDomains] = useState("");
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get("/admin/org-settings");
      setS(res.data);
      setDomains((res.data.allowed_signup_domains || []).join(", "));
    } catch (err) { toast.error("Failed to load organization settings"); }
    finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try {
      setSaving(true);
      await api.put("/admin/org-settings", {
        org_name: s.org_name, logo_url: s.logo_url, timezone: s.timezone,
        locale: s.locale, allowed_signup_domains: domains,
      });
      toast.success("Organization settings saved");
      load();
    } catch (err) { toast.error(err.message || "Save failed"); }
    finally { setSaving(false); }
  };

  if (loading || !s) return <PageLoader message="Loading organization settings…" />;

  return (
    <div className="admin-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Organization</h1>
          <p className="page-subtitle">Company-wide identity, defaults, and sign-up policy.</p>
        </div>
        <Button variant="primary" loading={saving} onClick={save}>Save changes</Button>
      </div>

      <Card>
        <CardHeader title="Branding &amp; identity" />
        <CardBody>
          <div className="admin-form-grid">
            <div className="cm-field">
              <Input label="Organization name" value={s.org_name || ""}
                     onChange={(e) => setS({ ...s, org_name: e.target.value })} />
            </div>
            <div className="cm-field">
              <Input label="Logo URL" value={s.logo_url || ""}
                     onChange={(e) => setS({ ...s, logo_url: e.target.value })}
                     placeholder="https://…/logo.png" />
            </div>
          </div>
          {s.logo_url && (
            <div className="admin-logo-preview">
              <img src={s.logo_url} alt="Logo preview" onError={(e) => { e.target.style.display = "none"; }} />
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Localization" />
        <CardBody>
          <div className="admin-form-grid">
            <div className="cm-field">
              <Select label="Default timezone" value={s.timezone}
                      onChange={(e) => setS({ ...s, timezone: e.target.value })}>
                {TIMEZONES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
            </div>
            <div className="cm-field">
              <Select label="Default locale" value={s.locale}
                      onChange={(e) => setS({ ...s, locale: e.target.value })}>
                {LOCALES.map((l) => <option key={l} value={l}>{l}</option>)}
              </Select>
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Sign-up domain allowlist"
          subtitle="Only these email domains may register or be invited. Leave empty to allow any." />
        <CardBody>
          <Input label="Allowed domains (comma-separated)" value={domains}
                 onChange={(e) => setDomains(e.target.value)}
                 placeholder="webforx.tech, webforxtech.com" />
        </CardBody>
      </Card>
    </div>
  );
}
