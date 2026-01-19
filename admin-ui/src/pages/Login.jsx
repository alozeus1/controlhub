import { useState } from "react";
import api from "../utils/api";
import "./login.css";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleLogin(e) {
    e.preventDefault();
    setErrorMsg(""); // reset error

    try {
      const data = await api.post("/auth/login", { email, password });

      if (!data || !data.access_token) {
        setErrorMsg("Invalid email or password.");
        return;
      }

      // Save JWT token
      localStorage.setItem("token", data.access_token);

      // Redirect to dashboard
      window.location.href = "/ui/dashboard";

    } catch (err) {
      console.error("Login error:", err);
      setErrorMsg("Unable to reach the server. Please try again.");
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1 className="title">Admin Access Portal</h1>

        {errorMsg && (
          <div className="error-box">
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleLogin} className="login-form">
          <input
            className="cyber-input"
            type="email"
            placeholder="Email address"
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <input
            className="cyber-input"
            type="password"
            placeholder="Password"
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          <button className="cyber-button" type="submit">
            <span>LOGIN</span>
          </button>
        </form>
      </div>

      <div className="grid-bg"></div>
    </div>
  );
}
