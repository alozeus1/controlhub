import Sidebar from "./Sidebar";
import TopNav from "./TopNav";
import { Outlet } from "react-router-dom";

export default function MainLayout() {
  return (
    <div>
      <Sidebar />
      <TopNav />

      <div style={{ marginLeft: 240, padding: 40, marginTop: 60 }}>
        <Outlet />
      </div>
    </div>
  );
}
