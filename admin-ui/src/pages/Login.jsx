import { useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import { buildCognitoAuthorizeUrl, getAuthMode, isCognitoEnabled, setTokens } from "../utils/auth";
import controlhubLogo from "../assets/brand/controlhub-logo.svg";
import webForxMark from "../assets/brand/web-forx-mark.png";
import "./Login.css";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const authMode = getAuthMode();
  const cognitoEnabled = isCognitoEnabled();
  const cognitoUrl = buildCognitoAuthorizeUrl();

  async function handleLogin(e) {
    e.preventDefault();
    setErrorMsg("");
    setLoading(true);

    try {
      const { data } = await api.post("/auth/login", { email, password });

      if (!data || !data.access_token) {
        setErrorMsg("Invalid email or password.");
        setLoading(false);
        return;
      }

      setTokens(data.access_token, data.refresh_token);
      sessionStorage.setItem("user", JSON.stringify(data.user));
      // Preserve legacy key for components not yet migrated
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));

      window.location.href = "/ui/dashboard";
    } catch (err) {
      console.error("Login error:", err);
      setErrorMsg(err.response?.data?.error || "Unable to reach the server. Please try again.");
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
              <span className="login-brand-feature-icon">🔐</span>
              <span>Role-based access control</span>
            </div>
            <div className="login-brand-feature">
              <span className="login-brand-feature-icon">📋</span>
              <span>Full audit trail</span>
            </div>
            <div className="login-brand-feature">
              <span className="login-brand-feature-icon">✅</span>
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

            {(authMode === "local" || authMode === "hybrid") && (
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
                    {showPassword ? "🙈" : "👁"}
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
            </form>
            )}

            {cognitoEnabled && cognitoUrl && (
              <button className="login-button" type="button" onClick={() => (window.location.href = cognitoUrl)}>
                Sign in with Google
              </button>
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
