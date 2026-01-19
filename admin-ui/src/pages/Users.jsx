import { useEffect, useState } from "react";
import api from "../utils/api";

export default function Users() {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    async function load() {
      const data = await api.get("/admin/users");
      if (data) setUsers(data);
    }
    load();
  }, []);

  return (
    <div>
      <h1 style={{ color: "#00eaff", textShadow: "0 0 10px #00eaff" }}>
        👤 Users
      </h1>

      <table className="cyber-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Email</th>
            <th>Role</th>
            <th>Created</th>
          </tr>
        </thead>

        <tbody>
          {users.map(u => (
            <tr key={u.id}>
              <td>{u.id}</td>
              <td>{u.email}</td>
              <td>{u.role}</td>
              <td>{u.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
