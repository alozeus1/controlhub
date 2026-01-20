const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:9000";

class ApiError extends Error {
  constructor(message, response) {
    super(message);
    this.response = response;
  }
}

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
    throw new ApiError("Unable to connect to API.", { data: { error: "Network error" } });
  }

  const data = await res.json();

  if (res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/ui/login";
    return { data: null };
  }

  if (!res.ok) {
    throw new ApiError(data.error || "Request failed", { data, status: res.status });
  }

  return { data };
}

async function uploadFile(path, file, onProgress = null) {
  const token = localStorage.getItem("token");
  
  const formData = new FormData();
  formData.append("file", file);
  
  const options = {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  };
  
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch (err) {
    console.error("API unreachable:", err);
    throw new ApiError("Unable to connect to API.", { data: { error: "Network error" } });
  }
  
  const data = await res.json();
  
  if (res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/ui/login";
    return { data: null };
  }
  
  if (!res.ok) {
    throw new ApiError(data.error || "Upload failed", { data, status: res.status });
  }
  
  return { data };
}

const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
  delete: (path) => request("DELETE", path),
  upload: (path, file, onProgress) => uploadFile(path, file, onProgress),
};

export default api;
