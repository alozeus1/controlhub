import { getToken, tryRefreshToken, clearTokens } from "./auth";
import { promptForElevation } from "./elevation";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:9000";

class ApiError extends Error {
  constructor(message, response) {
    super(message);
    this.response = response;
  }
}

async function parseResponseBody(res, responseType) {
  if (responseType === "blob") {
    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    if (contentType.includes("application/json")) {
      const text = await res.text();
      return text ? JSON.parse(text) : null;
    }
    return res.blob();
  }
  if (responseType === "text") {
    return res.text();
  }

  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("Invalid JSON response", { status: res.status, raw: text });
  }
}

async function request(method, path, body = null, retry = true, requestOptions = {}) {
  // Prefer sessionStorage token; fall back to legacy localStorage
  const token = getToken() || localStorage.getItem("token");
  const responseType = requestOptions.responseType || "json";
  const extraHeaders = requestOptions.headers || {};

  const fetchOptions = {
    method,
    headers: {
      ...(responseType !== "blob" ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...extraHeaders,
    },
  };

  if (body) {
    fetchOptions.body = responseType === "blob" ? body : JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, fetchOptions);
  } catch (err) {
    console.error("API unreachable:", err);
    throw new ApiError("Unable to connect to API.", { data: { error: "Network error" } });
  }

  // On 401, attempt one silent token refresh then retry.
  // Callers can pass { skip401Redirect: true } (e.g. the login form) so a 401
  // surfaces as a normal error to handle inline instead of forcing a redirect.
  if (res.status === 401 && retry && !requestOptions.skip401Redirect) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return request(method, path, body, false, requestOptions);
    }
    clearTokens();
    window.location.href = "/ui/login";
    return { data: null };
  }

  const data = await parseResponseBody(res, responseType);
  const headers = Object.fromEntries(res.headers.entries());

  // On 403 ELEVATION_REQUIRED, prompt for just-in-time elevation and, if the
  // user completes it, retry once. Mirrors the silent-refresh path above so
  // individual pages never have to handle elevation themselves.
  if (res.status === 403 && data?.code === "ELEVATION_REQUIRED" && retry) {
    const elevated = await promptForElevation(data.permission_key);
    if (elevated) {
      return request(method, path, body, false, requestOptions);
    }
  }

  if (!res.ok) {
    // Surface validation details so users see WHAT failed, not just "Validation failed"
    const details = Array.isArray(data?.details) && data.details.length ? `: ${data.details.join("; ")}` : "";
    throw new ApiError(`${data?.error || "Request failed"}${details}`, { data, status: res.status, headers });
  }

  return { data, status: res.status, headers };
}

async function uploadFile(path, file, onProgress = null) {
  const token = getToken() || localStorage.getItem("token");

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100);
        onProgress(percent, event.loaded, event.total);
      }
    });

    xhr.addEventListener("load", () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (e) {
        data = { error: "Invalid response" };
      }

      if (xhr.status === 401) {
        clearTokens();
        window.location.href = "/ui/login";
        resolve({ data: null });
        return;
      }

      if (xhr.status >= 400) {
        reject(new ApiError(data.error || "Upload failed", { data, status: xhr.status }));
        return;
      }

      resolve({ data });
    });

    xhr.addEventListener("error", () => {
      reject(new ApiError("Unable to connect to API.", { data: { error: "Network error" } }));
    });

    xhr.addEventListener("abort", () => {
      reject(new ApiError("Upload cancelled", { data: { error: "Cancelled" } }));
    });

    xhr.open("POST", `${API_BASE}${path}`);
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.send(formData);
  });
}

// PATCH/PUT are tunneled as POST + X-HTTP-Method-Override because some
// proxies, security tools, and extensions silently drop those verbs while
// passing POST. The backend's MethodOverrideMiddleware restores the real
// method before routing.
const withOverride = (method, options = {}) => ({
  ...options,
  headers: { ...(options.headers || {}), "X-HTTP-Method-Override": method },
});

const api = {
  get: (path, options = {}) => request("GET", path, null, true, options),
  post: (path, body, options = {}) => request("POST", path, body, true, options),
  put: (path, body, options = {}) => request("POST", path, body, true, withOverride("PUT", options)),
  patch: (path, body, options = {}) => request("POST", path, body, true, withOverride("PATCH", options)),
  delete: (path, options = {}) => request("DELETE", path, null, true, options),
  upload: (path, file, onProgress) => uploadFile(path, file, onProgress),
};

export default api;
