import { useLocation } from "react-router-dom";
import "./topnav.css";

export default function TopNav() {
  const { pathname } = useLocation();

  return (
    <div className="topnav">
      <div className="breadcrumbs">
        {pathname.replace("/ui/", "").toUpperCase()}
      </div>

      <div className="user-info">
        <span className="user-badge">Admin</span>
      </div>
    </div>
  );
}
