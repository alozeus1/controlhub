import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../utils/api";
import { Select } from "../components/ui/Input";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import { motion } from "framer-motion";
import { Users } from "lucide-react";
import "./PersonDetail.css";

export default function TeamLeadAssignments() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState({ team_leads: [], unassigned_interns: [] });

  const fetchRoster = useCallback(async () => {
    const res = await api.get("/admin/internship/team-lead-assignments");
    setData(res.data);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await fetchRoster();
      } catch (err) {
        toast.error(err.message || "Failed to load team lead assignments");
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchRoster, toast]);

  const handleAssign = async (personId, pocPersonId) => {
    try {
      setSaving(true);
      await api.put(`/admin/internship/people/${personId}/poc`, {
        poc_person_id: pocPersonId ? Number(pocPersonId) : null,
      });
      toast.success(pocPersonId ? "Intern assigned to team lead" : "Intern unassigned");
      await fetchRoster();
    } catch (err) {
      toast.error(err.message || "Assignment failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <PageLoader message="Loading team lead assignments..." />;

  const { team_leads: teamLeads, unassigned_interns: unassigned } = data;

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="person-detail-page">
      <div className="page-header" style={{ marginBottom: "1.5rem" }}>
        <div>
          <h1 className="page-title">Team Lead Assignments</h1>
          <p className="page-subtitle">
            Assign interns to a PoC/Team Lead for their biweekly reviews. Reassign anytime — changes apply to future review periods.
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "1.5rem" }}>
        {teamLeads.length === 0 ? (
          <div className="glass-panel">
            <p className="text-muted">No team leads yet. Create a user with the <code>team_lead</code> role and link a person profile.</p>
          </div>
        ) : (
          teamLeads.map((lead) => (
            <div key={lead.user_id} className="glass-panel">
              <div className="glass-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h3><Users size={18} /> {lead.full_name}</h3>
                <span className="badge badge-neutral">{lead.assigned_interns.length} intern{lead.assigned_interns.length === 1 ? "" : "s"}</span>
              </div>
              <p className="text-muted" style={{ fontSize: "var(--font-size-xs)", marginBottom: "0.75rem" }}>{lead.email}</p>
              {lead.assigned_interns.length === 0 ? (
                <p className="text-muted" style={{ fontSize: "var(--font-size-sm)" }}>No interns assigned.</p>
              ) : (
                lead.assigned_interns.map((intern) => (
                  <div key={intern.person_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
                    <div>
                      <Link to={`/ui/people/${intern.person_id}`} style={{ color: "var(--color-primary)", fontWeight: 600 }}>
                        {intern.full_name}
                      </Link>
                      {intern.intern_track && (
                        <span style={{ display: "block", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                          {intern.intern_track}
                        </span>
                      )}
                    </div>
                    <button
                      className="badge badge-neutral"
                      style={{ border: "none", cursor: "pointer" }}
                      disabled={saving}
                      onClick={() => handleAssign(intern.person_id, null)}
                    >
                      Unassign
                    </button>
                  </div>
                ))
              )}
            </div>
          ))
        )}

        <div className="glass-panel">
          <div className="glass-header"><h3>Unassigned Interns</h3></div>
          {unassigned.length === 0 ? (
            <p className="text-muted">Every active intern has a team lead assigned.</p>
          ) : (
            unassigned.map((intern) => (
              <div key={intern.person_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
                <div>
                  <Link to={`/ui/people/${intern.person_id}`} style={{ color: "var(--color-primary)", fontWeight: 600 }}>
                    {intern.full_name}
                  </Link>
                  {intern.intern_track && (
                    <span style={{ display: "block", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
                      {intern.intern_track}
                    </span>
                  )}
                </div>
                <Select
                  style={{ width: "160px" }}
                  value=""
                  disabled={saving || teamLeads.length === 0}
                  onChange={(e) => e.target.value && handleAssign(intern.person_id, e.target.value)}
                >
                  <option value="">Assign to...</option>
                  {teamLeads.filter((l) => l.person_id).map((l) => (
                    <option key={l.person_id} value={l.person_id}>{l.full_name}</option>
                  ))}
                </Select>
              </div>
            ))
          )}
        </div>
      </div>
    </motion.div>
  );
}
