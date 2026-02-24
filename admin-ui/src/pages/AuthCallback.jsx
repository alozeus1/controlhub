import { useEffect, useState } from "react";
import { exchangeCognitoToken, setTokens } from "../utils/auth";

function parseHashToken(hash) {
  const clean = hash.startsWith("#") ? hash.slice(1) : hash;
  const params = new URLSearchParams(clean);
  return params.get("id_token");
}

export default function AuthCallback() {
  const [error, setError] = useState("");

  useEffect(() => {
    async function run() {
      try {
        const idToken = parseHashToken(window.location.hash);
        if (!idToken) {
          setError("Missing token from identity provider.");
          return;
        }
        const data = await exchangeCognitoToken(idToken);
        setTokens(data.access_token, data.refresh_token);
        sessionStorage.setItem("user", JSON.stringify(data.user));
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("user", JSON.stringify(data.user));
        window.location.href = "/ui/dashboard";
      } catch (e) {
        setError(e.message || "SSO sign-in failed.");
      }
    }
    run();
  }, []);

  return <div style={{ padding: 24 }}>{error ? `Sign-in failed: ${error}` : "Signing you in..."}</div>;
}

export { parseHashToken };
