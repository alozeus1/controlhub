import Sidebar from "./Sidebar";
import TopNav from "./TopNav";
import { Outlet, Link } from "react-router-dom";
import "./MainLayout.css";

export default function MainLayout() {
  const currentYear = new Date().getFullYear();

  return (
    <div className="main-layout">
      <Sidebar />
      <TopNav />

      <main className="main-content">
        <div className="main-content-inner">
          <Outlet />
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
              Web Forx
            </a>
            . All rights reserved.
          </span>
          <div className="main-footer-links">
            <Link to="/ui/support">Support</Link>
            <Link to="/ui/privacy">Privacy</Link>
          </div>
        </footer>
      </main>
    </div>
  );
}
