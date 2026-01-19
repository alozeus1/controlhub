import { useEffect, useState } from "react";
import api from "../utils/api";

export default function Jobs() {
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    async function load() {
      const data = await api.get("/admin/jobs");
      if (data) setJobs(data);
    }
    load();
  }, []);

  return (
    <div style={{ padding: 40 }}>
      <h1 style={{ color: "#00eaff", textShadow: "0 0 10px #00eaff" }}>
        🛠️ Background Jobs
      </h1>

      <table className="cyber-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Job ID</th>
            <th>User</th>
            <th>Status</th>
            <th>Created</th>
          </tr>
        </thead>

        <tbody>
          {jobs.map(j => (
            <tr key={j.id}>
              <td>{j.id}</td>
              <td>{j.job_id}</td>
              <td>{j.user_id}</td>
              <td>{j.status}</td>
              <td>{j.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
