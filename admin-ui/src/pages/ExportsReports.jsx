import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./ExportsReports.css";

const INITIAL_FORM = {
  module_scope: "people",
  template_id: "",
  output_type: "csv",
  destination_type: "download",
  destination_ref: "",
  search: "",
  team: "",
  department: "",
  cohort: "",
  employment_type: "",
  intern_track: "",
  status: "",
  limit: "",
};

function buildFilters(formData) {
  const filters = {};
  [
    "search",
    "team",
    "department",
    "cohort",
    "employment_type",
    "intern_track",
    "status",
  ].forEach((field) => {
    if (formData[field]) filters[field] = formData[field];
  });
  if (formData.limit) {
    const parsed = Number(formData.limit);
    if (!Number.isNaN(parsed) && parsed > 0) {
      filters.limit = parsed;
    }
  }
  return filters;
}

function triggerBlobDownload(blob, filename) {
  const blobUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(blobUrl);
}

export default function ExportsReports() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [runningId, setRunningId] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [destinations, setDestinations] = useState([]);
  const [requests, setRequests] = useState([]);
  const [statusMeta, setStatusMeta] = useState({ permissions: {}, presign_ttl_bounds: {} });
  const [formData, setFormData] = useState(INITIAL_FORM);

  const templateOptions = useMemo(
    () => templates.filter((template) => template.module_scope === formData.module_scope),
    [templates, formData.module_scope]
  );

  const destinationOptions = useMemo(
    () => destinations.filter((d) => d.destination_type === formData.destination_type),
    [destinations, formData.destination_type]
  );

  const loadData = useCallback(async () => {
    const [templatesRes, requestsRes, statusRes, destinationsRes] = await Promise.all([
      api.get("/admin/agent/templates"),
      api.get("/admin/agent-requests?page=1&page_size=15"),
      api.get("/admin/agent/status"),
      api.get("/admin/external-destinations"),
    ]);

    const templateItems = templatesRes.data.items || [];
    setTemplates(templateItems);
    setRequests(requestsRes.data.items || []);
    setStatusMeta(statusRes.data || { permissions: {}, presign_ttl_bounds: {} });
    setDestinations(destinationsRes.data.items || []);

    if (!formData.template_id && templateItems.length > 0) {
      const first = templateItems.find((template) => template.module_scope === formData.module_scope) || templateItems[0];
      setFormData((prev) => ({ ...prev, template_id: first.id }));
    }
  }, [formData.module_scope, formData.template_id]);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await loadData();
      } catch (err) {
        if (err.response?.data?.code === "FEATURE_DISABLED") {
          toast.error("Agent Service is disabled");
          return;
        }
        toast.error(err.response?.data?.error || err.message || "Failed to load exports page");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadData, toast]);

  const submitRequest = async () => {
    try {
      setSubmitting(true);
      const payload = {
        module_scope: formData.module_scope,
        template_id: formData.template_id,
        output_type: formData.output_type,
        destination_type: formData.destination_type,
        destination_ref: formData.destination_type === "download" ? null : formData.destination_ref,
        filters_json: buildFilters(formData),
      };

      const response = await api.post("/admin/agent-requests", payload);
      const code = response.data?.code;
      if (code === "APPROVAL_REQUIRED") {
        toast.success(`Approval required (request #${response.data.approval_request?.id})`);
      } else {
        toast.success("Export request completed");
      }
      await loadData();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to submit agent request");
    } finally {
      setSubmitting(false);
    }
  };

  const runRequest = async (item) => {
    const requestId = typeof item === "object" ? item.id : item;
    // Proactively block running a request that's still awaiting approval.
    if (typeof item === "object" && item.status === "pending_approval") {
      toast.error("Approval required before this can run.");
      return;
    }
    try {
      setRunningId(requestId);
      await api.post(`/admin/agent-requests/${requestId}/run`, {});
      toast.success("Agent request executed");
      await loadData();
    } catch (err) {
      // Backend returns a clear APPROVAL_REQUIRED message; surface it verbatim.
      toast.error(err.response?.data?.error || err.message || "Failed to run request");
    } finally {
      setRunningId(null);
    }
  };

  const downloadArtifact = async (artifact) => {
    try {
      const ttlDefault = statusMeta?.presign_ttl_bounds?.default_minutes || 10;
      const presign = await api.post(`/admin/generated-artifacts/${artifact.id}/presign`, {
        ttl_minutes: ttlDefault,
      });
      if (presign.data?.code === "APPROVAL_REQUIRED") {
        toast.success(`Approval required (request #${presign.data.approval_request?.id})`);
        return;
      }

      const downloadUrl = presign.data?.download_url;
      if (!downloadUrl) {
        throw new Error("Missing download URL");
      }

      if (downloadUrl.startsWith("http://") || downloadUrl.startsWith("https://")) {
        window.open(downloadUrl, "_blank", "noopener,noreferrer");
        toast.success("Download link opened");
        return;
      }

      const response = await api.get(downloadUrl, { responseType: "blob" });
      const disposition = response.headers["content-disposition"] || "";
      const filenameMatch = disposition.match(/filename=([^;]+)/i);
      const filename = (filenameMatch?.[1] || artifact.filename || "artifact.bin").replace(/"/g, "");
      triggerBlobDownload(response.data, filename);
      toast.success("Download started");
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to download artifact");
    }
  };

  if (loading) {
    return <PageLoader message="Loading exports and reports..." />;
  }

  return (
    <div className="exports-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Exports & Reports</h1>
          <p className="page-subtitle">Governed agent requests with approvals, audit trail, and expiring downloads</p>
        </div>
        <div className="page-header-actions">
          <Link to="/ui/agent-requests" className="export-history-link">View Agent History</Link>
        </div>
      </div>

      <Card>
        <CardHeader title="Request Export" subtitle="Template and destination controls are policy-governed" />
        <CardBody>
          <div className="export-form-grid">
            <Select
              label="Module"
              value={formData.module_scope}
              onChange={(e) => setFormData((prev) => ({ ...prev, module_scope: e.target.value, template_id: "" }))}
            >
              <option value="people">People</option>
              <option value="assets">Assets</option>
              <option value="deployments">Deployments</option>
            </Select>

            <Select
              label="Template"
              value={formData.template_id}
              onChange={(e) => setFormData((prev) => ({ ...prev, template_id: e.target.value }))}
            >
              <option value="">Select template...</option>
              {templateOptions.map((template) => (
                <option key={template.id} value={template.id}>{template.name}</option>
              ))}
            </Select>

            <Select
              label="Output"
              value={formData.output_type}
              onChange={(e) => setFormData((prev) => ({ ...prev, output_type: e.target.value }))}
            >
              <option value="csv">CSV</option>
              <option value="xlsx">XLSX</option>
              <option value="docx">DOCX</option>
              <option value="md">Markdown</option>
            </Select>

            <Select
              label="Destination Type"
              value={formData.destination_type}
              onChange={(e) => setFormData((prev) => ({ ...prev, destination_type: e.target.value, destination_ref: "" }))}
            >
              <option value="download">S3 Download</option>
              {statusMeta.permissions?.["agent:write_external"] && <option value="google_drive_folder">Google Drive Folder</option>}
              {statusMeta.permissions?.["agent:write_external"] && <option value="google_sheet_range">Google Sheet Range</option>}
            </Select>

            {formData.destination_type !== "download" && (
              <Select
                label="Destination"
                value={formData.destination_ref}
                onChange={(e) => setFormData((prev) => ({ ...prev, destination_ref: e.target.value }))}
              >
                <option value="">Select allow-listed destination...</option>
                {destinationOptions.map((dest) => (
                  <option key={dest.id} value={String(dest.id)}>{dest.name}</option>
                ))}
              </Select>
            )}

            <Input label="Search" placeholder="Name or email" value={formData.search} onChange={(e) => setFormData((prev) => ({ ...prev, search: e.target.value }))} />
            <Input label="Team" value={formData.team} onChange={(e) => setFormData((prev) => ({ ...prev, team: e.target.value }))} />
            <Input label="Department" value={formData.department} onChange={(e) => setFormData((prev) => ({ ...prev, department: e.target.value }))} />
            <Input label="Cohort" value={formData.cohort} onChange={(e) => setFormData((prev) => ({ ...prev, cohort: e.target.value }))} />
            <Input label="Employment Type" value={formData.employment_type} onChange={(e) => setFormData((prev) => ({ ...prev, employment_type: e.target.value }))} />
            <Input label="Intern Track" value={formData.intern_track} onChange={(e) => setFormData((prev) => ({ ...prev, intern_track: e.target.value }))} />
            <Input label="Status" value={formData.status} onChange={(e) => setFormData((prev) => ({ ...prev, status: e.target.value }))} />
            <Input label="Row Limit" type="number" value={formData.limit} onChange={(e) => setFormData((prev) => ({ ...prev, limit: e.target.value }))} />
          </div>

          <div className="exports-actions-row">
            <Button variant="primary" loading={submitting} onClick={submitRequest}>Submit Agent Request</Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Recent Requests" subtitle="Run pending jobs and download generated artifacts" />
        <CardBody>
          {requests.length === 0 ? (
            <div className="empty-state"><p>No agent requests yet.</p></div>
          ) : (
            <table className="exports-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Scope</th>
                  <th>Template</th>
                  <th>Output</th>
                  <th>Destination</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((item) => (
                  <tr key={item.id}>
                    <td>#{item.id}</td>
                    <td>{item.module_scope}</td>
                    <td>{item.template_id}</td>
                    <td>{item.output_type}</td>
                    <td>{item.destination_type}{item.destination_ref ? ` (${item.destination_ref})` : ""}</td>
                    <td>
                      <span className={`status-badge status-${item.status}`}>{item.status}</span>
                    </td>
                    <td>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</td>
                    <td>
                      <div className="table-actions">
                        <Button variant="secondary" size="sm" loading={runningId === item.id}
                                title={item.status === "pending_approval" ? "Approval required before this can run" : undefined}
                                onClick={() => runRequest(item)}>Run</Button>
                        {item.latest_artifact && (
                          <Button variant="secondary" size="sm" onClick={() => downloadArtifact(item.latest_artifact)}>Download</Button>
                        )}
                        <Link className="history-link" to={`/ui/agent-requests?request_id=${item.id}`}>History</Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
