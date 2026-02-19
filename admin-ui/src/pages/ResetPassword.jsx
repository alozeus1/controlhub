import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "../utils/api";
import controlhubLogo from "../assets/brand/controlhub-logo.svg";
import "./ResetPassword.css";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (!token) {
      setError("Missing reset token. Please request a new link.");
      return;
    }

    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: newPassword });
      setSuccess(true);
    } catch (err) {
      setError(err.response?.data?.error || "Failed to reset password. The link may have expired.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="reset-page">
      <div className="reset-bg" />
      <div className="reset-container">
        <div className="reset-card">
          <div className="reset-header">
            <img src={controlhubLogo} alt="Web Forx ControlHub" className="reset-logo" />
            <h1 className="reset-title">Set new password</h1>
            <p className="reset-subtitle">Enter and confirm your new password below.</p>
          </div>

          {success ? (
            <div className="reset-success">
              <div className="reset-success-icon">✅</div>
              <p className="reset-success-msg">
                Your password has been reset successfully.
              </p>
              <Link to="/ui/login" className="reset-back-link">
                Sign in with new password
              </Link>
            </div>
          ) : (
            <>
              {!token && (
                <div className="reset-error">
                  Missing reset token. Please request a{" "}
                  <Link to="/ui/forgot-password">new link</Link>.
                </div>
              )}
              {error && <div className="reset-error">{error}</div>}
              <form onSubmit={handleSubmit} className="reset-form">
                <div className="form-group">
                  <label className="form-label">New password</label>
                  <div className="form-input-wrapper">
                    <input
                      className="form-input"
                      type={showNew ? "text" : "password"}
                      placeholder="At least 8 characters"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="form-input-toggle"
                      onClick={() => setShowNew(!showNew)}
                      aria-label={showNew ? "Hide password" : "Show password"}
                    >
                      {showNew ? "🙈" : "👁"}
                    </button>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Confirm new password</label>
                  <div className="form-input-wrapper">
                    <input
                      className="form-input"
                      type={showConfirm ? "text" : "password"}
                      placeholder="Repeat your new password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="form-input-toggle"
                      onClick={() => setShowConfirm(!showConfirm)}
                      aria-label={showConfirm ? "Hide password" : "Show password"}
                    >
                      {showConfirm ? "🙈" : "👁"}
                    </button>
                  </div>
                </div>

                <button
                  className="reset-button"
                  type="submit"
                  disabled={loading || !token}
                >
                  {loading ? (
                    <span className="reset-button-loading">
                      <span className="reset-spinner" />
                      Resetting...
                    </span>
                  ) : (
                    "Reset Password"
                  )}
                </button>
              </form>
              <div className="reset-footer">
                <Link to="/ui/login" className="reset-back-link">
                  ← Back to sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
