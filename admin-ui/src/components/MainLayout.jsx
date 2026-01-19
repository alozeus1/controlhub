import Sidebar from "./Sidebar";
import TopNav from "./TopNav";
import { Outlet } from "react-router-dom";
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
          <span>&copy; {currentYear} Web Forx. All rights reserved.</span>
          <div className="main-footer-links">
            <a href="#">Documentation</a>
            <a href="#">Support</a>
            <a href="#">Privacy</a>
          </div>
        </footer>
      </main>
    </div>
  );
}
