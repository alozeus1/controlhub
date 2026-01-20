import { useEffect, useState, useRef, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Pagination from "../components/ui/Pagination";
import { PageLoader } from "../components/ui/Spinner";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import "./Uploads.css";

const normalizeArray = (response) => {
  if (!response) return [];
  if (Array.isArray(response)) return response;
  if (response.data?.items) return response.data.items;
  if (response.items) return response.items;
  if (Array.isArray(response.data)) return response.data;
  return [];
};

const formatBytes = (bytes) => {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (dateStr) => {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleString();
};

export default function Uploads() {
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [search, setSearch] = useState("");
  const [uploading, setUploading] = useState(false);
  const [deleteModal, setDeleteModal] = useState({ open: false, upload: null });
  const [deleting, setDeleting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);
  const toast = useToast();

  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const isAdmin = user.role === "admin" || user.role === "superadmin";

  const fetchUploads = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      let url = `/admin/uploads?page=${page}&page_size=20`;
      if (search) {
        url += `&search=${encodeURIComponent(search)}`;
      }
      const res = await api.get(url);
      const items = normalizeArray(res);
      setUploads(items);
      setPagination({
        page: res.data?.page || 1,
        pages: res.data?.pages || 1,
        total: res.data?.total || items.length,
        page_size: res.data?.page_size || 20,
      });
    } catch (err) {
      console.error("Failed to load uploads:", err);
      toast.error("Failed to load uploads");
      setUploads([]);
    } finally {
      setLoading(false);
    }
  }, [search, toast]);

  useEffect(() => {
    fetchUploads(1);
  }, [fetchUploads]);

  const handleFileSelect = async (files) => {
    if (!files || files.length === 0) return;
    
    const file = files[0];
    const maxSize = 50 * 1024 * 1024; // 50MB
    
    if (file.size > maxSize) {
      toast.error(`File too large. Maximum size is 50MB.`);
      return;
    }
    
    try {
      setUploading(true);
      const res = await api.upload("/admin/uploads", file);
      toast.success(`Uploaded ${file.name} successfully`);
      fetchUploads(1);
    } catch (err) {
      console.error("Upload failed:", err);
      toast.error(err.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files);
    }
  };

  const handleDownload = async (upload) => {
    try {
      const res = await api.get(`/admin/uploads/${upload.id}/download`);
      if (res.data?.download_url) {
        // Replace internal Docker hostname with localhost for browser access
        let url = res.data.download_url;
        url = url.replace("http://localstack:4566", "http://localhost:4566");
        window.open(url, "_blank");
        toast.success(`Downloading ${upload.original_filename}`);
      }
    } catch (err) {
      console.error("Download failed:", err);
      toast.error("Failed to get download link");
    }
  };

  const handleDelete = async () => {
    if (!deleteModal.upload) return;
    
    try {
      setDeleting(true);
      await api.delete(`/admin/uploads/${deleteModal.upload.id}`);
      toast.success(`Deleted ${deleteModal.upload.original_filename}`);
      setDeleteModal({ open: false, upload: null });
      fetchUploads(pagination.page);
    } catch (err) {
      console.error("Delete failed:", err);
      toast.error(err.message || "Failed to delete file");
    } finally {
      setDeleting(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    fetchUploads(1);
  };

  return (
    <div className="uploads-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">File Uploads</h1>
          <p className="page-subtitle">Upload, download, and manage files stored in S3</p>
        </div>
      </div>

      {isAdmin && (
        <Card className="upload-card">
          <CardBody>
            <div
              className={`upload-zone ${dragActive ? "drag-active" : ""} ${uploading ? "uploading" : ""}`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => !uploading && fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                className="upload-input"
                onChange={(e) => handleFileSelect(e.target.files)}
                disabled={uploading}
              />
              {uploading ? (
                <div className="upload-zone-content">
                  <div className="upload-spinner"></div>
                  <p>Uploading...</p>
                </div>
              ) : (
                <div className="upload-zone-content">
                  <div className="upload-icon">📁</div>
                  <p className="upload-text">
                    <strong>Click to upload</strong> or drag and drop
                  </p>
                  <p className="upload-hint">Maximum file size: 50MB</p>
                </div>
              )}
            </div>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader 
          title={`${pagination.total} Uploads`}
          action={
            <form onSubmit={handleSearch} className="search-form">
              <Input
                placeholder="Search by filename..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="search-input"
              />
              <Button type="submit" variant="secondary" size="sm">
                Search
              </Button>
            </form>
          }
        />
        <CardBody>
          {loading ? (
            <PageLoader message="Loading uploads..." />
          ) : uploads.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📂</div>
              <p className="empty-state-text">No uploads found</p>
              {search && (
                <Button variant="ghost" onClick={() => { setSearch(""); fetchUploads(1); }}>
                  Clear search
                </Button>
              )}
            </div>
          ) : (
            <>
              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Filename</th>
                      <th>Type</th>
                      <th>Size</th>
                      <th>Uploader</th>
                      <th>Created</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {uploads.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <div className="filename-cell">
                            <span className="filename">{u.original_filename || u.filename}</span>
                          </div>
                        </td>
                        <td>
                          <span className="content-type">{u.content_type || "-"}</span>
                        </td>
                        <td>{formatBytes(u.size_bytes)}</td>
                        <td>
                          <span className="uploader">{u.uploader_email || `User #${u.user_id}`}</span>
                        </td>
                        <td className="text-muted">{formatDate(u.created_at)}</td>
                        <td>
                          <div className="action-buttons">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDownload(u)}
                            >
                              ⬇️ Download
                            </Button>
                            {isAdmin && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="danger"
                                onClick={() => setDeleteModal({ open: true, upload: u })}
                              >
                                🗑️ Delete
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchUploads}
              />
            </>
          )}
        </CardBody>
      </Card>

      <ConfirmModal
        isOpen={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, upload: null })}
        onConfirm={handleDelete}
        title="Delete Upload"
        message={`Are you sure you want to delete "${deleteModal.upload?.original_filename}"? This action cannot be undone.`}
        confirmText={deleting ? "Deleting..." : "Delete"}
        confirmVariant="danger"
        loading={deleting}
      />
    </div>
  );
}
