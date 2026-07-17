import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import AppIcon from "./ui/AppIcon";
import api from "../utils/api";
import "./GlobalSearch.css";

export default function GlobalSearch() {
  const [q, setQ] = useState("");
  const [groups, setGroups] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef(null);
  const navigate = useNavigate();

  const run = useCallback(async (term) => {
    if (term.trim().length < 2) { setGroups([]); return; }
    try {
      setLoading(true);
      const res = await api.get(`/admin/search?q=${encodeURIComponent(term.trim())}`);
      setGroups(res.data.groups || []);
    } catch { setGroups([]); }
    finally { setLoading(false); }
  }, []);

  // Debounce.
  useEffect(() => {
    const t = setTimeout(() => run(q), 220);
    return () => clearTimeout(t);
  }, [q, run]);

  // Close on outside click / Escape.
  useEffect(() => {
    const onClick = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onClick); document.removeEventListener("keydown", onKey); };
  }, []);

  const go = (link) => { setOpen(false); setQ(""); setGroups([]); navigate(link); };
  const hasResults = groups.some((g) => g.items.length);

  return (
    <div className="global-search" ref={boxRef}>
      <div className="global-search-input">
        <AppIcon name="dashboard" size={15} className="global-search-icon" />
        <input
          type="text"
          placeholder="Search users, assets, secrets…"
          value={q}
          onFocus={() => setOpen(true)}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          aria-label="Global search"
        />
      </div>

      {open && q.trim().length >= 2 && (
        <div className="global-search-results">
          {loading && <div className="global-search-empty">Searching…</div>}
          {!loading && !hasResults && <div className="global-search-empty">No results for “{q}”.</div>}
          {!loading && groups.map((g) => (
            g.items.length > 0 && (
              <div className="global-search-group" key={g.category}>
                <div className="global-search-group-title">
                  <AppIcon name={g.icon || "document"} size={13} /> {g.category}
                </div>
                {g.items.map((it, i) => (
                  <button className="global-search-item" key={`${g.category}-${i}`} onClick={() => go(it.link)}>
                    <span className="global-search-item-label">{it.label}</span>
                    {it.sublabel && <span className="global-search-item-sub">{it.sublabel}</span>}
                  </button>
                ))}
              </div>
            )
          ))}
        </div>
      )}
    </div>
  );
}
