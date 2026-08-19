import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "./ui/Modal";
import Button from "./ui/Button";
import Input from "./ui/Input";
import api from "../utils/api";
import { registerElevationHandler } from "../utils/elevation";

const MIN_REASON = 10;

/**
 * Just-in-time elevation prompt.
 *
 * Mounted once at the app root. When any request comes back 403
 * ELEVATION_REQUIRED, this collects a reason plus a fresh second factor, calls
 * /admin/elevation/request, and resolves the pending promise so the API client
 * can retry the original request.
 *
 * The second factor is re-entered here on purpose: the whole point is to prove
 * the human is present, so it cannot be read off the existing session.
 */
export default function ElevationGate() {
  const [open, setOpen] = useState(false);
  const [permissionKey, setPermissionKey] = useState("");
  const [reason, setReason] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [password, setPassword] = useState("");
  const [needsMfa, setNeedsMfa] = useState(false);
  const [pendingApproval, setPendingApproval] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Holds the resolve() of the promise the API client is awaiting.
  const resolverRef = useRef(null);

  const reset = useCallback(() => {
    setReason("");
    setMfaCode("");
    setPassword("");
    setNeedsMfa(false);
    setPendingApproval(false);
    setError("");
    setBusy(false);
  }, []);

  const finish = useCallback((granted) => {
    setOpen(false);
    reset();
    const resolve = resolverRef.current;
    resolverRef.current = null;
    if (resolve) resolve(granted);
  }, [reset]);

  useEffect(() => {
    return registerElevationHandler((key) => {
      setPermissionKey(key || "");
      setOpen(true);
      return new Promise((resolve) => {
        // A second prompt while one is open would strand the first promise.
        if (resolverRef.current) resolverRef.current(false);
        resolverRef.current = resolve;
      });
    });
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (reason.trim().length < MIN_REASON) {
      setError(`Please give a reason of at least ${MIN_REASON} characters.`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await api.post("/admin/elevation/request", {
        permission_key: permissionKey,
        reason: reason.trim(),
        ...(mfaCode ? { mfa_code: mfaCode } : {}),
        ...(password ? { password } : {}),
      });
      if (res.status === 202) {
        // Dual-approval permission: inert until a second person approves.
        setPendingApproval(true);
        setBusy(false);
        return;
      }
      finish(true);
    } catch (err) {
      const code = err.response?.data?.code;
      if (code === "MFA_CODE_REQUIRED" || code === "INVALID_MFA_CODE") {
        setNeedsMfa(true);
      }
      setError(err.response?.data?.error || "Elevation failed.");
      setBusy(false);
    }
  };

  if (!open) return null;

  if (pendingApproval) {
    return (
      <Modal
        isOpen
        onClose={() => finish(false)}
        title="Waiting for a second approver"
        footer={<Button onClick={() => finish(false)}>Close</Button>}
      >
        <p>
          <code>{permissionKey}</code> requires approval from another person who holds
          this permission. Your request has been recorded — once they approve it,
          retry the action.
        </p>
      </Modal>
    );
  }

  return (
    <Modal
      isOpen
      onClose={() => finish(false)}
      title="Elevated access required"
      footer={
        <>
          <Button variant="secondary" onClick={() => finish(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? "Requesting…" : "Elevate"}
          </Button>
        </>
      }
    >
      <form onSubmit={submit}>
        <p>
          This action needs temporary elevated access to <code>{permissionKey}</code>.
          Confirm it is you, and say why — both are recorded in the audit log.
        </p>

        <Input
          label="Reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. rotating the production database password"
          autoFocus
          required
        />

        {needsMfa ? (
          <Input
            label="Authenticator code"
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value)}
            placeholder="123456"
            inputMode="numeric"
            autoComplete="one-time-code"
          />
        ) : (
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        )}

        {error && <p role="alert" style={{ color: "var(--danger, #e5484d)" }}>{error}</p>}
      </form>
    </Modal>
  );
}
