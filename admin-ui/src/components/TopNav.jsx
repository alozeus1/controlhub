import { useState, useEffect, useRef } from "react";
import { useLocation, Link } from "react-router-dom";
import logoIcon from "../assets/brand/logo-icon.svg";
import "./TopNav.css";

const pageNames = {
  dashboard: "Dashboard",
  users: "Users",
  uploads: "Uploads",
  jobs: "Jobs",
  "audit-logs": "Audit Logs",
  settings: "Settings",
  privacy: "Privacy Policy",
  support: "Support",
};

export default function TopNav({ onMenuToggle }) {
  const { pathname } = useLocation();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [user, setUser] = useState(null);
  const dropdownRef = useRef(null);

  const pageName = pathname.replace("/ui/", "");
  const pageTitle = pageNames[pageName] || pageName;

  useEffect(() => {
    const storedUser =
      sessionStorage.getItem("user") || localStorage.getItem("user");
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {}
    }
  }, []);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const initials = user?.email
    ? user.email.split("@")[0].slice(0, 2).toUpperCase()
    : "??";

  const env = process.env.NODE_ENV || "development";
  const envLabel = env === "production" ? "PROD" : env === "staging" ? "STAGING" : "DEV";
  const envClass = env === "production" ? "prod" : env === "staging" ? "staging" : "dev";

  return (
    <header className="topnav">
      <div className="topnav-left">
        {/* Hamburger — mobile only */}
        <button
          className="topnav-hamburger"
          onClick={onMenuToggle}
          aria-label="Open navigation menu"
        >
          <span className="hamburger-line" />
          <span className="hamburger-line" />
          <span className="hamburger-line" />
        </button>

        <Link to="/ui/dashboard" className="topnav-brand">
          <img src={logoIcon} alt="Web Forx" className="topnav-brand-logo" />
          <span className="topnav-brand-text">Web Forx <span>ControlHub</span></span>
        </Link>

        <nav className="topnav-breadcrumbs">
          <Link to="/ui/dashboard" className="topnav-breadcrumb-link">Home</Link>
          <span className="topnav-breadcrumb-separator">/</span>
          <span className="topnav-breadcrumb-current">{pageTitle}</span>
        </nav>
      </div>

      <div className="topnav-right">
        <span className={`topnav-env-badge ${envClass}`}>{envLabel}</span>

        <div
          ref={dropdownRef}
          className={`topnav-dropdown ${dropdownOpen ? "open" : ""}`}
        >
          <div
            className="topnav-user"
            onClick={() => setDropdownOpen(!dropdownOpen)}
          >
            <div className="topnav-user-avatar">{initials}</div>
            <div className="topnav-user-info">
              <span className="topnav-user-name">
                {user?.email?.split("@")[0] || "User"}
              </span>
              <span className="topnav-user-role">{user?.role || "user"}</span>
            </div>
          </div>

          <div className="topnav-dropdown-menu">
            <Link to="/ui/settings" className="topnav-dropdown-item">
              ⚙️ Settings
            </Link>
            <div className="topnav-dropdown-divider" />
            <Link to="/ui/logout" className="topnav-dropdown-item danger">
              🚪 Logout
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
