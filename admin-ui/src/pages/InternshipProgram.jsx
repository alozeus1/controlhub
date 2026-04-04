import { useCallback, useEffect, useMemo, useState } from "react";
import api from "../utils/api";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import { motion } from "framer-motion";
import { Calendar, Users, ListChecks, CheckCircle, PlayCircle, Plus } from 'lucide-react';
import "./InternshipProgram.css";

const EMPTY_PROGRAM_FORM = { name: "", description: "", start_date: "", end_date: "", status: "planned" };
const EMPTY_COHORT_FORM = { program_id: "", name: "", track: "", status: "active", start_date: "", end_date: "" };
const EMPTY_MEMBER_FORM = { cohort_id: "", person_id: "", role: "intern" };
const EMPTY_TEMPLATE_FORM = { title: "", description: "", is_active: true };

export default function InternshipProgram() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [metadata, setMetadata] = useState({ program_statuses: [], cohort_statuses: [], cohort_member_roles: [] });
  const [programs, setPrograms] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [internCandidates, setInternCandidates] = useState([]);

  const [selectedCohortId, setSelectedCohortId] = useState("");
  const [members, setMembers] = useState([]);

  const [programForm, setProgramForm] = useState(EMPTY_PROGRAM_FORM);
  const [cohortForm, setCohortForm] = useState(EMPTY_COHORT_FORM);
  const [memberForm, setMemberForm] = useState(EMPTY_MEMBER_FORM);
  const [templateForm, setTemplateForm] = useState(EMPTY_TEMPLATE_FORM);

  const selectedCohort = useMemo(() => cohorts.find(item => String(item.id) === String(selectedCohortId)), [cohorts, selectedCohortId]);

  const loadBaseData = useCallback(async () => {
    const [metaRes, programsRes, cohortsRes, templatesRes, peopleRes] = await Promise.all([
      api.get("/admin/internship/metadata"),
      api.get("/admin/internship/programs?page=1&page_size=100"),
      api.get("/admin/internship/cohorts?page=1&page_size=100"),
      api.get("/admin/internship/onboarding/templates"),
      api.get("/admin/people?employment_type=intern&page=1&page_size=200"),
    ]);

    setMetadata(metaRes.data || {});
    setPrograms(programsRes.data.items || []);
    setCohorts(cohortsRes.data.items || []);
    setTemplates(templatesRes.data.items || []);
    setInternCandidates(peopleRes.data.items || []);

    if (!selectedCohortId && (cohortsRes.data.items || []).length > 0) {
      const first = cohortsRes.data.items[0];
      setSelectedCohortId(String(first.id));
      setMemberForm(prev => ({ ...prev, cohort_id: String(first.id) }));
    }
  }, [selectedCohortId]);

  const loadMembers = useCallback(async (cohortId) => {
    if (!cohortId) return setMembers([]);
    const res = await api.get(`/admin/internship/cohorts/${cohortId}/members`);
    setMembers(res.data.items || []);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await loadBaseData();
      } catch (err) {
        toast.error(err.message || "Failed to load internship program page");
      } finally { setLoading(false); }
    })();
  }, [loadBaseData, toast]);

  useEffect(() => {
    loadMembers(selectedCohortId).catch(err => toast.error(err.message));
  }, [loadMembers, selectedCohortId, toast]);

  const refresh = async () => { await loadBaseData(); await loadMembers(selectedCohortId); };

  const createProgram = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/programs", programForm);
      toast.success("Program created");
      setProgramForm(EMPTY_PROGRAM_FORM);
      await refresh();
    } catch (err) { toast.error(err.message || "Failed to create program"); } finally { setSaving(false); }
  };

  const createCohort = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/cohorts", { ...cohortForm, program_id: Number(cohortForm.program_id) });
      toast.success("Cohort created");
      setCohortForm(EMPTY_COHORT_FORM);
      await refresh();
    } catch (err) { toast.error(err.message || "Failed to create cohort"); } finally { setSaving(false); }
  };

  const addMember = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/internship/cohorts/${memberForm.cohort_id}/members`, { person_id: Number(memberForm.person_id), role: memberForm.role });
      toast.success("Member added");
      await loadMembers(memberForm.cohort_id);
    } catch (err) { toast.error(err.message || "Failed to add member"); } finally { setSaving(false); }
  };

  const removeMember = async (member) => {
    try {
      setSaving(true);
      await api.delete(`/admin/internship/cohorts/${member.cohort_id}/members/${member.id}`);
      toast.success("Member removed");
      await loadMembers(member.cohort_id);
    } catch (err) { toast.error(err.message || "Failed to remove member"); } finally { setSaving(false); }
  };

  const createTemplate = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/onboarding/templates", templateForm);
      toast.success("Template item created");
      setTemplateForm(EMPTY_TEMPLATE_FORM);
      await refresh();
    } catch (err) { toast.error(err.message || "Failed to create item"); } finally { setSaving(false); }
  };

  const toggleTemplate = async (item) => {
    try {
      setSaving(true);
      await api.patch(`/admin/internship/onboarding/templates/${item.id}`, { is_active: !item.is_active });
      toast.success("Template updated");
      await refresh();
    } catch (err) { toast.error(err.message || "Failed to update item"); } finally { setSaving(false); }
  };

  if (loading) return <PageLoader message="Loading academy module..." />;

  // Quick stats calculations
  const activeCohorts = cohorts.filter(c => c.status === 'active').length;
  const plannedPrograms = programs.filter(p => p.status === 'planned').length;

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="internship-page">
      <div className="page-header" style={{ marginBottom: '2rem' }}>
        <div>
          <h1 className="page-title text-gradient">Academy & Internship Hub</h1>
          <p className="page-subtitle">Shape the next generation of talent through programs and connected cohorts.</p>
        </div>
        <div className="page-header-actions">
          <Button variant="secondary" onClick={refresh}>↻ Sync Data</Button>
        </div>
      </div>

      {/* KPI Widgets */}
      <div className="grid grid-3" style={{ marginBottom: '2rem' }}>
         <div className="glass-panel">
            <div className="glass-header"><h3><Calendar size={18} color="#2ad2ff"/> Active Programs</h3></div>
            <div className="metric-value">{programs.length}</div>
            <div className="metric-label">{plannedPrograms} planned for future</div>
         </div>
         <div className="glass-panel">
            <div className="glass-header"><h3><PlayCircle size={18} color="#24c783"/> Running Cohorts</h3></div>
            <div className="metric-value">{activeCohorts}</div>
            <div className="metric-label">Across all active tracks</div>
         </div>
         <div className="glass-panel">
            <div className="glass-header"><h3><ListChecks size={18} color="#ffb549"/> Active Requirements</h3></div>
            <div className="metric-value">{templates.filter(t => t.is_active).length}</div>
            <div className="metric-label">Global onboarding templates</div>
         </div>
      </div>

      <div className="internship-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
        <div className="glass-panel">
          <div className="glass-header">
             <h3>Programs Definition</h3>
          </div>
          <div style={{ padding: '0.5rem 0', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="internship-form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <Input placeholder="Program Name" value={programForm.name} onChange={(e) => setProgramForm((prev) => ({ ...prev, name: e.target.value }))} />
              <Select value={programForm.status} onChange={(e) => setProgramForm((prev) => ({ ...prev, status: e.target.value }))}>
                {metadata.program_statuses.map((status) => <option key={status} value={status}>{status}</option>)}
              </Select>
              <Input type="date" value={programForm.start_date} onChange={(e) => setProgramForm((prev) => ({ ...prev, start_date: e.target.value }))} />
              <Input type="date" value={programForm.end_date} onChange={(e) => setProgramForm((prev) => ({ ...prev, end_date: e.target.value }))} />
            </div>
            <TextArea placeholder="Short Description..." rows={2} value={programForm.description} onChange={(e) => setProgramForm((prev) => ({ ...prev, description: e.target.value }))} />
            <button className="btn-primary" disabled={saving} onClick={createProgram}><Plus size={16}/> Draft Program</button>
          </div>

          <div className="table-responsive" style={{ marginTop: '1.5rem' }}>
            <table>
              <thead>
                <tr>
                  <th>Identity</th>
                  <th>Dates</th>
                </tr>
              </thead>
              <tbody>
                {programs.map((program) => (
                  <tr key={program.id}>
                    <td>
                      <strong style={{ display: 'block', color: 'var(--color-text-primary)' }}>{program.name}</strong>
                      <span className={`badge ${program.status === 'active' ? 'badge-success' : 'badge-neutral'}`}>{program.status}</span>
                    </td>
                    <td className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>
                      {program.start_date || "-"} <br/> to {program.end_date || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass-panel">
          <div className="glass-header">
            <h3>Active Cohorts</h3>
          </div>
          <div style={{ padding: '0.5rem 0', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="internship-form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <Select value={cohortForm.program_id} onChange={(e) => setCohortForm((prev) => ({ ...prev, program_id: e.target.value }))}>
                <option value="">Link to Program</option>
                {programs.map((program) => <option key={program.id} value={program.id}>{program.name}</option>)}
              </Select>
              <Input placeholder="Cohort Identifier" value={cohortForm.name} onChange={(e) => setCohortForm((prev) => ({ ...prev, name: e.target.value }))} />
              <Input placeholder="Engineering, Design..." value={cohortForm.track} onChange={(e) => setCohortForm((prev) => ({ ...prev, track: e.target.value }))} />
              <Select value={cohortForm.status} onChange={(e) => setCohortForm((prev) => ({ ...prev, status: e.target.value }))}>
                {metadata.cohort_statuses.map((status) => <option key={status} value={status}>{status}</option>)}
              </Select>
              <Input type="date" value={cohortForm.start_date} onChange={(e) => setCohortForm((prev) => ({ ...prev, start_date: e.target.value }))} />
              <Input type="date" value={cohortForm.end_date} onChange={(e) => setCohortForm((prev) => ({ ...prev, end_date: e.target.value }))} />
            </div>
            <button className="btn-primary" disabled={saving} onClick={createCohort}><Plus size={16}/> Initialize Cohort</button>
          </div>

          <div className="table-responsive" style={{ marginTop: '1.5rem' }}>
            <table>
              <thead>
                <tr>
                  <th>Cohort</th>
                  <th>Track & Status</th>
                </tr>
              </thead>
              <tbody>
                {cohorts.map((cohort) => (
                  <tr key={cohort.id} style={{ cursor: 'pointer', background: String(selectedCohortId) === String(cohort.id) ? 'var(--color-bg-tertiary)' : 'transparent' }} onClick={() => {
                    setSelectedCohortId(String(cohort.id));
                    setMemberForm((prev) => ({ ...prev, cohort_id: String(cohort.id) }));
                  }}>
                    <td>
                      <strong style={{ display: 'block', color: 'var(--color-primary)' }}>{cohort.name}</strong>
                      <span className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>{cohort.program_name || "-"}</span>
                    </td>
                    <td>
                      <div style={{ fontSize: 'var(--font-size-sm)', marginBottom: '0.25rem' }}>{cohort.track}</div>
                      <span className={`badge ${cohort.status === 'active' ? 'badge-success' : 'badge-neutral'}`}>{cohort.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="internship-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        <div className="glass-panel">
          <div className="glass-header">
            <h3><Users size={18}/> Cohort Roster {selectedCohort ? `(${selectedCohort.name})` : ''}</h3>
          </div>
          <div style={{ padding: '0.5rem 0', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
              <Select value={memberForm.cohort_id} onChange={(e) => {
                setMemberForm((prev) => ({ ...prev, cohort_id: e.target.value }));
                setSelectedCohortId(e.target.value);
              }}>
                <option value="">Select Cohort</option>
                {cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}
              </Select>
              <Select value={memberForm.person_id} onChange={(e) => setMemberForm((prev) => ({ ...prev, person_id: e.target.value }))}>
                <option value="">Select Candidate...</option>
                {internCandidates.map((person) => <option key={person.id} value={person.id}>{person.full_name}</option>)}
              </Select>
              <Select value={memberForm.role} onChange={(e) => setMemberForm((prev) => ({ ...prev, role: e.target.value }))}>
                {metadata.cohort_member_roles.map((role) => <option key={role} value={role}>{role}</option>)}
              </Select>
            </div>
            <button className="btn-primary" disabled={saving || !memberForm.cohort_id || !memberForm.person_id} onClick={addMember}><Plus size={16}/> Enlist Member</button>
          </div>

          <div className="table-responsive" style={{ marginTop: '1.5rem' }}>
            <table>
              <thead>
                <tr>
                  <th>Identity</th>
                  <th>Role</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {members.length === 0 ? <tr><td colSpan={3} className="text-muted" style={{ textAlign: 'center', padding: '1rem' }}>Empty Roster.</td></tr> : members.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <strong style={{ display: 'block', color: 'var(--color-text-primary)' }}>{member.person_name}</strong>
                      <span className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>{member.person_email}</span>
                    </td>
                    <td>{member.role}</td>
                    <td><button className="btn-glass-danger" disabled={saving} onClick={() => removeMember(member)}>Evict</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass-panel">
          <div className="glass-header">
             <h3><CheckCircle size={18}/> Onboarding Templates</h3>
          </div>
          <div style={{ padding: '0.5rem 0', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '0.75rem' }}>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <Input placeholder="Template Title" value={templateForm.title} onChange={(e) => setTemplateForm((prev) => ({ ...prev, title: e.target.value }))} />
                <Select value={templateForm.is_active ? "true" : "false"} onChange={(e) => setTemplateForm((prev) => ({ ...prev, is_active: e.target.value === "true" }))}>
                  <option value="true">Active</option>
                  <option value="false">Inactive</option>
                </Select>
              </div>
              <TextArea placeholder="Requirements Description..." rows={2} value={templateForm.description} onChange={(e) => setTemplateForm((prev) => ({ ...prev, description: e.target.value }))} />
            </div>
            <button className="btn-primary" disabled={saving} onClick={createTemplate}><Plus size={16}/> Record Template</button>
          </div>

          <div className="template-list" style={{ marginTop: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {templates.map((template) => (
              <div key={template.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'var(--color-bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                <div>
                  <strong style={{ display: 'block', color: 'var(--color-text-primary)' }}>{template.title}</strong>
                  <span className="text-muted" style={{ fontSize: 'var(--font-size-sm)' }}>{template.description || "No description"}</span>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <span className={`badge ${template.is_active ? 'badge-success' : 'badge-neutral'}`}>{template.is_active ? 'Active' : 'Archived'}</span>
                  <button className="btn-glass" onClick={() => toggleTemplate(template)}>{template.is_active ? 'Disable' : 'Enable'}</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
