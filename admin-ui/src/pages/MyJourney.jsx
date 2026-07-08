import { useCallback, useEffect, useState } from "react";
import api from "../utils/api";
import Button from "../components/ui/Button";
import { TextArea } from "../components/ui/Input";
import Modal from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import { motion } from "framer-motion";
import { User, CheckSquare, MessagesSquare, Award } from "lucide-react";
import "./PersonDetail.css";

export default function MyJourney() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [journey, setJourney] = useState(null);
  const [selectedReview, setSelectedReview] = useState(null);
  const [reflection, setReflection] = useState("");

  const fetchJourney = useCallback(async () => {
    const res = await api.get("/admin/internship/my-journey");
    setJourney(res.data);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await fetchJourney();
      } catch (err) {
        toast.error(err.message || "Failed to load your journey");
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchJourney, toast]);

  const handleToggleItem = async (item) => {
    if (!item.id) return; // not initialized yet
    try {
      setSaving(true);
      const nextChecked = !item.checked;
      await api.patch(`/admin/internship/onboarding-item/${item.id}`, {
        checked: nextChecked,
        status: nextChecked ? "completed" : "pending",
      });
      toast.success(nextChecked ? "Task completed!" : "Task reopened");
      await fetchJourney();
    } catch (err) {
      toast.error(err.message || "Could not update task");
    } finally {
      setSaving(false);
    }
  };

  const handleSubmitReflection = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/internship/reviews/biweekly/${selectedReview.id}/intern-submit`, {
        responses: { accomplishments: reflection },
      });
      toast.success("Self-reflection submitted!");
      setSelectedReview(null);
      setReflection("");
      await fetchJourney();
    } catch (err) {
      toast.error(err.message || "Submission failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <PageLoader message="Loading your journey..." />;

  if (!journey?.linked) {
    return (
      <div className="person-detail-page">
        <div className="glass-panel" style={{ textAlign: "center", padding: "3rem", marginTop: "2rem" }}>
          <h2 style={{ marginBottom: "0.5rem" }}>No profile linked yet</h2>
          <p className="text-muted">
            Your account is not linked to a people profile. Ask your manager or HR to link your
            account, then refresh this page.
          </p>
        </div>
      </div>
    );
  }

  const { profile, onboarding, biweekly_reviews: biweeklies, milestone_reviews: milestones } = journey;
  const emp = profile.employment;
  const pendingReviews = biweeklies.filter((r) => r.status === "pending_intern");

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="person-detail-page">
      <div className="page-header" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <div className="avatar-circle" style={{ width: "60px", height: "60px", fontSize: "1.5rem" }}>
            {profile.full_name?.split(" ").map((p) => p[0]).slice(0, 2).join("")}
          </div>
          <div>
            <h1 className="page-title">My Journey</h1>
            <p className="page-subtitle">
              {profile.full_name} • {emp?.title || "No active role"}
              {emp?.manager_name ? ` • Manager: ${emp.manager_name}` : ""}
            </p>
          </div>
        </div>
      </div>

      {pendingReviews.length > 0 && (
        <div className="glass-panel" style={{ marginBottom: "1.5rem", borderLeft: "3px solid var(--color-primary)" }}>
          <div className="glass-header"><h3><MessagesSquare size={18} /> Action needed: your self-reflection</h3></div>
          {pendingReviews.map((r) => (
            <div key={r.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0" }}>
              <span style={{ fontSize: "var(--font-size-sm)" }}>
                Review period <strong>{r.period_start}</strong> to <strong>{r.period_end}</strong>
              </span>
              <Button variant="primary" onClick={() => { setSelectedReview(r); setReflection(""); }}>
                Submit Reflection
              </Button>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-3">
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div className="glass-panel">
            <div className="glass-header"><h3><User size={18} /> My Profile</h3></div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "var(--font-size-sm)" }}>
              <div><span className="text-muted">Email:</span> {profile.email}</div>
              <div><span className="text-muted">Team:</span> {profile.team || "—"}</div>
              <div><span className="text-muted">Department:</span> {profile.department || "—"}</div>
              <div><span className="text-muted">Cohort:</span> {profile.cohort || "—"}</div>
              {emp && (
                <>
                  <div><span className="text-muted">Track:</span> {emp.intern_track || "—"}</div>
                  <div><span className="text-muted">Started:</span> {emp.start_date || "—"}</div>
                  {emp.mentor_name && <div><span className="text-muted">Mentor:</span> {emp.mentor_name}</div>}
                </>
              )}
              {(profile.assigned_projects || []).length > 0 && (
                <div>
                  <span className="text-muted">Projects:</span>{" "}
                  {profile.assigned_projects.map((p) => (
                    <span key={p} className="badge badge-neutral" style={{ marginRight: "0.25rem" }}>{p}</span>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="glass-panel">
            <div className="glass-header"><h3><CheckSquare size={18} /> My Onboarding</h3></div>
            <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1rem" }}>
              <div style={{ flex: 1, background: "var(--color-bg-tertiary)", height: "8px", borderRadius: "4px", overflow: "hidden" }}>
                <div style={{ width: `${onboarding?.progress_percent || 0}%`, background: "var(--color-primary)", height: "100%" }} />
              </div>
              <span style={{ fontWeight: "bold" }}>{onboarding?.progress_percent || 0}%</span>
            </div>
            {(onboarding?.items || []).length === 0 ? (
              <p className="text-muted">Your onboarding checklist has not been initialized yet.</p>
            ) : (
              onboarding.items.map((item) => (
                <div key={item.template_item_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
                  <div>
                    <span style={{ textDecoration: item.checked ? "line-through" : "none", fontSize: "var(--font-size-sm)", color: item.checked ? "var(--color-text-secondary)" : "var(--color-text-primary)" }}>
                      {item.title}
                    </span>
                    {(item.due_date || item.owner_role) && (
                      <span style={{ display: "block", fontSize: "var(--font-size-xs)", color: item.status === "overdue" ? "var(--color-danger)" : "var(--color-text-muted)" }}>
                        {item.due_date ? `Due: ${item.due_date} ` : ""}{item.status === "overdue" ? "(Overdue) " : ""}
                        {item.owner_role && item.owner_role !== "intern" ? `• Handled by: ${item.owner_role}` : ""}
                      </span>
                    )}
                  </div>
                  {item.owner_role === "intern" && item.id ? (
                    <button
                      className={`badge ${item.checked ? "badge-success" : "badge-neutral"}`}
                      style={{ border: "none", cursor: "pointer" }}
                      onClick={() => handleToggleItem(item)}
                      disabled={saving}
                    >
                      {item.checked ? "Done" : "Mark done"}
                    </button>
                  ) : (
                    <span className={`badge ${item.checked ? "badge-success" : "badge-neutral"}`}>
                      {item.checked ? "Done" : "Pending"}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div className="glass-panel">
            <div className="glass-header"><h3><MessagesSquare size={18} /> My Biweekly Reviews</h3></div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.5rem" }}>
              {biweeklies.length === 0 ? (
                <p className="text-muted">No review periods opened yet.</p>
              ) : (
                biweeklies.map((r) => (
                  <div key={r.id} style={{ padding: "0.75rem", background: "var(--color-bg-tertiary)", borderRadius: "var(--radius-md)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                      <strong style={{ fontSize: "var(--font-size-sm)" }}>{r.period_start} to {r.period_end}</strong>
                      <span className={`badge ${r.status === "completed" ? "badge-success" : "badge-neutral"}`}>{r.status.replace("_", " ")}</span>
                    </div>
                    {r.status === "completed" && (
                      <>
                        {r.score_progress && (
                          <div style={{ fontSize: "var(--font-size-sm)" }}>
                            Score: <strong style={{ color: "var(--color-primary)" }}>{r.score_progress}/5</strong>
                          </div>
                        )}
                        {r.strengths && (
                          <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>
                            Strengths: {r.strengths}
                          </div>
                        )}
                        {(r.action_items || []).length > 0 && (
                          <ul style={{ margin: "0.25rem 0 0 1rem", fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>
                            {r.action_items.map((a, i) => (
                              <li key={i}>{a.task}{a.due ? ` (due ${a.due})` : ""}</li>
                            ))}
                          </ul>
                        )}
                      </>
                    )}
                    {r.status === "pending_intern" && (
                      <Button variant="primary" style={{ width: "100%", marginTop: "0.25rem" }} onClick={() => { setSelectedReview(r); setReflection(""); }}>
                        Submit Self Reflection
                      </Button>
                    )}
                    {r.status === "pending_manager" && (
                      <p className="text-muted" style={{ fontSize: "var(--font-size-xs)", margin: 0 }}>
                        Submitted — waiting on your manager's evaluation.
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div className="glass-panel">
            <div className="glass-header"><h3><Award size={18} /> My Milestone Results</h3></div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.5rem" }}>
              {milestones.length === 0 ? (
                <p className="text-muted">No released milestone reviews yet. Results appear here once your manager finalizes them.</p>
              ) : (
                milestones.map((m) => (
                  <div key={m.id} style={{ padding: "0.75rem", background: "var(--color-bg-tertiary)", borderRadius: "var(--radius-md)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                      <strong style={{ textTransform: "capitalize" }}>{m.review_type.replace("_", " ")} Review</strong>
                      <span className="badge badge-success">{m.final_decision?.toUpperCase() || m.status}</span>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "var(--font-size-sm)", marginBottom: "0.5rem" }}>
                      <div>Score: <strong>{m.compiled_score}/5</strong></div>
                      <div>Onboarding: <strong>{m.onboarding_progress}%</strong></div>
                    </div>
                    {m.report_card_json?.competencies && (
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.25rem 0.75rem", fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>
                        {Object.entries(m.report_card_json.competencies).map(([name, score]) => (
                          <div key={name} style={{ display: "flex", justifyContent: "space-between" }}>
                            <span style={{ textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</span>
                            <strong style={{ color: "var(--color-text-primary)" }}>{score}</strong>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      <Modal isOpen={!!selectedReview} onClose={() => setSelectedReview(null)} title="Biweekly Self-Reflection">
        {selectedReview && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1rem" }}>
            <div>
              Period: <strong>{selectedReview.period_start} to {selectedReview.period_end}</strong>
            </div>
            {(selectedReview.manager_questions || []).length > 0 && (
              <div>
                <label className="input-label">Reflection prompts</label>
                <ul style={{ margin: "0.25rem 0 0 1rem", fontSize: "var(--font-size-sm)", color: "var(--color-text-secondary)" }}>
                  {selectedReview.manager_questions.map((q, i) => <li key={i}>{q}</li>)}
                </ul>
              </div>
            )}
            <TextArea
              label="Accomplishments & learnings"
              rows={4}
              placeholder="What did you achieve this period? What did you learn? Any blockers?"
              value={reflection}
              onChange={(e) => setReflection(e.target.value)}
            />
            <Button variant="primary" loading={saving} disabled={!reflection.trim()} onClick={handleSubmitReflection}>
              Submit Self Reflection
            </Button>
          </div>
        )}
      </Modal>
    </motion.div>
  );
}
