import { useEffect, useState, useCallback } from "react";
import Card, { CardHeader, CardBody, CardFooter } from "./ui/Card";
import Button from "./ui/Button";
import Input from "./ui/Input";
import Badge from "./ui/Badge";
import Modal from "./ui/Modal";
import { useToast } from "./ui/Toast";
import api from "../utils/api";
import "./MfaCard.css";

export default function MfaCard() {
  const [status, setStatus] = useState(null);
  const [setup, setSetup] = useState(null);      // {qr_svg, secret, otpauth_url}
  const [code, setCode] = useState("");
  const [backupCodes, setBackupCodes] = useState(null);
  const [disableOpen, setDisableOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    try { const res = await api.get("/auth/mfa/status"); setStatus(res.data); }
    catch { /* silent */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const startSetup = async () => {
    try { setBusy(true); const res = await api.post("/auth/mfa/setup"); setSetup(res.data); setCode(""); }
    catch (err) { toast.error(err.message || "Could not start setup"); }
    finally { setBusy(false); }
  };

  const verify = async () => {
    try {
      setBusy(true);
      const res = await api.post("/auth/mfa/verify", { code });
      setBackupCodes(res.data.backup_codes || []);
      setSetup(null); setCode("");
      toast.success("MFA enabled");
      load();
    } catch (err) { toast.error(err.message || "Invalid code"); }
    finally { setBusy(false); }
  };

  const disable = async () => {
    try {
      setBusy(true);
      await api.post("/auth/mfa/disable", { code });
      toast.success("MFA disabled");
      setDisableOpen(false); setCode(""); load();
    } catch (err) { toast.error(err.message || "Could not disable MFA"); }
    finally { setBusy(false); }
  };

  const enabled = status?.enabled;

  return (
    <Card>
      <CardHeader title="Two-Factor Authentication (MFA)"
        subtitle="Add a time-based one-time code from an authenticator app." />
      <CardBody>
        <div className="mfa-status-row">
          <Badge variant={enabled ? "success" : "neutral"}>{enabled ? "Enabled" : "Not enabled"}</Badge>
          {status?.required_by_policy && !enabled &&
            <span className="mfa-required">Required by your organization</span>}
          {enabled && <span className="mfa-muted">{status.backup_codes_remaining} backup codes remaining</span>}
        </div>

        {/* Enrollment flow */}
        {!enabled && setup && (
          <div className="mfa-setup">
            <p className="mfa-muted">1. Scan this QR code in your authenticator app (or enter the key manually).</p>
            <div className="mfa-qr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
            <p className="mfa-key">Manual key: <code>{setup.secret}</code></p>
            <p className="mfa-muted">2. Enter the 6-digit code to confirm.</p>
            <div className="mfa-verify-row">
              <Input placeholder="123456" value={code} inputMode="numeric" maxLength={6}
                     onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
              <Button variant="primary" loading={busy} onClick={verify}>Verify &amp; enable</Button>
            </div>
          </div>
        )}

        {/* Backup codes shown once */}
        {backupCodes && (
          <div className="mfa-backup">
            <p className="mfa-muted">Save these backup codes somewhere safe — each works once if you lose your device.</p>
            <div className="mfa-backup-grid">
              {backupCodes.map((c) => <code key={c}>{c}</code>)}
            </div>
            <Button variant="secondary" size="sm" onClick={() => setBackupCodes(null)}>I've saved them</Button>
          </div>
        )}
      </CardBody>
      <CardFooter>
        {!enabled && !setup && <Button variant="primary" loading={busy} onClick={startSetup}>Set up MFA</Button>}
        {enabled && (
          <Button variant="danger" onClick={() => { setCode(""); setDisableOpen(true); }}
                  disabled={status?.required_by_policy}>
            Disable MFA
          </Button>
        )}
      </CardFooter>

      <Modal isOpen={disableOpen} onClose={() => setDisableOpen(false)} title="Disable MFA"
             footer={<>
               <Button variant="ghost" onClick={() => setDisableOpen(false)}>Cancel</Button>
               <Button variant="danger" loading={busy} onClick={disable}>Disable</Button>
             </>}>
        <p className="mfa-muted">Enter a current authenticator code (or a backup code) to confirm.</p>
        <Input placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
      </Modal>
    </Card>
  );
}
