import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import controlhubLogo from "../assets/brand/controlhub-logo.svg";
import "./ForgotPassword.css";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSubmitted(true);
    } catch (err) {
      setError(err.response?.data?.error || "An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="forgot-page">
      <div className="forgot-bg" />
      <div className="forgot-container">
        <div className="forgot-card">
          <div className="forgot-header">
            <img src={controlhubLogo} alt="Web Forx ControlHub" className="forgot-logo" />
            <h1 className="forgot-title">Reset your password</h1>
            <p className="forgot-subtitle">
              Enter your email address and we'll send you a reset link.
            </p>
          </div>

          {submitted ? (
            <div className="forgot-success">
              <div className="forgot-success-icon">✅</div>
              <p className="forgot-success-msg">
                If this email exists, a password reset link has been sent. Check your inbox.
              </p>
              <Link to="/ui/login" className="forgot-back-link">
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
              {error && <div className="forgot-error">{error}</div>}
              <form onSubmit={handleSubmit} className="forgot-form">
                <div className="form-group">
                  <label className="form-label">Email address</label>
                  <input
                    className="form-input"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                  />
                </div>
                <button className="forgot-button" type="submit" disabled={loading}>
                  {loading ? (
                    <span className="forgot-button-loading">
                      <span className="forgot-spinner" />
                      Sending...
                    </span>
                  ) : (
                    "Send Reset Link"
                  )}
                </button>
              </form>
              <div className="forgot-footer">
                <Link to="/ui/login" className="forgot-back-link">
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
