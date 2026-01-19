import { useEffect, useState } from "react";
import api from "../utils/api";
import {
  LineChart, Line,
  PieChart, Pie,
  BarChart, Bar,
  XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer
} from "recharts";

export default function Dashboard() {
  const [users, setUsers] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    async function load() {
      setUsers(await api.get("/admin/users") || []);
      setUploads(await api.get("/admin/uploads") || []);
      setJobs(await api.get("/admin/jobs") || []);
    }
    load();
  }, []);

  return (
    <div>

      <h1 style={{ color: "#00eaff", textShadow: "0 0 15px #00eaff" }}>
        📊 Analytics Dashboard
      </h1>

      {/* Top Stats */}
      <div style={{ display: "flex", gap: 20, marginTop: 20 }}>
        <div className="cyber-card">Users: {users.length}</div>
        <div className="cyber-card">Uploads: {uploads.length}</div>
        <div className="cyber-card">Jobs: {jobs.length}</div>
      </div>

      {/* Charts Section */}
      <div style={{ display: "flex", marginTop: 40, gap: 40 }}>
        
        {/* Pie Chart: Job Status */}
        <div className="cyber-card" style={{ width: "40%", height: 300 }}>
          <h3>Job Status</h3>
          <ResponsiveContainer>
            <PieChart>
              <Pie
                data={[
                  { name: "Pending", value: jobs.filter(j => j.status === "pending").length },
                  { name: "Completed", value: jobs.filter(j => j.status === "completed").length },
                  { name: "Failed", value: jobs.filter(j => j.status === "failed").length }
                ]}
                dataKey="value"
                outerRadius={100}
                fill="#00eaff"
              />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Line Chart: Upload Growth */}
        <div className="cyber-card" style={{ width: "60%", height: 300 }}>
          <h3>Uploads Over Time</h3>
          <ResponsiveContainer>
            <LineChart
              data={uploads.map(u => ({ created_at: u.created_at, value: 1 }))}
            >
              <XAxis dataKey="created_at" hide />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke="#00eaff" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
