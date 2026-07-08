import { NavLink } from "react-router-dom";
import logoIcon from "../assets/brand/logo-icon.svg";
import { useFeatures } from "../contexts/FeaturesContext";
import { getCurrentRole } from "../utils/auth";
import AppIcon from "./ui/AppIcon";
import "./Sidebar.css";

const MANAGER_ROLES = ["superadmin", "hr_admin", "admin", "people_manager"];

const getNavItems = (features, role) => {
  // Basic users (interns) only get their self-service journey.
  if (role === "user") {
    return [
      { section: "My Space", items: [
        { to: "/ui/my-journey", icon: "users", label: "My Journey" },
      ]},
    ];
  }

  // PoCs/team leads and mentors get their review queue plus their own journey,
  // not the full admin surface.
  if (role === "team_lead" || role === "mentor") {
    return [
      { section: "My Space", items: [
        { to: "/ui/my-journey", icon: "users", label: "My Journey" },
      ]},
      { section: "Reviews", items: [
        { to: "/ui/intern-ops", icon: "alert", label: "Intern Ops" },
      ]},
    ];
  }

  const items = [
    { section: "Overview", items: [
      { to: "/ui/dashboard", icon: "dashboard", label: "Dashboard" },
      ...(features.internship_program ? [{ to: "/ui/my-journey", icon: "users", label: "My Journey" }] : []),
    ]},
    { section: "Management", items: [
      { to: "/ui/users", icon: "users", label: "Users" },
      { to: "/ui/uploads", icon: "folder", label: "Uploads" },
      { to: "/ui/jobs", icon: "automation", label: "Jobs" },
    ]},
    { section: "Governance", items: [
      { to: "/ui/approvals", icon: "shield", label: "Approvals" },
      { to: "/ui/policies", icon: "document", label: "Policies" },
    ]},
    { section: "Security", items: [
      { to: "/ui/secrets", icon: "lock", label: "Secrets" },
      { to: "/ui/certificates", icon: "shield", label: "Certificates" },
      { to: "/ui/feature-flags", icon: "flag", label: "Feature Flags" },
    ]},
    { section: "DevOps", items: [
      { to: "/ui/env-config", icon: "document", label: "Env Config" },
      { to: "/ui/deployments", icon: "cloud", label: "Deployments" },
      { to: "/ui/incidents", icon: "alert", label: "Incidents" },
      { to: "/ui/runbooks", icon: "document", label: "Runbooks" },
    ]},
    { section: "Operations", items: [
      { to: "/ui/workflows", icon: "automation", label: "Workflows" },
      { to: "/ui/licenses", icon: "document", label: "Licenses" },
      { to: "/ui/costs", icon: "currency", label: "Cost Tracker" },
      ...(features.people ? [{ to: "/ui/people", icon: "users", label: "People" }] : []),
      ...(features.internship_program ? [{ to: "/ui/internship", icon: "users", label: "Internship Program" }] : []),
      ...(features.internship_program && MANAGER_ROLES.includes(role) ? [{ to: "/ui/intern-ops", icon: "alert", label: "Intern Ops" }] : []),
      ...(features.agent_service ? [{ to: "/ui/exports-reports", icon: "report", label: "Exports & Reports" }] : []),
      ...(features.agent_service ? [{ to: "/ui/agent-requests", icon: "robot", label: "Agent Requests" }] : []),
    ]},
  ];

  const enterpriseItems = [];

  if (features.service_accounts) {
    enterpriseItems.push({ to: "/ui/service-accounts", icon: "lock", label: "Service Accounts" });
  }
  if (features.notifications) {
    enterpriseItems.push({ to: "/ui/notifications", icon: "bell", label: "Notifications" });
    enterpriseItems.push({ to: "/ui/alert-rules", icon: "alert", label: "Alert Rules" });
  }
  if (features.integrations) {
    enterpriseItems.push({ to: "/ui/integrations", icon: "link", label: "Integrations" });
  }
  if (features.assets) {
    enterpriseItems.push({ to: "/ui/assets", icon: "monitor", label: "Assets" });
  }

  if (enterpriseItems.length > 0) {
    items.push({ section: "Enterprise", items: enterpriseItems });
  }

  items.push({ section: "System", items: [
    { to: "/ui/audit-logs", icon: "document", label: "Audit Logs" },
    { to: "/ui/settings", icon: "settings", label: "Settings" },
  ]});

  return items;
};

export default function Sidebar({ isOpen, onClose }) {
  const { features } = useFeatures();
  const navItems = getNavItems(features, getCurrentRole());

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
                  <span className="sidebar-link-icon">
                    <AppIcon name={item.icon} />
                  </span>
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
