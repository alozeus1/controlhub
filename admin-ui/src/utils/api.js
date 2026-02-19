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
        localStorage.removeItem("token");
        localStorage.removeItem("user");
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
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  put: (path, body) => request("PUT", path, body),
  patch: (path, body) => request("PATCH", path, body),
  delete: (path) => request("DELETE", path),
  upload: (path, file, onProgress) => uploadFile(path, file, onProgress),
};

export default api;
