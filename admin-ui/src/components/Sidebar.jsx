import { NavLink } from "react-router-dom";
import logoIcon from "../assets/brand/logo-icon.svg";
import { useFeatures } from "../contexts/FeaturesContext";
import "./Sidebar.css";

const getNavItems = (features) => {
  const items = [
    { section: "Overview", items: [
      { to: "/ui/dashboard", icon: "📊", label: "Dashboard" },
    ]},
    { section: "Management", items: [
      { to: "/ui/users", icon: "👥", label: "Users" },
      { to: "/ui/uploads", icon: "📁", label: "Uploads" },
      { to: "/ui/jobs", icon: "⚙️", label: "Jobs" },
    ]},
    { section: "Governance", items: [
      { to: "/ui/approvals", icon: "✅", label: "Approvals" },
      { to: "/ui/policies", icon: "📜", label: "Policies" },
    ]},
  ];

  // Add enterprise features conditionally
  const enterpriseItems = [];
  
  if (features.service_accounts) {
    enterpriseItems.push({ to: "/ui/service-accounts", icon: "🔑", label: "Service Accounts" });
  }
  if (features.notifications) {
    enterpriseItems.push({ to: "/ui/notifications", icon: "🔔", label: "Notifications" });
    enterpriseItems.push({ to: "/ui/alert-rules", icon: "⚡", label: "Alert Rules" });
  }
  if (features.integrations) {
    enterpriseItems.push({ to: "/ui/integrations", icon: "🔗", label: "Integrations" });
  }
  if (features.assets) {
    enterpriseItems.push({ to: "/ui/assets", icon: "🖥️", label: "Assets" });
  }

  if (enterpriseItems.length > 0) {
    items.push({ section: "Enterprise", items: enterpriseItems });
  }

  items.push({ section: "System", items: [
    { to: "/ui/audit-logs", icon: "📋", label: "Audit Logs" },
    { to: "/ui/settings", icon: "🔧", label: "Settings" },
  ]});

  return items;
};

export default function Sidebar() {
  const { features } = useFeatures();
  const navItems = getNavItems(features);
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <a href="/ui/dashboard" className="sidebar-logo">
          <img src={logoIcon} alt="Web Forx" className="sidebar-logo-img" />
          <div className="sidebar-logo-content">
            <span className="sidebar-logo-text"><span>ControlHub</span></span>
            <span className="sidebar-logo-subtitle">by Web Forx Global Inc.</span>
          </div>
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
          <a href="https://www.webforxtech.com/" target="_blank" rel="noopener noreferrer">Web Forx Global Inc.</a>
        </div>
      </div>
    </aside>
  );
}
