import { useEffect, useState } from "react";
import api from "../utils/api";

export default function Uploads() {
  const [uploads, setUploads] = useState([]);

  useEffect(() => {
    async function load() {
      const data = await api.get("/admin/uploads");
      if (data) setUploads(data);
    }
    load();
  }, []);

  return (
    <div style={{ padding: 40 }}>
      <h1 style={{ color: "#00eaff", textShadow: "0 0 10px #00eaff" }}>
        📁 File Uploads
      </h1>

      <table className="cyber-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>User</th>
            <th>Filename</th>
            <th>S3 Key</th>
            <th>Created</th>
          </tr>
        </thead>

        <tbody>
          {uploads.map(u => (
            <tr key={u.id}>
              <td>{u.id}</td>
              <td>{u.user_id}</td>
              <td>{u.filename}</td>
              <td>{u.s3_key}</td>
              <td>{u.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
