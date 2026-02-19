const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:9000";

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
  // Also clear legacy localStorage tokens
  localStorage.removeItem("token");
  localStorage.removeItem("user");
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
    // Network error — don't clear tokens, let caller decide
  }
  return false;
}

export function isAuthenticated() {
  return !!(getToken() || localStorage.getItem("token"));
}
