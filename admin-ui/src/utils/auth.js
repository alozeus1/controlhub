const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:9000";
const AUTH_MODE = (process.env.REACT_APP_AUTH_MODE || "hybrid").toLowerCase();

export function getAuthMode() {
  return AUTH_MODE;
}

export function isCognitoEnabled() {
  return process.env.REACT_APP_ENABLE_COGNITO_LOGIN === "true";
}

export function getToken() {
  return sessionStorage.getItem("access_token");
}

export function getRefreshToken() {
  return sessionStorage.getItem("refresh_token");
}

export function setTokens(accessToken, refreshToken) {
  sessionStorage.setItem("access_token", accessToken);
  if (refreshToken) {
    sessionStorage.setItem("refresh_token", refreshToken);
  }
}

export function clearTokens() {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
  sessionStorage.removeItem("user");
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

export function buildCognitoAuthorizeUrl() {
  const domain = process.env.REACT_APP_COGNITO_DOMAIN;
  const clientId = process.env.REACT_APP_COGNITO_APP_CLIENT_ID;
  const redirectUri = process.env.REACT_APP_COGNITO_REDIRECT_URI || `${window.location.origin}/ui/auth/callback`;
  if (!domain || !clientId) return null;
  const scope = encodeURIComponent("openid email profile");
  const encodedRedirect = encodeURIComponent(redirectUri);
  return `${domain}/oauth2/authorize?identity_provider=Google&response_type=token&client_id=${clientId}&redirect_uri=${encodedRedirect}&scope=${scope}`;
}

export async function exchangeCognitoToken(idToken) {
  const res = await fetch(`${API_BASE}/auth/cognito/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Authentication failed");
  }
  return data;
}

export async function tryRefreshToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${refreshToken}`,
      },
    });

    if (res.status !== 200) {
      clearTokens();
      return false;
    }

    const data = await res.json();
    if (data.access_token) {
      sessionStorage.setItem("access_token", data.access_token);
      return true;
    }
  } catch {
    // noop
  }
  return false;
}

export function isAuthenticated() {
  return !!(getToken() || localStorage.getItem("token"));
}
