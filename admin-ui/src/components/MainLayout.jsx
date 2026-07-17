import { useState } from "react";
import Sidebar from "./Sidebar";
import TopNav from "./TopNav";
import { Outlet, Link, useLocation } from "react-router-dom";
import AIManagerAssistant from "./AIManagerAssistant";
import ErrorBoundary from "./ErrorBoundary";
import "./MainLayout.css";

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const currentYear = new Date().getFullYear();
  const location = useLocation();

  return (
    <div className="main-layout">
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <TopNav onMenuToggle={() => setSidebarOpen((prev) => !prev)} />

      <main className="main-content">
        <div className="main-content-inner page-transition" key={location.pathname}>
          <ErrorBoundary resetKey={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </div>

        <footer className="main-footer">
          <span>
            &copy; {currentYear}{" "}
            <a
              href="https://www.webforxtech.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="footer-brand-link"
            >
              Web Forx Global Inc.
            </a>
            {" "}Web Forx™. All rights reserved.
          </span>
          <div className="main-footer-links">
            <a href="https://www.webforxtech.com/" target="_blank" rel="noopener noreferrer">Web Forx</a>
            <Link to="/ui/support">Support</Link>
            <Link to="/ui/privacy">Privacy</Link>
          </div>
        </footer>
      </main>
      
      {/* Global AI Management Assistant */}
      <AIManagerAssistant />
    </div>
  );
}
