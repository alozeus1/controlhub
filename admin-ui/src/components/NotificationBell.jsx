import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import api from "../utils/api";
import { formatDateTime } from "../utils/datetime";
import "./NotificationBell.css";

const POLL_INTERVAL_MS = 30000;

export default function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const ref = useRef(null);

  const fetchInbox = useCallback(async () => {
    try {
      const res = await api.get("/admin/notifications/inbox?page_size=20");
      setItems(res.data.items || []);
      setUnreadCount(res.data.unread_count || 0);
    } catch {
      // Silent — the bell is a convenience surface, not critical path.
    }
  }, []);

  useEffect(() => {
    fetchInbox();
    const interval = setInterval(fetchInbox, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchInbox]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleOpenItem = async (item) => {
    if (!item.is_read) {
      try {
        await api.post(`/admin/notifications/inbox/${item.id}/read`);
        setItems((prev) => prev.map((n) => (n.id === item.id ? { ...n, is_read: true } : n)));
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch {
        // ignore
      }
    }
    setOpen(false);
    if (item.link) navigate(item.link);
  };

  const handleDelete = async (e, item) => {
    e.stopPropagation();
    try {
      await api.delete(`/admin/notifications/inbox/${item.id}`);
      setItems((prev) => prev.filter((n) => n.id !== item.id));
      if (!item.is_read) setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      // ignore
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.post("/admin/notifications/inbox/read-all");
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // ignore
    }
  };

  return (
    <div ref={ref} className={`notif-bell ${open ? "open" : ""}`}>
      <button
        className="notif-bell-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
      >
        <Bell size={18} />
        {unreadCount > 0 && (
          <span className="notif-bell-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>
        )}
      </button>

      <div className="notif-bell-panel">
        <div className="notif-bell-header">
          <span>Notifications</span>
          {unreadCount > 0 && (
            <button className="notif-bell-mark-all" onClick={handleMarkAllRead}>
              Mark all read
            </button>
          )}
        </div>
        <div className="notif-bell-list">
          {items.length === 0 ? (
            <p className="notif-bell-empty">You're all caught up.</p>
          ) : (
            items.map((item) => (
              <div
                key={item.id}
                className={`notif-bell-item ${item.is_read ? "" : "unread"}`}
                onClick={() => handleOpenItem(item)}
              >
                <div className="notif-bell-item-body">
                  <div className="notif-bell-item-title">{item.title}</div>
                  {item.body && <div className="notif-bell-item-text">{item.body}</div>}
                  <div className="notif-bell-item-time">{formatDateTime(item.created_at)}</div>
                </div>
                <button
                  className="notif-bell-item-delete"
                  onClick={(e) => handleDelete(e, item)}
                  aria-label="Dismiss notification"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
