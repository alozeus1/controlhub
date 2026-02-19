import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Costs.css";

const PROVIDERS = ["aws", "gcp", "azure", "other"];
const PROVIDER_COLORS = { aws: "warning", gcp: "info", azure: "info", other: "default" };

function getCurrentPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function Costs() {
  const toast = useToast();
  const currentUser = JSON.parse(localStorage.getItem("user") || "{}");
  const isAdmin = currentUser.role === "admin" || currentUser.role === "super_admin";

  const [activeTab, setActiveTab] = useState("entries");
  const [costs, setCosts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [budgets, setBudgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [periodFilter, setPeriodFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [budgetStatusFilter, setBudgetStatusFilter] = useState("");
  const [showCostModal, setShowCostModal] = useState(false);
  const [showBudgetModal, setShowBudgetModal] = useState(false);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewingBudget, setReviewingBudget] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);

  const [costForm, setCostForm] = useState({
    cloud_provider: "aws",
    service_name: "",
    team: "",
    project: "",
    amount: "",
    currency: "USD",
    period: getCurrentPeriod(),
    notes: "",
  });

  const [budgetForm, setBudgetForm] = useState({
    title: "",
    team: "",
    project: "",
    amount_requested: "",
    justification: "",
  });

  const [reviewForm, setReviewForm] = useState({
    status: "approved",
    notes: "",
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const costParams = new URLSearchParams();
      if (periodFilter) costParams.append("period", periodFilter);
      if (teamFilter) costParams.append("team", teamFilter);

      const budgetParams = new URLSearchParams();
      if (budgetStatusFilter) budgetParams.append("status", budgetStatusFilter);

      const [costsRes, summaryRes, budgetsRes] = await Promise.all([
        api.get(`/admin/costs?${costParams}`),
        api.get("/admin/costs/summary"),
        api.get(`/admin/costs/budget-requests?${budgetParams}`),
      ]);
      setCosts(costsRes.data.items || costsRes.data || []);
      setSummary(summaryRes.data);
      setBudgets(budgetsRes.data.items || budgetsRes.data || []);
    } catch {
      toast.error("Failed to load cost data");
    } finally {
      setLoading(false);
    }
  }, [periodFilter, teamFilter, budgetStatusFilter, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const formatCurrency = (amount, currency = "USD") => {
    if (amount == null) return "-";
    return `$${Number(amount).toFixed(2)}`;
  };

  const handleAddCost = async () => {
    if (!costForm.service_name || !costForm.amount) {
      toast.error("Service name and amount are required");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/costs", {
        ...costForm,
        amount: Number(costForm.amount),
      });
      toast.success("Cost entry added");
      setShowCostModal(false);
      setCostForm({
        cloud_provider: "aws",
        service_name: "",
        team: "",
        project: "",
        amount: "",
        currency: "USD",
        period: getCurrentPeriod(),
        notes: "",
      });
      fetchData();
    } catch {
      toast.error("Failed to add cost entry");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCost = async () => {
    try {
      setSaving(true);
      await api.delete(`/admin/costs/${deleteConfirm.id}`);
      toast.success("Cost entry deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch {
      toast.error("Failed to delete cost entry");
    } finally {
      setSaving(false);
    }
  };

  const handleRequestBudget = async () => {
    if (!budgetForm.title || !budgetForm.amount_requested) {
      toast.error("Title and amount are required");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/costs/budget-requests", {
        ...budgetForm,
        amount_requested: Number(budgetForm.amount_requested),
      });
      toast.success("Budget request submitted");
      setShowBudgetModal(false);
      setBudgetForm({ title: "", team: "", project: "", amount_requested: "", justification: "" });
      fetchData();
    } catch {
      toast.error("Failed to submit budget request");
    } finally {
      setSaving(false);
    }
  };

  const openReview = (budget) => {
    setReviewingBudget(budget);
    setReviewForm({ status: "approved", notes: "" });
    setShowReviewModal(true);
  };

  const handleReview = async () => {
    try {
      setSaving(true);
      await api.patch(`/admin/costs/budget-requests/${reviewingBudget.id}`, reviewForm);
      toast.success(`Budget request ${reviewForm.status}`);
      setShowReviewModal(false);
      setReviewingBudget(null);
      fetchData();
    } catch {
      toast.error("Failed to review budget request");
    } finally {
      setSaving(false);
    }
  };

  const getBudgetStatusVariant = (status) => {
    const map = { pending: "warning", approved: "success", rejected: "error" };
    return map[status] || "default";
  };

  // Build CSS bar chart data
  const periodSummary = summary?.by_period || [];
  const maxAmount = Math.max(...periodSummary.map((p) => p.total || 0), 1);

  if (loading && costs.length === 0 && budgets.length === 0) {
    return <PageLoader message="Loading cost data..." />;
  }

  return (
    <div className="costs-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Cost Allocation</h1>
          <p className="page-subtitle">Track cloud spending and manage budget requests</p>
        </div>
        <div className="page-header-actions">
          {activeTab === "entries" ? (
            <Button variant="primary" onClick={() => setShowCostModal(true)}>Add Cost Entry</Button>
          ) : (
            <Button variant="primary" onClick={() => setShowBudgetModal(true)}>Request Budget</Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        <button className={`tab-btn ${activeTab === "entries" ? "active" : ""}`} onClick={() => setActiveTab("entries")}>
          Cost Entries
        </button>
        <button className={`tab-btn ${activeTab === "budgets" ? "active" : ""}`} onClick={() => setActiveTab("budgets")}>
          Budget Requests
        </button>
      </div>

      {/* Cost Entries Tab */}
      {activeTab === "entries" && (
        <>
          {/* Stats Row */}
          <div className="stats-cards">
            <div className="stat-card">
              <div className="stat-value">{summary?.total_entries || costs.length}</div>
              <div className="stat-label">Total Entries</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{formatCurrency(summary?.total_spend)}</div>
              <div className="stat-label">Total Spend</div>
            </div>
            {summary?.by_provider && Object.entries(summary.by_provider).map(([provider, amount]) => (
              <div className="stat-card" key={provider}>
                <div className="stat-value">{formatCurrency(amount)}</div>
                <div className="stat-label">
                  <Badge variant={PROVIDER_COLORS[provider] || "default"}>{provider.toUpperCase()}</Badge>
                </div>
              </div>
            ))}
          </div>

          {/* Bar Chart */}
          {periodSummary.length > 0 && (
            <Card>
              <CardHeader title="Monthly Spend" />
              <CardBody>
                <div className="bar-chart">
                  {periodSummary.map((p) => (
                    <div key={p.period} className="bar-row">
                      <span className="bar-label">{p.period}</span>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{ width: `${(p.total / maxAmount) * 100}%` }}
                        />
                      </div>
                      <span className="bar-value">{formatCurrency(p.total)}</span>
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}

          {/* Filters and Table */}
          <Card>
            <CardHeader
              title="Cost Entries"
              action={
                <div className="filters">
                  <Input
                    placeholder="Filter by period (YYYY-MM)"
                    value={periodFilter}
                    onChange={(e) => setPeriodFilter(e.target.value)}
                  />
                  <Input
                    placeholder="Filter by team"
                    value={teamFilter}
                    onChange={(e) => setTeamFilter(e.target.value)}
                  />
                </div>
              }
            />
            <CardBody>
              {costs.length === 0 ? (
                <div className="empty-state">
                  <p className="empty-state-title">No cost entries found</p>
                  <p className="empty-state-text">Add a cost entry to start tracking cloud spend</p>
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Provider</th>
                        <th>Service</th>
                        <th>Team</th>
                        <th>Project</th>
                        <th>Amount</th>
                        <th>Period</th>
                        <th>Notes</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {costs.map((cost) => (
                        <tr key={cost.id}>
                          <td>
                            <Badge variant={PROVIDER_COLORS[cost.cloud_provider] || "default"}>
                              {(cost.cloud_provider || "").toUpperCase()}
                            </Badge>
                          </td>
                          <td className="service-name">{cost.service_name}</td>
                          <td>{cost.team || "-"}</td>
                          <td>{cost.project || "-"}</td>
                          <td className="amount">{formatCurrency(cost.amount)}</td>
                          <td className="period">{cost.period}</td>
                          <td className="notes-cell">{cost.notes || "-"}</td>
                          <td>
                            {isAdmin && (
                              <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(cost)}>
                                Delete
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardBody>
          </Card>
        </>
      )}

      {/* Budget Requests Tab */}
      {activeTab === "budgets" && (
        <>
          {/* Status filter tabs */}
          <div className="status-filters">
            {["", "pending", "approved", "rejected"].map((s) => (
              <button
                key={s}
                className={`status-filter-btn ${budgetStatusFilter === s ? "active" : ""}`}
                onClick={() => setBudgetStatusFilter(s)}
              >
                {s ? s.charAt(0).toUpperCase() + s.slice(1) : "All"}
              </button>
            ))}
          </div>

          <Card>
            <CardBody>
              {budgets.length === 0 ? (
                <div className="empty-state">
                  <p className="empty-state-title">No budget requests</p>
                  <p className="empty-state-text">Submit a budget request to get started</p>
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Team</th>
                        <th>Project</th>
                        <th>Amount</th>
                        <th>Requested By</th>
                        <th>Status</th>
                        <th>Reviewed By</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {budgets.map((br) => (
                        <tr key={br.id}>
                          <td className="budget-title">{br.title}</td>
                          <td>{br.team || "-"}</td>
                          <td>{br.project || "-"}</td>
                          <td className="amount">{formatCurrency(br.amount_requested)}</td>
                          <td className="text-muted">{br.requested_by || "-"}</td>
                          <td><Badge variant={getBudgetStatusVariant(br.status)}>{br.status}</Badge></td>
                          <td className="text-muted">{br.reviewed_by || "-"}</td>
                          <td>
                            {isAdmin && br.status === "pending" && (
                              <Button variant="ghost" size="sm" onClick={() => openReview(br)}>
                                Review
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardBody>
          </Card>
        </>
      )}

      {/* Add Cost Entry Modal */}
      <Modal
        isOpen={showCostModal}
        onClose={() => setShowCostModal(false)}
        title="Add Cost Entry"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCostModal(false)} disabled={saving}>Cancel</Button>
            <Button variant="primary" onClick={handleAddCost} loading={saving}>Add</Button>
          </>
        }
      >
        <div className="form-grid">
          <Select
            label="Cloud Provider"
            value={costForm.cloud_provider}
            onChange={(e) => setCostForm({ ...costForm, cloud_provider: e.target.value })}
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{p.toUpperCase()}</option>
            ))}
          </Select>
          <Input
            label="Service Name"
            placeholder="e.g. EC2, Cloud Run"
            value={costForm.service_name}
            onChange={(e) => setCostForm({ ...costForm, service_name: e.target.value })}
            required
          />
          <Input
            label="Team"
            placeholder="e.g. Platform"
            value={costForm.team}
            onChange={(e) => setCostForm({ ...costForm, team: e.target.value })}
          />
          <Input
            label="Project"
            placeholder="e.g. main-api"
            value={costForm.project}
            onChange={(e) => setCostForm({ ...costForm, project: e.target.value })}
          />
          <Input
            label="Amount ($)"
            type="number"
            step="0.01"
            placeholder="e.g. 1234.56"
            value={costForm.amount}
            onChange={(e) => setCostForm({ ...costForm, amount: e.target.value })}
            required
          />
          <Input
            label="Period (YYYY-MM)"
            placeholder="e.g. 2026-02"
            value={costForm.period}
            onChange={(e) => setCostForm({ ...costForm, period: e.target.value })}
          />
          <TextArea
            label="Notes"
            placeholder="Optional notes..."
            value={costForm.notes}
            onChange={(e) => setCostForm({ ...costForm, notes: e.target.value })}
          />
        </div>
      </Modal>

      {/* Budget Request Modal */}
      <Modal
        isOpen={showBudgetModal}
        onClose={() => setShowBudgetModal(false)}
        title="Request Budget"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowBudgetModal(false)} disabled={saving}>Cancel</Button>
            <Button variant="primary" onClick={handleRequestBudget} loading={saving}>Submit</Button>
          </>
        }
      >
        <div className="form-grid">
          <Input
            label="Title"
            placeholder="e.g. Q2 Infrastructure Scaling"
            value={budgetForm.title}
            onChange={(e) => setBudgetForm({ ...budgetForm, title: e.target.value })}
            required
          />
          <Input
            label="Team"
            placeholder="e.g. Platform"
            value={budgetForm.team}
            onChange={(e) => setBudgetForm({ ...budgetForm, team: e.target.value })}
          />
          <Input
            label="Project"
            placeholder="e.g. main-api"
            value={budgetForm.project}
            onChange={(e) => setBudgetForm({ ...budgetForm, project: e.target.value })}
          />
          <Input
            label="Amount Requested ($)"
            type="number"
            step="0.01"
            placeholder="e.g. 5000.00"
            value={budgetForm.amount_requested}
            onChange={(e) => setBudgetForm({ ...budgetForm, amount_requested: e.target.value })}
            required
          />
          <TextArea
            label="Justification"
            placeholder="Explain why this budget is needed..."
            value={budgetForm.justification}
            onChange={(e) => setBudgetForm({ ...budgetForm, justification: e.target.value })}
          />
        </div>
      </Modal>

      {/* Review Budget Modal */}
      <Modal
        isOpen={showReviewModal}
        onClose={() => setShowReviewModal(false)}
        title={`Review: ${reviewingBudget?.title || ""}`}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowReviewModal(false)} disabled={saving}>Cancel</Button>
            <Button
              variant={reviewForm.status === "approved" ? "primary" : "danger"}
              onClick={handleReview}
              loading={saving}
            >
              {reviewForm.status === "approved" ? "Approve" : "Reject"}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <div className="review-info">
            <p>Amount: <strong>{formatCurrency(reviewingBudget?.amount_requested)}</strong></p>
            <p>Team: {reviewingBudget?.team || "-"}</p>
            {reviewingBudget?.justification && (
              <p className="review-justification">Justification: {reviewingBudget.justification}</p>
            )}
          </div>
          <Select
            label="Decision"
            value={reviewForm.status}
            onChange={(e) => setReviewForm({ ...reviewForm, status: e.target.value })}
          >
            <option value="approved">Approve</option>
            <option value="rejected">Reject</option>
          </Select>
          <TextArea
            label="Notes"
            placeholder="Optional review notes..."
            value={reviewForm.notes}
            onChange={(e) => setReviewForm({ ...reviewForm, notes: e.target.value })}
          />
        </div>
      </Modal>

      {/* Delete Cost Confirmation */}
      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDeleteCost}
        title="Delete Cost Entry"
        message={`Delete this ${deleteConfirm?.service_name} cost entry for ${formatCurrency(deleteConfirm?.amount)}?`}
        confirmText="Delete"
        loading={saving}
      />
    </div>
  );
}
