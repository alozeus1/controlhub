import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import controlhubLogo from "../assets/brand/controlhub-logo.svg";
import "./Login.css";
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
    <div className="login-page">
      <div className="login-bg" />
      
      {/* Brand panel reused from Login */}
      <div className="login-brand-panel">
        <div className="login-brand-content">
          <img src={controlhubLogo} alt="Web Forx ControlHub" className="login-brand-logo" />
          <h2 className="login-brand-title">Web Forx ControlHub</h2>
          <p className="login-brand-subtitle">
            Enterprise-grade admin platform for managing users, assets, and governance at scale.
          </p>
        </div>
      </div>

      <div className="login-form-panel">
        <div className="login-container">
          <div className="login-card">
            <div className="login-header">
              <div className="login-logo login-logo-mobile">
                <img src={controlhubLogo} alt="Web Forx ControlHub" className="login-logo-img" />
              </div>
              <h1 className="login-title">Reset your password</h1>
              <p className="login-subtitle">
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
              <form onSubmit={handleSubmit} className="login-form">
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
                <button className="login-button" type="submit" disabled={loading}>
                  {loading ? (
                    <span className="login-button-loading">
                      <span className="login-spinner" />
                      Sending...
                    </span>
                  ) : (
                    "Send Reset Link"
                  )}
                </button>
              </form>
              <div className="login-footer">
                <Link to="/ui/login" className="login-forgot-link">
                  ← Back to sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
      </div>
    </div>
  );
}
