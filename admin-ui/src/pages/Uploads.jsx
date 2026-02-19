import { useEffect, useState, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Pagination from "../components/ui/Pagination";
import Badge from "../components/ui/Badge";
import { PageLoader } from "../components/ui/Spinner";
import { ConfirmModal } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import Dropdown, { DropdownItem, DropdownDivider } from "../components/ui/Dropdown";
import Tooltip from "../components/ui/Tooltip";
import "./Uploads.css";

const ALLOWED_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "application/pdf",
  "text/plain",
  "text/csv",
  "application/json",
  "application/xml",
];

const ALLOWED_EXTENSIONS = "JPG, PNG, GIF, WebP, PDF, TXT, CSV, JSON, XML";

const FILE_TYPE_ICONS = {
  "image/jpeg": "🖼️",
  "image/png": "🖼️",
  "image/gif": "🖼️",
  "image/webp": "🖼️",
  "application/pdf": "📄",
  "text/plain": "📝",
  "text/csv": "📊",
  "application/json": "{ }",
  "application/xml": "📋",
};

const normalizeArray = (response) => {
  if (!response) return [];
  if (Array.isArray(response)) return response;
  if (response.data?.items) return response.data.items;
  if (response.items) return response.items;
  if (Array.isArray(response.data)) return response.data;
  return [];
};

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatTimeAgo = (dateStr) => {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    return `${mins} minute${mins > 1 ? "s" : ""} ago`;
  }
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    return `${hours} hour${hours > 1 ? "s" : ""} ago`;
  }
  if (seconds < 604800) {
    const days = Math.floor(seconds / 86400);
    return `${days} day${days > 1 ? "s" : ""} ago`;
  }
  if (seconds < 2592000) {
    const weeks = Math.floor(seconds / 604800);
    return `${weeks} week${weeks > 1 ? "s" : ""} ago`;
  }
  const months = Math.floor(seconds / 2592000);
  return `${months} month${months > 1 ? "s" : ""} ago`;
};

const formatFullDate = (dateStr) => {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleString();
};

const getFileIcon = (contentType) => {
  return FILE_TYPE_ICONS[contentType] || "📁";
};

export default function Uploads() {
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [search, setSearch] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [deleteModal, setDeleteModal] = useState({ open: false, upload: null });
  const [deleting, setDeleting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [storageStatus, setStorageStatus] = useState({ loading: true, error: false, data: null });
  const fileInputRef = useRef(null);
  const searchTimeoutRef = useRef(null);
  const toast = useToast();

  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const isAdmin = user.role === "admin" || user.role === "superadmin";
  const canDelete = isAdmin;

  const fetchStorageStatus = useCallback(async () => {
    try {
      const res = await api.get("/admin/storage/status");
      setStorageStatus({ loading: false, error: false, data: res.data });
    } catch (err) {
      console.error("Failed to load storage status:", err);
      setStorageStatus({ loading: false, error: true, data: null });
    }
  }, []);

  const fetchUploads = useCallback(async (page = 1, searchQuery = search) => {
    try {
      setLoading(true);
      let url = `/admin/uploads?page=${page}&page_size=${pagination.page_size}`;
      if (searchQuery) {
        url += `&search=${encodeURIComponent(searchQuery)}`;
      }
      const res = await api.get(url);
      const items = normalizeArray(res);
      setUploads(items);
      setPagination((prev) => ({
        ...prev,
        page: res.data?.page || 1,
        pages: res.data?.pages || 1,
        total: res.data?.total || items.length,
        page_size: res.data?.page_size || prev.page_size,
      }));
    } catch (err) {
      console.error("Failed to load uploads:", err);
      toast.error("Failed to load uploads");
      setUploads([]);
    } finally {
      setLoading(false);
    }
  }, [search, pagination.page_size, toast]);

  useEffect(() => {
    fetchUploads(1, search);
    fetchStorageStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFileSelect = async (files) => {
    if (!files || files.length === 0) return;

    const file = files[0];
    const maxSize = 50 * 1024 * 1024; // 50MB

    if (file.size > maxSize) {
      toast.error(`File too large. Maximum size is 50MB.`);
      return;
    }

    if (!ALLOWED_TYPES.includes(file.type)) {
      toast.error(`File type not allowed. Supported types: ${ALLOWED_EXTENSIONS}`);
      return;
    }

    try {
      setUploading(true);
      setUploadProgress(0);
      await api.upload("/admin/uploads", file, (percent) => {
        setUploadProgress(percent);
      });
      toast.success(`Uploaded "${file.name}" successfully`);
      fetchUploads(1, search);
      fetchStorageStatus();
    } catch (err) {
      console.error("Upload failed:", err);
      toast.error(err.message || "Upload failed");
    } finally {
      setUploading(false);
      setUploadProgress(0);
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
        let url = res.data.download_url;
        url = url.replace("http://localstack:4566", "http://localhost:4566");
        window.open(url, "_blank");
        toast.success(`Downloading "${upload.original_filename}"`);
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
      const res = await api.delete(`/admin/uploads/${deleteModal.upload.id}`);
      
      // Check if approval is required (202 status)
      if (res.data?.code === "APPROVAL_REQUIRED") {
        toast.info(
          <span>
            Approval required. <Link to="/ui/approvals" style={{ color: "inherit", textDecoration: "underline" }}>View request</Link>
          </span>,
          8000
        );
        setDeleteModal({ open: false, upload: null });
        return;
      }
      
      toast.success(`Deleted "${deleteModal.upload.original_filename}"`);
      setDeleteModal({ open: false, upload: null });
      fetchUploads(pagination.page, search);
    } catch (err) {
      // Also check error response for approval required
      if (err.response?.data?.code === "APPROVAL_REQUIRED") {
        toast.info(
          <span>
            Approval required. <Link to="/ui/approvals" style={{ color: "inherit", textDecoration: "underline" }}>View request</Link>
          </span>,
          8000
        );
        setDeleteModal({ open: false, upload: null });
        return;
      }
      console.error("Delete failed:", err);
      toast.error(err.message || "Failed to delete file");
    } finally {
      setDeleting(false);
    }
  };

  const handleSearchChange = (e) => {
    const value = e.target.value;
    setSearch(value);

    // Debounced search
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      fetchUploads(1, value);
    }, 400);
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === "Enter") {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
      fetchUploads(1, search);
    }
  };

  const handleClearSearch = () => {
    setSearch("");
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    fetchUploads(1, "");
  };

  const handlePageSizeChange = (e) => {
    const newSize = parseInt(e.target.value, 10);
    setPagination((prev) => ({ ...prev, page_size: newSize }));
    fetchUploads(1, search);
  };

  const renderStorageStatus = () => {
    if (storageStatus.loading) {
      return (
        <Card className="storage-status-card">
          <CardBody>
            <div className="storage-status loading">
              <span className="storage-status-text">Loading storage status...</span>
            </div>
          </CardBody>
        </Card>
      );
    }

    if (storageStatus.error) {
      return (
        <Card className="storage-status-card">
          <CardBody>
            <div className="storage-status error">
              <span className="storage-status-icon">⚠️</span>
              <span className="storage-status-text">Storage status unavailable</span>
            </div>
          </CardBody>
        </Card>
      );
    }

    const { provider, bucket, region, last_upload_at } = storageStatus.data;
    const providerVariant = provider === "aws" ? "success" : "info";

    return (
      <Card className="storage-status-card">
        <CardBody>
          <div className="storage-status">
            <div className="storage-status-item">
              <span className="storage-status-label">Provider</span>
              <Badge variant={providerVariant}>{provider?.toUpperCase()}</Badge>
            </div>
            <div className="storage-status-item">
              <span className="storage-status-label">Bucket</span>
              <code className="storage-bucket">{bucket}</code>
            </div>
            <div className="storage-status-item">
              <span className="storage-status-label">Region</span>
              <span className="storage-region">{region}</span>
            </div>
            <div className="storage-status-item">
              <span className="storage-status-label">Last Upload</span>
              {last_upload_at ? (
                <Tooltip content={formatFullDate(last_upload_at)} position="top">
                  <span className="storage-last-upload">{formatTimeAgo(last_upload_at)}</span>
                </Tooltip>
              ) : (
                <span className="storage-last-upload muted">No uploads yet</span>
              )}
            </div>
          </div>
        </CardBody>
      </Card>
    );
  };

  return (
    <div className="uploads-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">File Uploads</h1>
          <p className="page-subtitle">Upload, download, and manage files stored in S3</p>
        </div>
      </div>

      {renderStorageStatus()}

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
                accept={ALLOWED_TYPES.join(",")}
              />
              {uploading ? (
                <div className="upload-zone-content">
                  <div className="upload-progress-container">
                    <div className="upload-progress-bar">
                      <div
                        className="upload-progress-fill"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                    <span className="upload-progress-text">{uploadProgress}%</span>
                  </div>
                  <p className="upload-text">Uploading...</p>
                </div>
              ) : (
                <div className="upload-zone-content">
                  <div className="upload-icon">📁</div>
                  <p className="upload-text">
                    <strong>Click to upload</strong> or drag and drop
                  </p>
                  <p className="upload-hint">
                    Supported: {ALLOWED_EXTENSIONS}
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
          title={`${pagination.total} Upload${pagination.total !== 1 ? "s" : ""}`}
          action={
            <div className="search-form">
              <div className="search-input-wrapper">
                <Input
                  placeholder="Search by filename..."
                  value={search}
                  onChange={handleSearchChange}
                  onKeyDown={handleSearchKeyDown}
                  className="search-input"
                />
                {search && (
                  <button
                    type="button"
                    className="search-clear"
                    onClick={handleClearSearch}
                    aria-label="Clear search"
                  >
                    ✕
                  </button>
                )}
              </div>
            </div>
          }
        />
        <CardBody>
          {loading ? (
            <PageLoader message="Loading uploads..." />
          ) : uploads.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">{search ? "🔍" : "📂"}</div>
              <p className="empty-state-title">
                {search ? "No matching uploads" : "No uploads yet"}
              </p>
              <p className="empty-state-text">
                {search
                  ? `No files match "${search}"`
                  : "Upload files using the panel above"}
              </p>
              {search && (
                <Button variant="ghost" onClick={handleClearSearch}>
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
                      <th>Size</th>
                      <th>Uploader</th>
                      <th>Created</th>
                      <th className="actions-col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {uploads.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <div className="filename-cell">
                            <span className="file-type-icon">{getFileIcon(u.content_type)}</span>
                            <Tooltip content={u.original_filename || u.filename} position="top">
                              <span className="filename">{u.original_filename || u.filename}</span>
                            </Tooltip>
                            <span className="content-type-badge">{u.content_type?.split("/")[1] || "-"}</span>
                          </div>
                        </td>
                        <td className="size-cell">{formatBytes(u.size_bytes)}</td>
                        <td>
                          <span className="uploader">{u.uploader_email || `User #${u.user_id}`}</span>
                        </td>
                        <td>
                          <Tooltip content={formatFullDate(u.created_at)} position="top">
                            <span className="time-ago">{formatTimeAgo(u.created_at)}</span>
                          </Tooltip>
                        </td>
                        <td className="actions-col">
                          <Dropdown
                            trigger={
                              <Button variant="ghost" size="sm" className="actions-trigger">
                                ⋮
                              </Button>
                            }
                            align="right"
                          >
                            <DropdownItem icon="⬇️" onClick={() => handleDownload(u)}>
                              Download
                            </DropdownItem>
                            {canDelete && (
                              <>
                                <DropdownDivider />
                                <DropdownItem
                                  icon="🗑️"
                                  danger
                                  onClick={() => setDeleteModal({ open: true, upload: u })}
                                >
                                  Delete
                                </DropdownItem>
                              </>
                            )}
                          </Dropdown>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pagination-container">
                <div className="pagination-size">
                  <label htmlFor="page-size">Show</label>
                  <select
                    id="page-size"
                    value={pagination.page_size}
                    onChange={handlePageSizeChange}
                    className="page-size-select"
                  >
                    <option value="10">10</option>
                    <option value="20">20</option>
                    <option value="50">50</option>
                    <option value="100">100</option>
                  </select>
                  <span>per page</span>
                </div>
                <Pagination
                  page={pagination.page}
                  pages={pagination.pages}
                  total={pagination.total}
                  pageSize={pagination.page_size}
                  onPageChange={(page) => fetchUploads(page, search)}
                />
              </div>
            </>
          )}
        </CardBody>
      </Card>

      <ConfirmModal
        isOpen={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, upload: null })}
        onConfirm={handleDelete}
        title="Delete File"
        message={
          <span>
            Are you sure you want to delete{" "}
            <strong>"{deleteModal.upload?.original_filename}"</strong>?
            <br />
            <br />
            This action cannot be undone.
          </span>
        }
        confirmText={deleting ? "Deleting..." : "Delete File"}
        confirmVariant="danger"
        loading={deleting}
      />
    </div>
  );
}
