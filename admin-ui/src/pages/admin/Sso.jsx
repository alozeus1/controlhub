import { useEffect, useState, useCallback } from "react";
import api from "../../utils/api";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Input, { Select } from "../../components/ui/Input";
import Badge from "../../components/ui/Badge";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import "./admin.css";

export default function Sso() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [secret, setSecret] = useState("");
  const [mapText, setMapText] = useState("");
  const [domains, setDomains] = useState("");
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get("/admin/sso/config");
      setCfg(res.data);
      setMapText(Object.entries(res.data.claim_role_map || {})
        .map(([k, v]) => `${k}=${v}`).join("\n"));
      setDomains((res.data.allowed_domains || []).join(", "));
    } catch (err) { toast.error("Failed to load SSO config"); }
    finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const parseMap = () => {
    const map = {};
    mapText.split("\n").map((l) => l.trim()).filter(Boolean).forEach((line) => {
      const [k, v] = line.split("=").map((x) => (x || "").trim());
      if (k && v) map[k] = v;
    });
    return map;
  };

  const save = async () => {
    try {
      setSaving(true);
      const payload = {
        enabled: cfg.enabled, display_name: cfg.display_name, discovery_url: cfg.discovery_url,
        client_id: cfg.client_id, default_role: cfg.default_role, role_claim: cfg.role_claim,
        claim_role_map: parseMap(), allowed_domains: domains,
      };
      if (secret) payload.client_secret = secret;
      await api.put("/admin/sso/config", payload);
      toast.success("SSO configuration saved");
      setSecret("");
      load();
    } catch (err) { toast.error(err.message || "Save failed"); }
    finally { setSaving(false); }
  };

  const test = async () => {
    try {
      setTesting(true);
      const res = await api.post("/admin/sso/test");
      res.data.ok ? toast.success(`Discovery OK — issuer ${res.data.issuer}`)
                  : toast.error(res.data.error || "Discovery failed");
    } catch (err) { toast.error(err.response?.data?.error || "Discovery failed"); }
    finally { setTesting(false); }
  };

  if (loading || !cfg) return <PageLoader message="Loading SSO configuration…" />;

  return (
    <div className="admin-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Single Sign-On (OIDC)
            <Badge variant={cfg.enabled ? "success" : "neutral"}>{cfg.enabled ? "Enabled" : "Disabled"}</Badge>
          </h1>
          <p className="page-subtitle">Connect an identity provider (Okta, Azure AD, Google Workspace, Auth0).</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" loading={testing} onClick={test}>Test discovery</Button>
          <Button variant="primary" loading={saving} onClick={save}>Save</Button>
        </div>
      </div>

      <Card>
        <CardHeader title="Provider" />
        <CardBody>
          <label className="admin-toggle">
            <input type="checkbox" checked={cfg.enabled}
                   onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} />
            <span>Enable SSO login</span>
          </label>
          <div className="admin-form-grid" style={{ marginTop: 12 }}>
            <div className="cm-field">
              <Input label="Button label" value={cfg.display_name || ""}
                     onChange={(e) => setCfg({ ...cfg, display_name: e.target.value })}
                     placeholder="Log in with Okta" />
            </div>
            <div className="cm-field">
              <Input label="Discovery URL (.well-known/openid-configuration)" value={cfg.discovery_url || ""}
                     onChange={(e) => setCfg({ ...cfg, discovery_url: e.target.value })}
                     placeholder="https://your-idp/.well-known/openid-configuration" />
            </div>
            <div className="cm-field">
              <Input label="Client ID" value={cfg.client_id || ""}
                     onChange={(e) => setCfg({ ...cfg, client_id: e.target.value })} />
            </div>
            <div className="cm-field">
              <Input label={cfg.has_client_secret ? "Client secret (leave blank to keep current)" : "Client secret"}
                     type="password" value={secret} onChange={(e) => setSecret(e.target.value)}
                     placeholder={cfg.has_client_secret ? "••••••••" : ""} />
            </div>
          </div>
          <p className="admin-note">Redirect / callback URL to register with your IdP:
            <span className="admin-mono"> {window.location.origin.replace(/:\d+$/, ":9000")}/auth/sso/callback</span>
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Role mapping"
          subtitle="Map an SSO claim value to a ControlHub role. Unmapped users get the default role." />
        <CardBody>
          <div className="admin-form-grid">
            <div className="cm-field">
              <Input label="Role claim" value={cfg.role_claim || "groups"}
                     onChange={(e) => setCfg({ ...cfg, role_claim: e.target.value })} placeholder="groups" />
            </div>
            <div className="cm-field">
              <Select label="Default role" value={cfg.default_role}
                      onChange={(e) => setCfg({ ...cfg, default_role: e.target.value })}>
                {["user", "viewer", "people_manager", "admin"].map((r) => <option key={r} value={r}>{r}</option>)}
              </Select>
            </div>
          </div>
          <div className="cm-field">
            <label className="admin-label">Claim → role map (one per line, <code>claim_value=role</code>)</label>
            <textarea className="cm-code" style={{ minHeight: 120 }} value={mapText}
                      onChange={(e) => setMapText(e.target.value)}
                      placeholder={"controlhub-admins=admin\ncontrolhub-viewers=viewer"} />
          </div>
          <div className="cm-field">
            <Input label="Allowed email domains (comma-separated, optional)" value={domains}
                   onChange={(e) => setDomains(e.target.value)} placeholder="webforx.tech" />
          </div>
        </CardBody>
      </Card>

      <p className="admin-note">
        Security: the OIDC id_token is verified against your provider's JWKS (signature, audience,
        issuer, expiry, and nonce) before a session is issued.
      </p>
    </div>
  );
}
