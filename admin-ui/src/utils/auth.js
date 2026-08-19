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

export function getCurrentUser() {
  try {
    const raw = sessionStorage.getItem("user") || localStorage.getItem("user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function getCurrentRole() {
  return getCurrentUser()?.role || null;
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
      // The server rotates the refresh token on every use and treats a replayed
      // one as theft. Storing the new one is required — keeping the old would
      // trip reuse detection on the next refresh and kill the session.
      setTokens(data.access_token, data.refresh_token);
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
