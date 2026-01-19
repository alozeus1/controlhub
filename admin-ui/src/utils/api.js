// Choose API base depending on environment
// If Docker gives REACT_APP_API_URL → use it
// Otherwise fallback to localhost for browser usage
const API_BASE =
  process.env.REACT_APP_API_URL || "http://localhost:9000";

// Shared request wrapper
async function request(method, path, body = null) {
  const token = localStorage.getItem("token");

  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch (err) {
    console.error("API unreachable:", err);
    throw new Error("Unable to connect to API.");
  }

  // Auto-logout on expired/invalid token
  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "/ui/login";
    return null;
  }

  return res.json();
}

const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  delete: (path) => request("DELETE", path),
};

export default api;
