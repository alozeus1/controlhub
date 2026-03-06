import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./AgentRequests.css";

function useQuery() {
  return new URLSearchParams(useLocation().search);
}

export default function AgentRequests() {
  const toast = useToast();
  const query = useQuery();
  const requestIdParam = query.get("request_id");

  const [loading, setLoading] = useState(true);
  const [requests, setRequests] = useState([]);
  const [selectedId, setSelectedId] = useState(requestIdParam ? Number(requestIdParam) : null);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [auditTrail, setAuditTrail] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [searchText, setSearchText] = useState("");

  const filteredRequests = useMemo(() => {
    const search = searchText.trim().toLowerCase();
    return requests.filter((item) => {
      if (statusFilter && item.status !== statusFilter) return false;
      if (!search) return true;
      return [
        String(item.id),
        item.module_scope,
        item.template_id,
        item.requester_email,
      ]
        .join(" ")
        .toLowerCase()
        .includes(search);
    });
  }, [requests, searchText, statusFilter]);

  const loadRequests = useCallback(async () => {
    const res = await api.get("/admin/agent-requests?page=1&page_size=100");
    const items = res.data.items || [];
    setRequests(items);

    if (!selectedId && items.length > 0) {
      setSelectedId(items[0].id);
    }
  }, [selectedId]);

  const loadRequestDetails = useCallback(async (requestId) => {
    if (!requestId) {
      setSelectedRequest(null);
      setAuditTrail([]);
      return;
    }

    const [detailsRes, auditRes] = await Promise.all([
      api.get(`/admin/agent-requests/${requestId}`),
      api.get(`/admin/audit-logs?target_type=agent_request&target_id=${requestId}&page_size=20`),
    ]);
    setSelectedRequest(detailsRes.data);
    setAuditTrail(auditRes.data.items || []);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await loadRequests();
      } catch (err) {
        toast.error(err.response?.data?.error || err.message || "Failed to load agent requests");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadRequests, toast]);

  useEffect(() => {
    loadRequestDetails(selectedId).catch((err) => {
      toast.error(err.response?.data?.error || err.message || "Failed to load request details");
    });
  }, [loadRequestDetails, selectedId, toast]);

  const downloadArtifact = async (artifactId, filename) => {
    try {
      const presign = await api.post(`/admin/generated-artifacts/${artifactId}/presign`, { ttl_minutes: 10 });
      if (presign.data?.code === "APPROVAL_REQUIRED") {
        toast.success(`Approval required (request #${presign.data.approval_request?.id})`);
        return;
      }

      const url = presign.data?.download_url;
      if (!url) {
        throw new Error("Missing download URL");
      }

      if (url.startsWith("http://") || url.startsWith("https://")) {
        window.open(url, "_blank", "noopener,noreferrer");
        toast.success("Download link opened");
        return;
      }

      const response = await api.get(url, { responseType: "blob" });
      const disposition = response.headers["content-disposition"] || "";
      const filenameMatch = disposition.match(/filename=([^;]+)/i);
      const resolved = (filenameMatch?.[1] || filename || "artifact.bin").replace(/"/g, "");
      const blobUrl = window.URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = resolved;
      anchor.click();
      window.URL.revokeObjectURL(blobUrl);
      toast.success("Download started");
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to download artifact");
    }
  };

  if (loading) {
    return <PageLoader message="Loading agent request history..." />;
  }

  return (
    <div className="agent-requests-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Agent Requests</h1>
          <p className="page-subtitle">Execution history, approvals, artifacts, and audit events</p>
        </div>
      </div>

      <div className="agent-requests-grid">
        <Card>
          <CardHeader title="Requests" subtitle="Filter and inspect request history" />
          <CardBody>
            <div className="agent-request-filters">
              <Input
                placeholder="Search by id/scope/template/requester"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
              <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All Status</option>
                <option value="pending">pending</option>
                <option value="pending_approval">pending_approval</option>
                <option value="processing">processing</option>
                <option value="completed">completed</option>
                <option value="failed">failed</option>
              </Select>
            </div>

            <div className="agent-request-list">
              {filteredRequests.length === 0 ? (
                <p className="empty-text">No agent requests match the current filters.</p>
              ) : (
                filteredRequests.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`request-item ${selectedId === item.id ? "selected" : ""}`}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <div className="request-item-row">
                      <strong>#{item.id}</strong>
                      <span className={`status-badge status-${item.status}`}>{item.status}</span>
                    </div>
                    <p>{item.module_scope} · {item.template_id} · {item.output_type}</p>
                    <small>{item.requester_email || "-"}</small>
                  </button>
                ))
              )}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={selectedRequest ? `Request #${selectedRequest.request.id}` : "Request Details"} />
          <CardBody>
            {!selectedRequest ? (
              <p className="empty-text">Select a request to inspect details.</p>
            ) : (
              <div className="details-stack">
                <div className="details-grid">
                  <div>
                    <label>Scope</label>
                    <p>{selectedRequest.request.module_scope}</p>
                  </div>
                  <div>
                    <label>Template</label>
                    <p>{selectedRequest.request.template_id}</p>
                  </div>
                  <div>
                    <label>Output</label>
                    <p>{selectedRequest.request.output_type}</p>
                  </div>
                  <div>
                    <label>Destination</label>
                    <p>{selectedRequest.request.destination_type}{selectedRequest.request.destination_ref ? ` (${selectedRequest.request.destination_ref})` : ""}</p>
                  </div>
                  <div>
                    <label>Created</label>
                    <p>{selectedRequest.request.created_at ? new Date(selectedRequest.request.created_at).toLocaleString() : "-"}</p>
                  </div>
                  <div>
                    <label>Completed</label>
                    <p>{selectedRequest.request.completed_at ? new Date(selectedRequest.request.completed_at).toLocaleString() : "-"}</p>
                  </div>
                </div>

                <div>
                  <h3 className="section-title">Filters</h3>
                  <pre className="details-json">{JSON.stringify(selectedRequest.request.filters_json || {}, null, 2)}</pre>
                </div>

                <div>
                  <h3 className="section-title">Artifacts</h3>
                  <div className="details-list">
                    {(selectedRequest.artifacts || []).length === 0 ? (
                      <p className="empty-text">No artifacts generated.</p>
                    ) : (
                      selectedRequest.artifacts.map((artifact) => (
                        <div key={artifact.id} className="details-list-item">
                          <div>
                            <strong>{artifact.filename}</strong>
                            <p>rows: {artifact.row_count ?? "-"} · hash: {artifact.sha256}</p>
                            <small>expires: {artifact.expires_at ? new Date(artifact.expires_at).toLocaleString() : "-"}</small>
                          </div>
                          <Button variant="secondary" size="sm" onClick={() => downloadArtifact(artifact.id, artifact.filename)}>Download</Button>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="section-title">Approval Requests</h3>
                  <div className="details-list">
                    {(selectedRequest.approvals || []).length === 0 ? (
                      <p className="empty-text">No approval records.</p>
                    ) : (
                      selectedRequest.approvals.map((approval) => (
                        <div key={approval.id} className="details-list-item compact">
                          <div>
                            <strong>#{approval.id}</strong>
                            <p>{approval.status} · {approval.policy_name}</p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="section-title">Audit Trail</h3>
                  <div className="details-list">
                    {auditTrail.length === 0 ? (
                      <p className="empty-text">No audit events for this request.</p>
                    ) : (
                      auditTrail.map((event) => (
                        <div key={event.id} className="details-list-item compact">
                          <div>
                            <strong>{event.action}</strong>
                            <p>{event.actor_email || "System"}</p>
                            <small>{event.created_at ? new Date(event.created_at).toLocaleString() : "-"}</small>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
