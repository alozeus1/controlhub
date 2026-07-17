import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import { setTokens } from "../utils/auth";
import controlhubLogo from "../assets/brand/controlhub-logo.svg";
import webForxMark from "../assets/brand/web-forx-mark.png";
import AppIcon from "../components/ui/AppIcon";
import "./login.css";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [loading, setLoading] = useState(false);
  // MFA second-factor step
  const [mfaToken, setMfaToken] = useState(null);
  const [mfaCode, setMfaCode] = useState("");
  // SSO
  const [sso, setSso] = useState({ enabled: false });

  useEffect(() => {
    // Surface SSO callback errors passed back as ?sso_error=...
    const params = new URLSearchParams(window.location.search);
    const ssoErr = params.get("sso_error");
    if (ssoErr) setErrorMsg(`Single sign-on failed (${ssoErr.replace(/_/g, " ")}).`);
    api.get("/auth/sso/status").then((res) => setSso(res.data || { enabled: false })).catch(() => {});
  }, []);

  function finishLogin(data) {
    setTokens(data.access_token, data.refresh_token);
    sessionStorage.setItem("user", JSON.stringify(data.user));
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("user", JSON.stringify(data.user));
    const role = data.user?.role;
    window.location.href = role === "user" ? "/ui/my-journey"
      : (role === "team_lead" || role === "mentor") ? "/ui/intern-ops"
      : "/ui/dashboard";
  }

  async function handleLogin(e) {
    e.preventDefault();
    setErrorMsg("");
    setLoading(true);

    try {
      const { data } = await api.post(
        "/auth/login",
        { email, password },
        { skip401Redirect: true }   // surface auth failures inline instead of redirecting
      );

      if (data?.mfa_required) {
        setMfaToken(data.mfa_token);
        setLoading(false);
        return;   // show the MFA code step
      }

      if (!data || !data.access_token) {
        setErrorMsg("Invalid email or password.");
        setLoading(false);
        return;
      }
      finishLogin(data);
    } catch (err) {
      console.error("Login error:", err);
      setErrorMsg(err.response?.data?.error || "Unable to reach the server. Please try again.");
      setLoading(false);
    }
  }

  async function handleMfa(e) {
    e.preventDefault();
    setErrorMsg("");
    setLoading(true);
    try {
      const { data } = await api.post(
        "/auth/mfa/login-verify",
        { mfa_token: mfaToken, code: mfaCode },
        { skip401Redirect: true }
      );
      if (!data || !data.access_token) {
        setErrorMsg("Invalid authentication code.");
        setLoading(false);
        return;
      }
      finishLogin(data);
    } catch (err) {
      setErrorMsg(err.response?.data?.error || "Invalid authentication code.");
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-bg" />

      {/* Brand panel (hidden on mobile) */}
      <div className="login-brand-panel">
        <div className="login-brand-content">
          <img src={controlhubLogo} alt="Web Forx ControlHub" className="login-brand-logo" />
          <h2 className="login-brand-title">Web Forx ControlHub</h2>
          <p className="login-brand-subtitle">
            Enterprise-grade admin platform for managing users, assets, and governance at scale.
          </p>
          <div className="login-brand-features">
            <div className="login-brand-feature">
              <span className="login-brand-feature-icon"><AppIcon name="lock" size={16} /></span>
              <span>Role-based access control</span>
            </div>
            <div className="login-brand-feature">
              <span className="login-brand-feature-icon"><AppIcon name="document" size={16} /></span>
              <span>Full audit trail</span>
            </div>
            <div className="login-brand-feature">
              <span className="login-brand-feature-icon"><AppIcon name="shield" size={16} /></span>
              <span>Approval governance workflows</span>
            </div>
          </div>
        </div>
      </div>

      {/* Form panel */}
      <div className="login-form-panel">
        <div className="login-container">
          <div className="login-card">
            <div className="login-header">
              <div className="login-logo login-logo-mobile">
                <img src={controlhubLogo} alt="Web Forx ControlHub" className="login-logo-img" />
              </div>
              <h1 className="login-title">Welcome back</h1>
              <p className="login-subtitle">Sign in to access the control hub</p>
            </div>

            {errorMsg && <div className="login-error">{errorMsg}</div>}

            {mfaToken ? (
              <form onSubmit={handleMfa} className="login-form">
                <p className="login-subtitle" style={{ marginBottom: 10 }}>
                  Enter the 6-digit code from your authenticator app (or a backup code).
                </p>
                <div className="form-group">
                  <label className="form-label">Authentication code</label>
                  <input className="form-input" inputMode="numeric" autoFocus placeholder="123456"
                         value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} autoComplete="one-time-code" />
                </div>
                <button className="login-button" type="submit" disabled={loading}>
                  {loading ? (
                    <span className="login-button-loading"><span className="login-spinner" />Verifying...</span>
                  ) : "Verify"}
                </button>
                <button type="button" className="login-forgot-link login-linkbtn"
                        onClick={() => { setMfaToken(null); setMfaCode(""); setErrorMsg(""); }}>
                  ← Back to login
                </button>
              </form>
            ) : (
            <form onSubmit={handleLogin} className="login-form">
              <div className="form-group">
                <label className="form-label">Email</label>
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

              <div className="form-group">
                <div className="form-label-row">
                  <label className="form-label">Password</label>
                  <Link to="/ui/forgot-password" className="login-forgot-link">
                    Forgot password?
                  </Link>
                </div>
                <div className="form-input-wrapper">
                  <input
                    className="form-input"
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    className="form-input-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    <span className={`toggle-icon ${showPassword ? "is-visible" : ""}`}>
                      {showPassword ? (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                          <line x1="1" y1="1" x2="23" y2="23" />
                        </svg>
                      ) : (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      )}
                    </span>
                  </button>
                </div>
              </div>

              <button className="login-button" type="submit" disabled={loading}>
                {loading ? (
                  <span className="login-button-loading">
                    <span className="login-spinner" />
                    Signing in...
                  </span>
                ) : (
                  "Sign In"
                )}
              </button>

              {sso.enabled && (
                <>
                  <div className="login-divider"><span>or</span></div>
                  <button type="button" className="login-sso-button"
                          onClick={() => { window.location.href = sso.login_url; }}>
                    {sso.display_name || "Single Sign-On"}
                  </button>
                </>
              )}
            </form>
            )}
          </div>

          <div className="login-footer">
            <a href="https://www.webforxtech.com/" target="_blank" rel="noopener noreferrer" className="login-footer-brand">
              <img src={webForxMark} alt="Web Forx" className="login-footer-mark" />
            </a>
            <p className="login-footer-text">
              &copy; {new Date().getFullYear()} Web Forx Global Inc. Web Forx™. All rights reserved.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
