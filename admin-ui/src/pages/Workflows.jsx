import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./Workflows.css";

const WORKFLOW_TYPES = ["onboarding", "offboarding", "custom"];

export default function Workflows() {
  const navigate = useNavigate();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState("runs");
  const [runs, setRuns] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showStartModal, setShowStartModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [saving, setSaving] = useState(false);

  const [startForm, setStartForm] = useState({
    template_id: "",
    subject_name: "",
    subject_user_id: "",
    note: "",
  });

  const [templateForm, setTemplateForm] = useState({
    name: "",
    workflow_type: "onboarding",
    description: "",
    steps: [{ title: "", description: "", assignee_role: "" }],
  });

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [runsRes, templatesRes] = await Promise.all([
        api.get("/admin/workflows/runs"),
        api.get("/admin/workflows/templates"),
      ]);
      setRuns(runsRes.data.items || runsRes.data || []);
      setTemplates(templatesRes.data.items || templatesRes.data || []);
    } catch {
      toast.error("Failed to load workflows");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getTypeBadgeVariant = (type) => {
    const map = { onboarding: "info", offboarding: "warning", custom: "default" };
    return map[type] || "default";
  };

  const getStatusVariant = (status) => {
    const map = { completed: "success", in_progress: "warning", pending: "default", cancelled: "error" };
    return map[status] || "default";
  };

  const handleStartWorkflow = async () => {
    if (!startForm.template_id) {
      toast.error("Please select a template");
      return;
    }
    if (!startForm.subject_name && !startForm.subject_user_id) {
      toast.error("Please provide a subject name or user ID");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/workflows/runs", startForm);
      toast.success("Workflow started");
      setShowStartModal(false);
      setStartForm({ template_id: "", subject_name: "", subject_user_id: "", note: "" });
      fetchData();
    } catch {
      toast.error("Failed to start workflow");
    } finally {
      setSaving(false);
    }
  };

  const addStep = () => {
    setTemplateForm({
      ...templateForm,
      steps: [...templateForm.steps, { title: "", description: "", assignee_role: "" }],
    });
  };

  const removeStep = (index) => {
    const steps = templateForm.steps.filter((_, i) => i !== index);
    setTemplateForm({ ...templateForm, steps: steps.length ? steps : [{ title: "", description: "", assignee_role: "" }] });
  };

  const updateStep = (index, field, value) => {
    const steps = [...templateForm.steps];
    steps[index] = { ...steps[index], [field]: value };
    setTemplateForm({ ...templateForm, steps });
  };

  const handleCreateTemplate = async () => {
    if (!templateForm.name) {
      toast.error("Template name is required");
      return;
    }
    const validSteps = templateForm.steps.filter((s) => s.title);
    if (validSteps.length === 0) {
      toast.error("At least one step with a title is required");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/workflows/templates", {
        ...templateForm,
        steps: validSteps,
      });
      toast.success("Template created");
      setShowTemplateModal(false);
      setTemplateForm({
        name: "",
        workflow_type: "onboarding",
        description: "",
        steps: [{ title: "", description: "", assignee_role: "" }],
      });
      fetchData();
    } catch {
      toast.error("Failed to create template");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteTemplate = async () => {
    try {
      setSaving(true);
      await api.delete(`/admin/workflows/templates/${deleteConfirm.id}`);
      toast.success("Template deleted");
      setDeleteConfirm(null);
      fetchData();
    } catch {
      toast.error("Failed to delete template");
    } finally {
      setSaving(false);
    }
  };

  const formatDate = (d) => (d ? new Date(d).toLocaleString() : "-");

  if (loading && runs.length === 0 && templates.length === 0) {
    return <PageLoader message="Loading workflows..." />;
  }

  return (
    <div className="workflows-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Onboarding / Offboarding</h1>
          <p className="page-subtitle">Manage workflow templates and active runs</p>
        </div>
        <div className="page-header-actions">
          {activeTab === "runs" ? (
            <Button variant="primary" onClick={() => setShowStartModal(true)}>Start Workflow</Button>
          ) : (
            <Button variant="primary" onClick={() => setShowTemplateModal(true)}>Create Template</Button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="tab-bar">
        <button className={`tab-btn ${activeTab === "runs" ? "active" : ""}`} onClick={() => setActiveTab("runs")}>
          Active Runs
        </button>
        <button className={`tab-btn ${activeTab === "templates" ? "active" : ""}`} onClick={() => setActiveTab("templates")}>
          Templates
        </button>
      </div>

      {/* Active Runs Tab */}
      {activeTab === "runs" && (
        <Card>
          <CardBody>
            {runs.length === 0 ? (
              <div className="empty-state">
                <p className="empty-state-title">No active workflow runs</p>
                <p className="empty-state-text">Start a workflow from a template to begin</p>
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Run ID</th>
                      <th>Template</th>
                      <th>Type</th>
                      <th>Subject</th>
                      <th>Progress</th>
                      <th>Status</th>
                      <th>Started By</th>
                      <th>Started At</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => {
                      const completed = run.steps_completed ?? 0;
                      const total = run.steps_total ?? 0;
                      const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
                      return (
                        <tr key={run.id}>
                          <td className="run-id">{run.id?.toString().slice(0, 8) || "-"}</td>
                          <td className="template-name">{run.template_name || "-"}</td>
                          <td>
                            <Badge variant={getTypeBadgeVariant(run.workflow_type)}>
                              {run.workflow_type}
                            </Badge>
                          </td>
                          <td>{run.subject_name || run.subject_user_id || "-"}</td>
                          <td>
                            <div className="progress-cell">
                              <div className="progress-bar">
                                <div className="progress-fill" style={{ width: `${pct}%` }} />
                              </div>
                              <span className="progress-text">{completed}/{total}</span>
                            </div>
                          </td>
                          <td><Badge variant={getStatusVariant(run.status)}>{run.status}</Badge></td>
                          <td className="text-muted">{run.started_by || "-"}</td>
                          <td className="timestamp">{formatDate(run.created_at)}</td>
                          <td>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => navigate(`/ui/workflows/runs/${run.id}`)}
                            >
                              View
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {/* Templates Tab */}
      {activeTab === "templates" && (
        <div className="template-grid">
          {templates.length === 0 ? (
            <Card>
              <CardBody>
                <div className="empty-state">
                  <p className="empty-state-title">No templates</p>
                  <p className="empty-state-text">Create a workflow template to get started</p>
                </div>
              </CardBody>
            </Card>
          ) : (
            templates.map((tpl) => (
              <Card key={tpl.id}>
                <CardBody>
                  <div className="template-card-content">
                    <div className="template-card-header">
                      <h3 className="template-card-title">{tpl.name}</h3>
                      <Badge variant={getTypeBadgeVariant(tpl.workflow_type)}>{tpl.workflow_type}</Badge>
                    </div>
                    <p className="template-card-desc">{tpl.description || "No description"}</p>
                    <div className="template-card-meta">
                      <span>{tpl.steps?.length || tpl.step_count || 0} steps</span>
                      <span>Created by {tpl.created_by || "system"}</span>
                    </div>
                    <div className="template-card-actions">
                      <Button variant="danger" size="sm" onClick={() => setDeleteConfirm(tpl)}>Delete</Button>
                    </div>
                  </div>
                </CardBody>
              </Card>
            ))
          )}
        </div>
      )}

      {/* Start Workflow Modal */}
      <Modal
        isOpen={showStartModal}
        onClose={() => setShowStartModal(false)}
        title="Start Workflow"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowStartModal(false)} disabled={saving}>Cancel</Button>
            <Button variant="primary" onClick={handleStartWorkflow} loading={saving}>Start</Button>
          </>
        }
      >
        <div className="form-grid">
          <Select
            label="Template"
            value={startForm.template_id}
            onChange={(e) => setStartForm({ ...startForm, template_id: e.target.value })}
          >
            <option value="">Select a template...</option>
            {templates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>{tpl.name} ({tpl.workflow_type})</option>
            ))}
          </Select>
          <Input
            label="Subject Name"
            placeholder="e.g. John Doe"
            value={startForm.subject_name}
            onChange={(e) => setStartForm({ ...startForm, subject_name: e.target.value })}
          />
          <Input
            label="Subject User ID (optional)"
            placeholder="User ID or email"
            value={startForm.subject_user_id}
            onChange={(e) => setStartForm({ ...startForm, subject_user_id: e.target.value })}
          />
          <TextArea
            label="Note"
            placeholder="Optional note..."
            value={startForm.note}
            onChange={(e) => setStartForm({ ...startForm, note: e.target.value })}
          />
        </div>
      </Modal>

      {/* Create Template Modal */}
      <Modal
        isOpen={showTemplateModal}
        onClose={() => setShowTemplateModal(false)}
        title="Create Template"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowTemplateModal(false)} disabled={saving}>Cancel</Button>
            <Button variant="primary" onClick={handleCreateTemplate} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-grid">
          <Input
            label="Name"
            placeholder="e.g. New Hire Onboarding"
            value={templateForm.name}
            onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value })}
            required
          />
          <Select
            label="Workflow Type"
            value={templateForm.workflow_type}
            onChange={(e) => setTemplateForm({ ...templateForm, workflow_type: e.target.value })}
          >
            {WORKFLOW_TYPES.map((t) => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </Select>
          <TextArea
            label="Description"
            placeholder="Describe this workflow..."
            value={templateForm.description}
            onChange={(e) => setTemplateForm({ ...templateForm, description: e.target.value })}
          />

          <div className="steps-section">
            <div className="steps-header">
              <label className="input-label">Steps</label>
              <Button variant="secondary" size="sm" onClick={addStep}>+ Add Step</Button>
            </div>
            {templateForm.steps.map((step, idx) => (
              <div key={idx} className="step-row">
                <span className="step-number">{idx + 1}</span>
                <Input
                  placeholder="Step title"
                  value={step.title}
                  onChange={(e) => updateStep(idx, "title", e.target.value)}
                />
                <Input
                  placeholder="Description"
                  value={step.description}
                  onChange={(e) => updateStep(idx, "description", e.target.value)}
                />
                <Input
                  placeholder="Assignee role"
                  value={step.assignee_role}
                  onChange={(e) => updateStep(idx, "assignee_role", e.target.value)}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeStep(idx)}
                  disabled={templateForm.steps.length === 1}
                >
                  Remove
                </Button>
              </div>
            ))}
          </div>
        </div>
      </Modal>

      <ConfirmModal
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={handleDeleteTemplate}
        title="Delete Template"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This cannot be undone.`}
        confirmText="Delete"
        loading={saving}
      />
    </div>
  );
}
