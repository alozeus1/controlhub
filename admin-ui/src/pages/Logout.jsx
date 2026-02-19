import { useEffect } from "react";
import api from "../utils/api";
import { clearTokens } from "../utils/auth";

export default function Logout() {
  useEffect(() => {
    async function doLogout() {
      try {
        await api.post("/auth/logout", {});
      } catch {
        // Best-effort — proceed even if server-side blocklist fails
      }
      clearTokens();
      window.location.href = "/ui/login";
    }
    doLogout();
  }, []);

  return <p>Logging out...</p>;
}
