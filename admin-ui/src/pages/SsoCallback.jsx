import { useEffect } from "react";
import { setTokens } from "../utils/auth";
import api from "../utils/api";

/**
 * Receives tokens from the SSO callback via the URL fragment
 * (#access_token=…&refresh_token=…), stores them, loads the user, and
 * redirects into the app. Tokens are in the fragment so they are never sent
 * to the server or written to logs.
 */
export default function SsoCallback() {
  useEffect(() => {
    const run = async () => {
      const frag = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
      const access = frag.get("access_token");
      const refresh = frag.get("refresh_token");
      if (!access) {
        window.location.href = "/ui/login?sso_error=no_token";
        return;
      }
      setTokens(access, refresh);
      localStorage.setItem("token", access);
      try {
        const { data } = await api.get("/auth/me");
        const user = data?.user || data;
        sessionStorage.setItem("user", JSON.stringify(user));
        localStorage.setItem("user", JSON.stringify(user));
        const role = user?.role;
        window.location.href = role === "user" ? "/ui/my-journey"
          : (role === "team_lead" || role === "mentor") ? "/ui/intern-ops"
          : "/ui/dashboard";
      } catch {
        window.location.href = "/ui/dashboard";
      }
    };
    run();
  }, []);

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center",
      background: "var(--color-bg-primary)", color: "var(--color-text-secondary)" }}>
      Signing you in…
    </div>
  );
}
