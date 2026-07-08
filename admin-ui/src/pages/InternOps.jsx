import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import { motion } from "framer-motion";
import { ClipboardList, AlarmClock, ListChecks, Gavel, CalendarClock, ShieldAlert } from "lucide-react";
import "./PersonDetail.css";

function StatCard({ icon: Icon, label, value, tone }) {
  return (
    <div className="glass-panel" style={{ flex: 1, minWidth: "150px", textAlign: "center", padding: "1rem" }}>
      <Icon size={20} style={{ color: tone || "var(--color-primary)", marginBottom: "0.25rem" }} />
      <div style={{ fontSize: "1.6rem", fontWeight: 700, color: value > 0 ? (tone || "var(--color-text-primary)") : "var(--color-text-secondary)" }}>
        {value}
      </div>
      <div style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>{label}</div>
    </div>
  );
}

function PersonLink({ item }) {
  return (
    <Link to={`/ui/people/${item.person_id}`} style={{ color: "var(--color-primary)", fontWeight: 600 }}>
      {item.full_name}
    </Link>
  );
}

function SectionPanel({ icon: Icon, title, emptyText, children, count }) {
  return (
    <div className="glass-panel">
      <div className="glass-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3><Icon size={18} /> {title}</h3>
        <span className={`badge ${count > 0 ? "badge-neutral" : "badge-success"}`}>{count}</span>
      </div>
      {count === 0 ? <p className="text-muted" style={{ margin: "0.5rem 0 0" }}>{emptyText}</p> : children}
    </div>
  );
}

export default function InternOps() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);

  const fetchSummary = useCallback(async () => {
    const res = await api.get("/admin/internship/ops-summary");
    setSummary(res.data);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await fetchSummary();
      } catch (err) {
        toast.error(err.message || "Failed to load intern operations summary");
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchSummary, toast]);

  if (loading) return <PageLoader message="Loading intern operations..." />;
  if (!summary) return <div className="person-detail-page"><p className="text-muted">No data available.</p></div>;

  const counts = summary.counts || {};

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="person-detail-page">
      <div className="page-header" style={{ marginBottom: "1.5rem" }}>
        <div>
          <h1 className="page-title">Intern Ops</h1>
          <p className="page-subtitle">
            {summary.scope === "all" ? "Program-wide view" : "Your direct reports"} — everything that needs a manager's attention.
          </p>
        </div>
      </div>

      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1.5rem" }}>
        <StatCard icon={ClipboardList} label="Reviews to grade" value={counts.action_queue || 0} />
        <StatCard icon={AlarmClock} label="Overdue reflections" value={counts.overdue_reflections || 0} tone="var(--color-danger)" />
        <StatCard icon={ListChecks} label="Overdue onboarding" value={counts.overdue_onboarding || 0} tone="var(--color-danger)" />
        <StatCard icon={Gavel} label="Pending decisions" value={counts.pending_decisions || 0} />
        <StatCard icon={CalendarClock} label="Milestones due" value={counts.milestones_due || 0} />
        <StatCard icon={ShieldAlert} label="At-risk interns" value={counts.at_risk || 0} tone="var(--color-danger)" />
      </div>

      <div className="grid grid-2" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1.5rem" }}>
        <SectionPanel icon={ClipboardList} title="Action Queue — grade these reviews" emptyText="Nothing waiting on you. Nice." count={(summary.action_queue || []).length}>
          {(summary.action_queue || []).map((item) => (
            <div key={item.review_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
              <div>
                <PersonLink item={item} />
                <span style={{ display: "block", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                  {item.period_start} to {item.period_end}{item.intern_track ? ` • ${item.intern_track}` : ""}
                  {item.stage === "poc" ? " • awaiting PoC assessment" : " • awaiting manager grading"}
                </span>
              </div>
              <Link to={`/ui/people/${item.person_id}`} className="badge badge-neutral">{item.stage === "poc" ? "Assess" : "Grade"}</Link>
            </div>
          ))}
        </SectionPanel>

        <SectionPanel icon={AlarmClock} title="Overdue Intern Reflections" emptyText="No overdue reflections." count={(summary.overdue_reflections || []).length}>
          {(summary.overdue_reflections || []).map((item) => (
            <div key={item.review_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
              <div>
                <PersonLink item={item} />
                <span style={{ display: "block", fontSize: "var(--font-size-xs)", color: "var(--color-danger)" }}>
                  Period ended {item.period_end} — {item.days_overdue} day{item.days_overdue === 1 ? "" : "s"} overdue
                </span>
              </div>
            </div>
          ))}
        </SectionPanel>

        <SectionPanel icon={ListChecks} title="Overdue Onboarding" emptyText="All onboarding on track." count={(summary.overdue_onboarding || []).length}>
          {(summary.overdue_onboarding || []).map((entry) => (
            <div key={entry.person_id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <PersonLink item={entry} />
                <span className="badge badge-neutral">{entry.overdue_count} overdue</span>
              </div>
              <ul style={{ margin: "0.25rem 0 0 1rem", fontSize: "var(--font-size-xs)", color: "var(--color-text-secondary)" }}>
                {entry.items.slice(0, 3).map((i) => (
                  <li key={i.item_id}>{i.title} (due {i.due_date}{i.owner_role ? `, owner: ${i.owner_role}` : ""})</li>
                ))}
                {entry.items.length > 3 && <li>…and {entry.items.length - 3} more</li>}
              </ul>
            </div>
          ))}
        </SectionPanel>

        <SectionPanel icon={Gavel} title="Pending Milestone Decisions" emptyText="No draft scorecards awaiting a decision." count={(summary.pending_decisions || []).length}>
          {(summary.pending_decisions || []).map((item) => (
            <div key={item.milestone_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
              <div>
                <PersonLink item={item} />
                <span style={{ display: "block", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                  {item.review_type.replace("_", " ")} • score {item.compiled_score}/5
                  {item.ai_recommendations_approved ? " • draft approved" : " • draft NOT yet approved"}
                </span>
              </div>
              <Link to={`/ui/people/${item.person_id}`} className="badge badge-neutral">Decide</Link>
            </div>
          ))}
        </SectionPanel>

        <SectionPanel icon={CalendarClock} title="Milestones Due for Compilation" emptyText="No milestone scorecards due." count={(summary.milestones_due || []).length}>
          {(summary.milestones_due || []).map((item) => (
            <div key={`${item.person_id}-${item.due_type}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
              <div>
                <PersonLink item={item} />
                <span style={{ display: "block", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                  {item.due_type.replace("_", " ")} review • day {item.days_in_program} in program
                </span>
              </div>
              <Link to={`/ui/people/${item.person_id}`} className="badge badge-neutral">Compile</Link>
            </div>
          ))}
        </SectionPanel>

        <SectionPanel icon={ShieldAlert} title="At-Risk Board" emptyText="No interns currently flagged." count={(summary.at_risk || []).length}>
          {(summary.at_risk || []).map((item) => (
            <div key={item.person_id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <PersonLink item={item} />
                <span style={{ fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                  {item.recent_scores.length > 0 ? `Recent scores: ${item.recent_scores.join(", ")}` : "No recent scores"}
                </span>
              </div>
              <div style={{ marginTop: "0.25rem" }}>
                {(item.risk_flags || []).map((f) => (
                  <span key={f} className="badge badge-neutral" style={{ marginRight: "0.25rem", color: "var(--color-danger)" }}>{f}</span>
                ))}
                {item.reasons.includes("low_recent_scores") && (
                  <span className="badge badge-neutral" style={{ color: "var(--color-danger)" }}>low scores</span>
                )}
              </div>
            </div>
          ))}
        </SectionPanel>
      </div>
    </motion.div>
  );
}
