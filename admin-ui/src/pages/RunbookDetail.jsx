import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import { TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./RunbookDetail.css";

export default function RunbookDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const isNew = id === "new";

  const [runbook, setRunbook] = useState(null);
  const [loading, setLoading] = useState(!isNew);
  const [editing, setEditing] = useState(isNew);
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editData, setEditData] = useState({
    title: "",
    category: "",
    tags: "",
    content: "",
  });

  const fetchRunbook = useCallback(async () => {
    if (isNew) return;
    try {
      setLoading(true);
      const res = await api.get(`/admin/runbooks/${id}`);
      setRunbook(res.data);
      setEditData({
        title: res.data.title || "",
        category: res.data.category || "",
        tags: (res.data.tags || []).join(", "),
        content: res.data.content || "",
      });
    } catch {
      toast.error("Failed to load runbook");
      navigate("/ui/runbooks");
    } finally {
      setLoading(false);
    }
  }, [id, isNew, toast, navigate]);

  useEffect(() => {
    fetchRunbook();
  }, [fetchRunbook]);

  const handleSave = async () => {
    if (!editData.title.trim() || !editData.content.trim()) {
      toast.error("Title and content are required");
      return;
    }
    try {
      setSaving(true);
      const payload = {
        title: editData.title,
        category: editData.category,
        tags: editData.tags
          ? editData.tags.split(",").map((t) => t.trim()).filter(Boolean)
          : [],
        content: editData.content,
      };

      if (isNew) {
        const res = await api.post("/admin/runbooks", payload);
        toast.success("Runbook created");
        navigate(`/ui/runbooks/${res.data.id}`);
      } else {
        await api.put(`/admin/runbooks/${id}`, payload);
        toast.success("Runbook updated");
        setEditing(false);
        fetchRunbook();
      }
    } catch (err) {
      toast.error(err.message || "Failed to save runbook");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      setSaving(true);
      await api.delete(`/admin/runbooks/${id}`);
      toast.success("Runbook deleted");
      navigate("/ui/runbooks");
    } catch (err) {
      toast.error(err.message || "Failed to delete runbook");
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const renderContent = (content) => {
    if (!content) return null;
    return (
      <pre className="runbook-content-rendered">{content}</pre>
    );
  };

  if (loading) {
    return <PageLoader message="Loading runbook..." />;
  }

  return (
    <div className="runbook-detail-page">
      <div className="page-header">
        <div>
          <button className="back-link" onClick={() => navigate("/ui/runbooks")}>
            &larr; Back to Runbooks
          </button>
          <h1 className="page-title">
            {isNew ? "New Runbook" : editing ? "Edit Runbook" : runbook?.title}
          </h1>
          {!isNew && !editing && runbook && (
            <div className="runbook-meta">
              {runbook.category && <Badge variant="default">{runbook.category}</Badge>}
              {runbook.tags?.map((tag) => (
                <span key={tag} className="meta-tag">{tag}</span>
              ))}
              <span className="meta-date">
                Last updated {formatDate(runbook.updated_at)} by {runbook.updated_by || "unknown"}
              </span>
            </div>
          )}
        </div>
        {!isNew && !editing && (
          <div className="page-header-actions">
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>
              Delete
            </Button>
          </div>
        )}
      </div>

      {editing ? (
        <Card>
          <CardBody>
            <div className="edit-form">
              <Input
                label="Title *"
                value={editData.title}
                onChange={(e) => setEditData({ ...editData, title: e.target.value })}
                placeholder="Runbook title"
              />
              <div className="form-row">
                <Input
                  label="Category"
                  value={editData.category}
                  onChange={(e) => setEditData({ ...editData, category: e.target.value })}
                  placeholder="e.g., Deployment, Monitoring"
                />
                <Input
                  label="Tags (comma-separated)"
                  value={editData.tags}
                  onChange={(e) => setEditData({ ...editData, tags: e.target.value })}
                  placeholder="e.g., kubernetes, aws, database"
                />
              </div>
              <TextArea
                label="Content *"
                value={editData.content}
                onChange={(e) => setEditData({ ...editData, content: e.target.value })}
                placeholder="Write your runbook content here (supports plain text / markdown)..."
                rows={20}
              />
              <div className="edit-actions">
                {!isNew && (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setEditing(false);
                      setEditData({
                        title: runbook.title || "",
                        category: runbook.category || "",
                        tags: (runbook.tags || []).join(", "),
                        content: runbook.content || "",
                      });
                    }}
                  >
                    Cancel
                  </Button>
                )}
                <Button variant="primary" onClick={handleSave} loading={saving}>
                  {isNew ? "Create" : "Save"}
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      ) : (
        runbook && (
          <Card>
            <CardBody>
              {renderContent(runbook.content)}
            </CardBody>
          </Card>
        )
      )}

      <ConfirmModal
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Delete Runbook"
        message={`Are you sure you want to delete "${runbook?.title}"? This action cannot be undone.`}
        confirmText="Delete"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
