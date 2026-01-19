import { NavLink } from "react-router-dom";
import "./sidebar.css";

export default function Sidebar() {
  return (
    <div className="sidebar">
      <h2 className="logo">⚡ Admin</h2>

      <nav className="nav">
        <NavLink to="/ui/dashboard">📊 Dashboard</NavLink>
        <NavLink to="/ui/users">👤 Users</NavLink>
        <NavLink to="/ui/uploads">📁 Uploads</NavLink>
        <NavLink to="/ui/jobs">🛠️ Jobs</NavLink>
        <NavLink to="/ui/logout">🚪 Logout</NavLink>
      </nav>
    </div>
  );
}
