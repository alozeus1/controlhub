import { useEffect, useState, useCallback } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./AuditExport.css";

const FORMAT_OPTIONS = [
  { value: "csv", label: "CSV", desc: "Spreadsheet compatible" },
  { value: "json", label: "JSON", desc: "Structured data" },
  { value: "jsonl", label: "JSON Lines", desc: "Streaming friendly" },
];

export default function AuditExport() {
  const navigate = useNavigate();
  const toast = useToast();

  const [exports, setExports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showQuickExport, setShowQuickExport] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [runningId, setRunningId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    format: "csv",
    destination_type: "download",
    filters: {
      start_date: "",
      end_date: "",
    },
  });
  const [quickExportData, setQuickExportData] = useState({
    format: "csv",
    filters: {
      start_date: "",
      end_date: "",
    },
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get("/admin/audit-exports");
      setExports(res.data.items || []);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Integrations feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load audit exports");
    } finally {
      setLoading(false);
    }
  }, [toast, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const resetForm = () => {
    setFormData({
      name: "",
      format: "csv",
      destination_type: "download",
      filters: { start_date: "", end_date: "" },
    });
  };

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      toast.error("Export name is required");
      return;
    }

    try {
      setSaving(true);
      const payload = {
        name: formData.name,
        format: formData.format,
        destination_type: formData.destination_type,
        filters: {},
      };
      if (formData.filters.start_date) {
        payload.filters.start_date = formData.filters.start_date;
      }
      if (formData.filters.end_date) {
        payload.filters.end_date = formData.filters.end_date;
      }

      await api.post("/admin/audit-exports", payload);
      toast.success("Export job created");
      setShowCreateModal(false);
      resetForm();
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to create export");
    } finally {
      setSaving(false);
    }
  };

  const handleRunExport = async (job) => {
    try {
      setRunningId(job.id);
      const response = await api.post(`/admin/audit-exports/${job.id}/run`, null, {
        responseType: "blob",
      });

      // Get filename from header or generate one
      const contentDisposition = response.headers["content-disposition"];
      let filename = `audit_export.${job.export_format}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/);
        if (match) filename = match[1];
      }

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      toast.success("Export downloaded");
      fetchData(); // Refresh to show updated last_run_at
    } catch (err) {
      toast.error(err.message || "Export failed");
    } finally {
      setRunningId(null);
    }
  };

  const handleQuickExport = async () => {
    try {
      setSaving(true);
      const payload = {
        format: quickExportData.format,
        filters: {},
      };
      if (quickExportData.filters.start_date) {
        payload.filters.start_date = quickExportData.filters.start_date;
      }
      if (quickExportData.filters.end_date) {
        payload.filters.end_date = quickExportData.filters.end_date;
      }

      const response = await api.post("/admin/audit-exports/now", payload, {
        responseType: "blob",
      });

      const contentDisposition = response.headers["content-disposition"];
      let filename = `audit_export.${quickExportData.format}`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/);
        if (match) filename = match[1];
      }

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      toast.success("Export downloaded");
      setShowQuickExport(false);
    } catch (err) {
      toast.error(err.message || "Export failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;

    try {
      setSaving(true);
      await api.delete(`/admin/audit-exports/${deleteConfirm.id}`);
      toast.success("Export job deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to delete export");
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  if (loading) {
    return <PageLoader message="Loading audit exports..." />;
  }

  return (
    <div className="audit-export-page">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            <Link to="/ui/integrations">Integrations</Link>
            <span>/</span>
            <span>Audit Export</span>
          </div>
          <h1 className="page-title">Audit Log Export</h1>
          <p className="page-subtitle">Export audit logs for compliance and analysis</p>
        </div>
        <div className="header-actions">
          <Button variant="secondary" onClick={() => setShowQuickExport(true)}>
            Quick Export
          </Button>
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>
            + Create Export Job
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader title="Export Jobs" />
        <CardBody>
          {exports.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📦</div>
              <p className="empty-state-title">No export jobs</p>
              <p className="empty-state-text">Create saved export configurations or use Quick Export</p>
              <div className="empty-state-actions">
                <Button variant="secondary" onClick={() => setShowQuickExport(true)}>
                  Quick Export
                </Button>
                <Button variant="primary" onClick={() => setShowCreateModal(true)}>
                  Create Export Job
                </Button>
              </div>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Format</th>
                  <th>Last Run</th>
                  <th>Records</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {exports.map((job) => (
                  <tr key={job.id}>
                    <td className="job-name">{job.name}</td>
                    <td>
                      <Badge variant="default">{job.export_format.toUpperCase()}</Badge>
                    </td>
                    <td className="timestamp">{formatDate(job.last_run_at)}</td>
                    <td>{job.last_run_records ?? "-"}</td>
                    <td>
                      {job.last_run_status ? (
                        <Badge variant={job.last_run_status === "success" ? "success" : "error"}>
                          {job.last_run_status}
                        </Badge>
                      ) : (
                        <Badge variant="default">Never run</Badge>
                      )}
                    </td>
                    <td>
                      <div className="action-buttons">
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => handleRunExport(job)}
                          loading={runningId === job.id}
                        >
                          Run & Download
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="danger"
                          onClick={() => setDeleteConfirm(job)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
        title="Create Export Job"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Export Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="e.g., Monthly Compliance Export"
          />
          <Select
            label="Export Format"
            value={formData.format}
            onChange={(e) => setFormData({ ...formData, format: e.target.value })}
          >
            {FORMAT_OPTIONS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label} - {f.desc}
              </option>
            ))}
          </Select>
          <div className="date-range">
            <Input
              label="Start Date (optional)"
              type="date"
              value={formData.filters.start_date}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  filters: { ...formData.filters, start_date: e.target.value },
                })
              }
            />
            <Input
              label="End Date (optional)"
              type="date"
              value={formData.filters.end_date}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  filters: { ...formData.filters, end_date: e.target.value },
                })
              }
            />
          </div>
          <p className="help-text">Leave dates empty to export last 30 days</p>
        </div>
      </Modal>

      {/* Quick Export Modal */}
      <Modal
        isOpen={showQuickExport}
        onClose={() => setShowQuickExport(false)}
        title="Quick Export"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowQuickExport(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleQuickExport} loading={saving}>Download</Button>
          </>
        }
      >
        <div className="form-stack">
          <Select
            label="Export Format"
            value={quickExportData.format}
            onChange={(e) => setQuickExportData({ ...quickExportData, format: e.target.value })}
          >
            {FORMAT_OPTIONS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label} - {f.desc}
              </option>
            ))}
          </Select>
          <div className="date-range">
            <Input
              label="Start Date (optional)"
              type="date"
              value={quickExportData.filters.start_date}
              onChange={(e) =>
                setQuickExportData({
                  ...quickExportData,
                  filters: { ...quickExportData.filters, start_date: e.target.value },
                })
              }
            />
            <Input
              label="End Date (optional)"
              type="date"
              value={quickExportData.filters.end_date}
              onChange={(e) =>
                setQuickExportData({
                  ...quickExportData,
                  filters: { ...quickExportData.filters, end_date: e.target.value },
                })
              }
            />
          </div>
          <p className="help-text">Leave dates empty to export last 30 days</p>
        </div>
      </Modal>

      {/* Delete Confirm */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDelete}
        title="Delete Export Job"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"?`}
        confirmText="Delete"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
