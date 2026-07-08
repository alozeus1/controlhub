import { getToken, tryRefreshToken, clearTokens } from "./auth";

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

  // On 401, attempt one silent token refresh then retry
  if (res.status === 401 && retry) {
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

const api = {
  get: (path, options = {}) => request("GET", path, null, true, options),
  post: (path, body, options = {}) => request("POST", path, body, true, options),
  put: (path, body, options = {}) => request("PUT", path, body, true, options),
  patch: (path, body, options = {}) => request("PATCH", path, body, true, options),
  delete: (path, options = {}) => request("DELETE", path, null, true, options),
  upload: (path, file, onProgress) => uploadFile(path, file, onProgress),
};

export default api;
