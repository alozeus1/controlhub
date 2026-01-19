export async function refreshToken() {
  const token = localStorage.getItem("token");
  if (!token) return;

  const res = await fetch("http://localhost:9000/auth/refresh", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (res.status !== 200) {
    console.warn("Refresh failed");
    return;
  }

  const data = await res.json();
  localStorage.setItem("token", data.access_token);
}
