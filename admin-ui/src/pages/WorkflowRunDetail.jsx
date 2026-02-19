import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import { TextArea } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./WorkflowRunDetail.css";

export default function WorkflowRunDetail() {
  const { id } = useParams();
  const toast = useToast();

  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [stepNotes, setStepNotes] = useState({});

  const fetchRun = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/workflows/runs/${id}`);
      setRun(res.data);
    } catch {
      toast.error("Failed to load workflow run");
    } finally {
      setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => {
    fetchRun();
  }, [fetchRun]);

  const handleStepAction = async (stepId, action) => {
    try {
      setSaving(stepId);
      await api.patch(`/admin/workflows/runs/${id}/steps/${stepId}`, {
        status: action,
        notes: stepNotes[stepId] || undefined,
      });
      toast.success(`Step ${action === "completed" ? "completed" : "skipped"}`);
      fetchRun();
    } catch {
      toast.error("Failed to update step");
    } finally {
      setSaving(null);
    }
  };

  const getStatusVariant = (status) => {
    const map = { completed: "success", in_progress: "warning", pending: "default", skipped: "default", cancelled: "error" };
    return map[status] || "default";
  };

  const getTypeBadgeVariant = (type) => {
    const map = { onboarding: "info", offboarding: "warning", custom: "default" };
    return map[type] || "default";
  };

  const formatDate = (d) => (d ? new Date(d).toLocaleString() : "-");

  if (loading) {
    return <PageLoader message="Loading workflow run..." />;
  }

  if (!run) {
    return (
      <div className="workflow-detail-page">
        <div className="empty-state">
          <p className="empty-state-title">Workflow run not found</p>
          <Link to="/ui/workflows">Back to Workflows</Link>
        </div>
      </div>
    );
  }

  const steps = run.steps || [];
  const completedCount = steps.filter((s) => s.status === "completed").length;
  const totalCount = steps.length;
  const pct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <div className="workflow-detail-page">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            <Link to="/ui/workflows">Workflows</Link>
            <span>/</span>
            <span>Run Details</span>
          </div>
          <h1 className="page-title">{run.template_name || "Workflow Run"}</h1>
          <p className="page-subtitle">
            {run.subject_name || run.subject_user_id || "Unknown subject"}
          </p>
        </div>
      </div>

      {/* Run Info */}
      <Card>
        <CardBody>
          <div className="run-info-grid">
            <div className="run-info-item">
              <span className="run-info-label">Type</span>
              <Badge variant={getTypeBadgeVariant(run.workflow_type)}>{run.workflow_type}</Badge>
            </div>
            <div className="run-info-item">
              <span className="run-info-label">Status</span>
              <Badge variant={getStatusVariant(run.status)}>{run.status}</Badge>
            </div>
            <div className="run-info-item">
              <span className="run-info-label">Started By</span>
              <span>{run.started_by || "-"}</span>
            </div>
            <div className="run-info-item">
              <span className="run-info-label">Started At</span>
              <span>{formatDate(run.created_at)}</span>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Progress */}
      <div className="progress-section">
        <div className="progress-header">
          <span className="progress-label">Progress: {completedCount} / {totalCount} steps</span>
          <span className="progress-pct">{pct}%</span>
        </div>
        <div className="progress-bar-lg">
          <div className="progress-fill-lg" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Steps Checklist */}
      <Card>
        <CardHeader title="Steps" />
        <CardBody>
          {steps.length === 0 ? (
            <div className="empty-state">
              <p className="empty-state-title">No steps defined</p>
            </div>
          ) : (
            <div className="steps-list">
              {steps.map((step, idx) => (
                <div key={step.id || idx} className={`step-item ${step.status === "completed" ? "step-completed" : ""} ${step.status === "skipped" ? "step-skipped" : ""}`}>
                  <div className="step-icon">
                    {step.status === "completed" ? (
                      <span className="check-icon">&#10003;</span>
                    ) : step.status === "skipped" ? (
                      <span className="skip-icon">-</span>
                    ) : (
                      <span className="step-order">{idx + 1}</span>
                    )}
                  </div>
                  <div className="step-content">
                    <div className="step-title-row">
                      <h4 className="step-title">{step.title}</h4>
                      <Badge variant={getStatusVariant(step.status)}>{step.status}</Badge>
                    </div>
                    {step.description && (
                      <p className="step-description">{step.description}</p>
                    )}
                    {step.status === "completed" && (
                      <div className="step-completed-info">
                        Completed by {step.completed_by || "unknown"} on {formatDate(step.completed_at)}
                      </div>
                    )}
                    {step.status === "pending" && (
                      <div className="step-actions">
                        <TextArea
                          placeholder="Optional notes..."
                          value={stepNotes[step.id] || ""}
                          onChange={(e) => setStepNotes({ ...stepNotes, [step.id]: e.target.value })}
                        />
                        <div className="step-action-buttons">
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => handleStepAction(step.id, "completed")}
                            loading={saving === step.id}
                          >
                            Mark Complete
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleStepAction(step.id, "skipped")}
                            loading={saving === step.id}
                          >
                            Skip
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
