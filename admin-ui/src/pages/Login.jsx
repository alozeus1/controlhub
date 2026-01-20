import { useState } from "react";
import api from "../utils/api";
import controlhubLogo from "../assets/brand/controlhub-logo.svg";
import webForxMark from "../assets/brand/web-forx-mark.png";
import "./Login.css";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [loading, setLoading] = useState(false);

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
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <div className="login-logo">
              <img src={controlhubLogo} alt="Web Forx ControlHub" className="login-logo-img" />
            </div>
            <h1 className="login-title">Welcome back</h1>
            <p className="login-subtitle">Sign in to access the control hub</p>
          </div>

          {errorMsg && <div className="login-error">{errorMsg}</div>}

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
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                className="form-input"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <button className="login-button" type="submit" disabled={loading}>
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>
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
      <div className="login-bg" />
    </div>
  );
}
