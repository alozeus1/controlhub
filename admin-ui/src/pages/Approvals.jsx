import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Select, TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Pagination from "../components/ui/Pagination";
import Modal from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import Tooltip from "../components/ui/Tooltip";
import "./Approvals.css";

const STATUS_VARIANTS = {
  pending: "warning",
  approved: "success",
  rejected: "error",
  cancelled: "default",
};

const formatTimeAgo = (dateStr) => {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    return `${mins}m ago`;
  }
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    return `${hours}h ago`;
  }
  const days = Math.floor(seconds / 86400);
  return `${days}d ago`;
};

const formatFullDate = (dateStr) => {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleString();
};

export default function Approvals() {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [statusFilter, setStatusFilter] = useState("pending");
  const [selectedApproval, setSelectedApproval] = useState(null);
  const [showDecisionModal, setShowDecisionModal] = useState(false);
  const [decisionType, setDecisionType] = useState(null);
  const [comment, setComment] = useState("");
  const [processing, setProcessing] = useState(false);
  const toast = useToast();

  const currentUser = JSON.parse(localStorage.getItem("user") || "{}");

  const fetchApprovals = useCallback(async (page = 1) => {
    try {
      setLoading(true);
      let url = `/admin/approvals?page=${page}&page_size=20`;
      if (statusFilter) {
        url += `&status=${statusFilter}`;
      }
      const res = await api.get(url);
      setApprovals(res.data.items || []);
      setPagination({
        page: res.data.page,
        pages: res.data.pages,
        total: res.data.total,
        page_size: res.data.page_size,
      });
    } catch (err) {
      toast.error("Failed to load approvals");
      setApprovals([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, toast]);

  useEffect(() => {
    fetchApprovals(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const openDecisionModal = (approval, type) => {
    setSelectedApproval(approval);
    setDecisionType(type);
    setComment("");
    setShowDecisionModal(true);
  };

  const handleDecision = async () => {
    if (!selectedApproval || !decisionType) return;

    try {
      setProcessing(true);
      const endpoint = decisionType === "approve" ? "approve" : "reject";
      const res = await api.post(`/admin/approvals/${selectedApproval.id}/${endpoint}`, {
        comment: comment || undefined,
      });

      if (decisionType === "approve" && res.data.execution_result?.success) {
        toast.success(`Request approved and executed: ${res.data.execution_result.message}`);
      } else if (decisionType === "approve") {
        toast.success(res.data.message || "Approval recorded");
      } else {
        toast.success("Request rejected");
      }

      setShowDecisionModal(false);
      fetchApprovals(pagination.page);
    } catch (err) {
      toast.error(err.message || `Failed to ${decisionType} request`);
    } finally {
      setProcessing(false);
    }
  };

  const canMakeDecision = (approval) => {
    if (approval.status !== "pending") return false;
    if (approval.requester_id === currentUser.id) return false;
    return true;
  };

  const getActionLabel = (action) => {
    const labels = {
      "upload.delete": "Delete Upload",
      "user.role_change": "Change User Role",
      "user.disable": "Disable User",
      "job.cancel": "Cancel Job",
    };
    return labels[action] || action;
  };

  const pendingCount = approvals.filter(a => a.status === "pending").length;

  return (
    <div className="approvals-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Approval Requests</h1>
          <p className="page-subtitle">Review and approve/reject pending requests</p>
        </div>
        <Link to="/ui/policies">
          <Button variant="secondary">Manage Policies</Button>
        </Link>
      </div>

      {statusFilter === "pending" && pendingCount > 0 && (
        <div className="pending-banner">
          <span className="pending-icon">⏳</span>
          <span>{pendingCount} request(s) awaiting your review</span>
        </div>
      )}

      <Card>
        <CardHeader
          title={`${pagination.total} Request${pagination.total !== 1 ? "s" : ""}`}
          action={
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ width: 150 }}
            >
              <option value="">All Status</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </Select>
          }
        />
        <CardBody>
          {loading ? (
            <PageLoader message="Loading approvals..." />
          ) : approvals.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                {statusFilter === "pending" ? "✅" : "📋"}
              </div>
              <p className="empty-state-title">
                {statusFilter === "pending" ? "No pending requests" : "No approval requests"}
              </p>
              <p className="empty-state-text">
                {statusFilter === "pending"
                  ? "All caught up! No actions awaiting approval."
                  : "Approval requests will appear here when policies require them."}
              </p>
            </div>
          ) : (
            <>
              <table className="approvals-table">
                <thead>
                  <tr>
                    <th>Request</th>
                    <th>Requester</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {approvals.map((approval) => (
                    <tr key={approval.id} className={approval.status === "pending" ? "pending-row" : ""}>
                      <td>
                        <div className="request-cell">
                          <span className="request-action">{getActionLabel(approval.action)}</span>
                          <span className="request-target">
                            {approval.target_type}: {approval.target_label || `#${approval.target_id}`}
                          </span>
                          <span className="request-policy">Policy: {approval.policy_name}</span>
                        </div>
                      </td>
                      <td>
                        <span className="requester">{approval.requester_email}</span>
                      </td>
                      <td>
                        <div className="status-cell">
                          <Badge variant={STATUS_VARIANTS[approval.status]}>
                            {approval.status.charAt(0).toUpperCase() + approval.status.slice(1)}
                          </Badge>
                          {approval.status === "pending" && (
                            <span className="approval-progress">
                              {approval.approvals_received}/{approval.approvals_required}
                            </span>
                          )}
                        </div>
                      </td>
                      <td>
                        <Tooltip content={formatFullDate(approval.created_at)} position="top">
                          <span className="time-ago">{formatTimeAgo(approval.created_at)}</span>
                        </Tooltip>
                      </td>
                      <td>
                        {canMakeDecision(approval) ? (
                          <div className="action-buttons">
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => openDecisionModal(approval, "approve")}
                            >
                              Approve
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="danger"
                              onClick={() => openDecisionModal(approval, "reject")}
                            >
                              Reject
                            </Button>
                          </div>
                        ) : approval.status === "pending" ? (
                          <span className="cannot-decide">
                            {approval.requester_id === currentUser.id ? "Your request" : "-"}
                          </span>
                        ) : (
                          <Tooltip content={formatFullDate(approval.resolved_at)} position="top">
                            <span className="resolved-at">
                              Resolved {formatTimeAgo(approval.resolved_at)}
                            </span>
                          </Tooltip>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchApprovals}
              />
            </>
          )}
        </CardBody>
      </Card>

      {/* Decision Modal */}
      <Modal
        isOpen={showDecisionModal}
        onClose={() => setShowDecisionModal(false)}
        title={decisionType === "approve" ? "Approve Request" : "Reject Request"}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowDecisionModal(false)}>
              Cancel
            </Button>
            <Button
              variant={decisionType === "approve" ? "primary" : "danger"}
              onClick={handleDecision}
              loading={processing}
            >
              {decisionType === "approve" ? "Approve" : "Reject"}
            </Button>
          </>
        }
      >
        {selectedApproval && (
          <div className="decision-details">
            <div className="decision-summary">
              <p><strong>Action:</strong> {getActionLabel(selectedApproval.action)}</p>
              <p><strong>Target:</strong> {selectedApproval.target_label || `#${selectedApproval.target_id}`}</p>
              <p><strong>Requested by:</strong> {selectedApproval.requester_email}</p>
            </div>
            <TextArea
              label="Comment (optional)"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={decisionType === "reject" ? "Reason for rejection..." : "Add a comment..."}
              rows={3}
            />
            {decisionType === "approve" && (
              <div className="approve-warning">
                <span className="warning-icon">⚠️</span>
                <span>Approving will execute the action immediately.</span>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
