import { NavLink } from "react-router-dom";
import "./Sidebar.css";

const navItems = [
  { section: "Overview", items: [
    { to: "/ui/dashboard", icon: "📊", label: "Dashboard" },
  ]},
  { section: "Management", items: [
    { to: "/ui/users", icon: "👥", label: "Users" },
    { to: "/ui/uploads", icon: "📁", label: "Uploads" },
    { to: "/ui/jobs", icon: "⚙️", label: "Jobs" },
  ]},
  { section: "System", items: [
    { to: "/ui/audit-logs", icon: "📋", label: "Audit Logs" },
    { to: "/ui/settings", icon: "🔧", label: "Settings" },
  ]},
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <a href="/ui/dashboard" className="sidebar-logo">
          <div className="sidebar-logo-icon">W</div>
          <span className="sidebar-logo-text">Web<span>Forx</span></span>
        </a>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((group) => (
          <div key={group.section} className="sidebar-section">
            <div className="sidebar-section-title">{group.section}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `sidebar-link ${isActive ? "active" : ""}`
                }
              >
                <span className="sidebar-link-icon">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-footer-brand">
          Powered by <a href="https://www.webforxtech.com/" target="_blank" rel="noopener noreferrer">Web Forx</a>
        </div>
      </div>
    </aside>
  );
}
