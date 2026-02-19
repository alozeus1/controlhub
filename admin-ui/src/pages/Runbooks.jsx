import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../utils/api";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Runbooks.css";

export default function Runbooks() {
  const navigate = useNavigate();
  const toast = useToast();

  const [runbooks, setRunbooks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (activeCategory) params.append("category", activeCategory);
      if (searchQuery) params.append("q", searchQuery);

      const [runbooksRes, categoriesRes] = await Promise.all([
        api.get(`/admin/runbooks?${params}`),
        api.get("/admin/runbooks/categories"),
      ]);
      setRunbooks(runbooksRes.data.items || runbooksRes.data || []);
      setCategories(categoriesRes.data.items || categoriesRes.data || []);
    } catch {
      toast.error("Failed to load runbooks");
    } finally {
      setLoading(false);
    }
  }, [activeCategory, searchQuery, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString();
  };

  const getPreview = (content) => {
    if (!content) return "";
    return content.substring(0, 150) + (content.length > 150 ? "..." : "");
  };

  if (loading && runbooks.length === 0) {
    return <PageLoader message="Loading runbooks..." />;
  }

  return (
    <div className="runbooks-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Runbooks</h1>
          <p className="page-subtitle">Operational runbooks and documentation</p>
        </div>
        <Button variant="primary" onClick={() => navigate("/ui/runbooks/new")}>
          + New Runbook
        </Button>
      </div>

      <div className="runbooks-layout">
        {/* Left Sidebar */}
        <div className="runbooks-sidebar">
          <Input
            placeholder="Search runbooks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <div className="category-list">
            <div
              className={`category-item ${activeCategory === "" ? "active" : ""}`}
              onClick={() => setActiveCategory("")}
            >
              <span>All</span>
              <span className="category-count">{runbooks.length}</span>
            </div>
            {categories.map((cat) => (
              <div
                key={cat.name || cat}
                className={`category-item ${activeCategory === (cat.name || cat) ? "active" : ""}`}
                onClick={() => setActiveCategory(cat.name || cat)}
              >
                <span>{cat.name || cat}</span>
                <span className="category-count">{cat.count ?? 0}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right Content */}
        <div className="runbooks-content">
          {runbooks.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📖</div>
              <p className="empty-state-title">No runbooks found</p>
              <p className="empty-state-text">Create your first runbook to get started</p>
              <Button variant="primary" onClick={() => navigate("/ui/runbooks/new")}>
                New Runbook
              </Button>
            </div>
          ) : (
            <div className="runbook-grid">
              {runbooks.map((runbook) => (
                <div
                  key={runbook.id}
                  className="runbook-card"
                  onClick={() => navigate(`/ui/runbooks/${runbook.id}`)}
                >
                  <div className="runbook-card-header">
                    <h3 className="runbook-card-title">{runbook.title}</h3>
                    {runbook.category && (
                      <Badge variant="default">{runbook.category}</Badge>
                    )}
                  </div>
                  <p className="runbook-card-preview">{getPreview(runbook.content)}</p>
                  <div className="runbook-card-footer">
                    <span className="runbook-card-date">
                      Updated {formatDate(runbook.updated_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
