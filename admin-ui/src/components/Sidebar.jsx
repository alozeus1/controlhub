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
    { section: "Security", items: [
      { to: "/ui/secrets", icon: "🔐", label: "Secrets" },
      { to: "/ui/certificates", icon: "🛡️", label: "Certificates" },
      { to: "/ui/feature-flags", icon: "🚩", label: "Feature Flags" },
    ]},
    { section: "DevOps", items: [
      { to: "/ui/env-config", icon: "🗂️", label: "Env Config" },
      { to: "/ui/deployments", icon: "🚀", label: "Deployments" },
      { to: "/ui/incidents", icon: "🚨", label: "Incidents" },
      { to: "/ui/runbooks", icon: "📖", label: "Runbooks" },
    ]},
    { section: "Operations", items: [
      { to: "/ui/workflows", icon: "🔄", label: "Workflows" },
      { to: "/ui/licenses", icon: "📄", label: "Licenses" },
      { to: "/ui/costs", icon: "💰", label: "Cost Tracker" },
    ]},
  ];

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

export default function Sidebar({ isOpen, onClose }) {
  const { features } = useFeatures();
  const navItems = getNavItems(features);

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />
      )}

      <aside className={`sidebar ${isOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-header">
          <a href="/ui/dashboard" className="sidebar-logo">
            <img src={logoIcon} alt="Web Forx" className="sidebar-logo-img" />
            <div className="sidebar-logo-content">
              <span className="sidebar-logo-text"><span>ControlHub</span></span>
              <span className="sidebar-logo-subtitle">by Web Forx Global Inc.</span>
            </div>
          </a>
          {/* Mobile close button */}
          <button
            className="sidebar-close-btn"
            onClick={onClose}
            aria-label="Close sidebar"
          >
            ✕
          </button>
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
                  onClick={onClose}
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
    </>
  );
}
