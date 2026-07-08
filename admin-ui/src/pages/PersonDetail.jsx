import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../utils/api";
import { formatDate } from "../utils/datetime";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import { motion } from "framer-motion";
import { User, Briefcase, MessagesSquare, Clock, Key, CheckSquare, FileText, History, ArrowLeft } from 'lucide-react';
import "./PersonDetail.css";

const EMPTY_CHECKIN = { summary: "", notes: "" };

export default function PersonDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [person, setPerson] = useState(null);
  const [employmentHistory, setEmploymentHistory] = useState([]);
  const [checkins, setCheckins] = useState([]);
  const [accessAssignments, setAccessAssignments] = useState([]);
  const [onboardingItems, setOnboardingItems] = useState([]);
  const [onboardingProgress, setOnboardingProgress] = useState({ done: 0, total: 0, progress_percent: 0 });
  const [completionChecklist, setCompletionChecklist] = useState({
    project_submitted: false,
    evaluation_done: false,
    admin_validated: false,
  });
  const [certificates, setCertificates] = useState([]);
  const [certificateForm, setCertificateForm] = useState({ pdf_url: "" });
  const [auditLogs, setAuditLogs] = useState([]);
  const [metadata, setMetadata] = useState({ employment_types: [], employment_statuses: [], intern_tracks: [], managers: [] });
  const [saving, setSaving] = useState(false);
  const [showTerminateConfirm, setShowTerminateConfirm] = useState(false);
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [checkinForm, setCheckinForm] = useState(EMPTY_CHECKIN);
  const [convertForm, setConvertForm] = useState({ title: "", start_date: "", notes: "" });

  const activeEmployment = person?.active_employment || null;
  const [profileForm, setProfileForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
    team: "",
    department: "",
    cohort: "",
    is_active: true,
    taiga_username: "",
    mattermost_username: "",
    assigned_projects: "",
    signed_documents: "",
    risk_flags: "",
    growth_summary: "",
  });
  const [employmentForm, setEmploymentForm] = useState({
    employment_type: "full_time",
    intern_track: "",
    status: "active",
    title: "",
    start_date: "",
    end_date: "",
    compensation_type: "",
    salary_amount: "",
    currency: "USD",
    contract_signed_date: "",
    payment_status: "pending",
    amount_paid: "",
    amount_outstanding: "",
    payment_due_date: "",
    payment_frequency: "",
    manager_person_id: "",
    mentor_person_id: "",
    notes: "",
  });

  const [biweeklyReviews, setBiweeklyReviews] = useState([]);
  const [milestoneReviews, setMilestoneReviews] = useState([]);
  const [showBiweeklyModal, setShowBiweeklyModal] = useState(false);
  const [biweeklyForm, setBiweeklyForm] = useState({ period_start: "", period_end: "" });
  const [selectedBiweekly, setSelectedBiweekly] = useState(null);
  const [internResponses, setInternResponses] = useState({});
  const [managerGradeForm, setManagerGradeForm] = useState({ score_progress: 5, blockers: "", strengths: "", action_items: "", notes: "" });
  const [showMilestoneModal, setShowMilestoneModal] = useState(false);
  const [milestoneForm, setMilestoneForm] = useState({ review_type: "3_month" });
  const [selectedMilestone, setSelectedMilestone] = useState(null);

  const hydrateForms = useCallback((personPayload) => {
    setProfileForm({
      first_name: personPayload.first_name || "",
      last_name: personPayload.last_name || "",
      email: personPayload.email || "",
      phone: personPayload.phone || "",
      team: personPayload.team || "",
      department: personPayload.department || "",
      cohort: personPayload.cohort || "",
      is_active: !!personPayload.is_active,
      taiga_username: personPayload.taiga_username || "",
      mattermost_username: personPayload.mattermost_username || "",
      assigned_projects: Array.isArray(personPayload.assigned_projects) ? personPayload.assigned_projects.join(", ") : "",
      signed_documents: typeof personPayload.signed_documents === "object" ? JSON.stringify(personPayload.signed_documents) : "",
      risk_flags: Array.isArray(personPayload.risk_flags) ? personPayload.risk_flags.join(", ") : "",
      growth_summary: personPayload.growth_summary || "",
    });
    const emp = personPayload.active_employment || {};
    setEmploymentForm({
      employment_type: emp.employment_type || "full_time",
      intern_track: emp.intern_track || "",
      status: emp.status || "active",
      title: emp.title || "",
      start_date: emp.start_date || "",
      end_date: emp.end_date || "",
      compensation_type: emp.compensation_type || "",
      salary_amount: emp.salary_amount ?? "",
      currency: emp.currency || "USD",
      contract_signed_date: emp.contract_signed_date || "",
      payment_status: emp.payment_status || "pending",
      amount_paid: emp.amount_paid ?? "",
      amount_outstanding: emp.amount_outstanding ?? "",
      payment_due_date: emp.payment_due_date || "",
      payment_frequency: emp.payment_frequency || "",
      manager_person_id: emp.manager_person_id || "",
      mentor_person_id: emp.mentor_person_id || "",
      notes: emp.notes || "",
    });
  }, []);

  const fetchAll = useCallback(async () => {
    const [personRes, checkinsRes, accessRes, logsRes, metadataRes, biweeklyRes, milestoneRes] = await Promise.all([
      api.get(`/admin/people/${id}`),
      api.get(`/admin/people/${id}/checkins`),
      api.get(`/admin/people/${id}/access-assignments`),
      api.get(`/admin/audit-logs?target_type=person&target_id=${id}&page_size=20`),
      api.get("/admin/people/metadata"),
      api.get(`/admin/internship/reviews/biweekly?person_id=${id}`).catch(() => ({ data: { items: [] } })),
      api.get(`/admin/internship/reviews/milestone?person_id=${id}`).catch(() => ({ data: { items: [] } })),
    ]);
    const payload = personRes.data.person;
    setPerson(payload);
    setEmploymentHistory(personRes.data.employment_history || []);
    setCheckins(checkinsRes.data.items || []);
    setAccessAssignments(accessRes.data.items || []);
    setAuditLogs(logsRes.data.items || []);
    setMetadata(metadataRes.data || {});
    setBiweeklyReviews(biweeklyRes.data.items || []);
    setMilestoneReviews(milestoneRes.data.items || []);
    hydrateForms(payload);

    const [onboardingRes, completionRes, certificatesRes] = await Promise.allSettled([
      api.get(`/admin/internship/people/${id}/onboarding`),
      api.get(`/admin/internship/people/${id}/completion`),
      api.get(`/admin/internship/people/${id}/certificates`),
    ]);

    if (onboardingRes.status === "fulfilled") {
      setOnboardingItems(onboardingRes.value.data.items || []);
      setOnboardingProgress({
        done: onboardingRes.value.data.done || 0,
        total: onboardingRes.value.data.total || 0,
        progress_percent: onboardingRes.value.data.progress_percent || 0,
      });
    }

    if (completionRes.status === "fulfilled") {
      setCompletionChecklist(completionRes.value.data.checklist || { project_submitted: false, evaluation_done: false, admin_validated: false });
    }

    if (certificatesRes.status === "fulfilled") {
      setCertificates(certificatesRes.value.data.items || []);
    }
  }, [hydrateForms, id]);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await fetchAll();
      } catch (err) {
        toast.error(err.message || "Failed to load person details");
        navigate("/ui/people");
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchAll, navigate, toast]);

  const refresh = async () => await fetchAll();

  const handleSaveProfile = async () => {
    try {
      setSaving(true);
      const parsedAssignedProjects = profileForm.assigned_projects
        ? profileForm.assigned_projects.split(",").map(p => p.trim()).filter(Boolean)
        : [];
      const parsedRiskFlags = profileForm.risk_flags
        ? profileForm.risk_flags.split(",").map(r => r.trim()).filter(Boolean)
        : [];
      let parsedDocs = {};
      try {
        if (profileForm.signed_documents) {
          parsedDocs = JSON.parse(profileForm.signed_documents);
        }
      } catch {
        parsedDocs = { "NDA": profileForm.signed_documents };
      }
      
      const payload = {
        ...profileForm,
        assigned_projects: parsedAssignedProjects,
        risk_flags: parsedRiskFlags,
        signed_documents: parsedDocs,
      };
      await api.patch(`/admin/people/${id}`, payload);
      toast.success("Profile updated");
      await refresh();
    } catch (err) { toast.error(err.message || "Update failed"); } finally { setSaving(false); }
  };

  const handleInitializeOnboarding = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/internship/people/${id}/onboarding/initialize`);
      toast.success("Onboarding checklist initialized!");
      await refresh();
    } catch (err) { toast.error(err.message || "Initialization failed"); } finally { setSaving(false); }
  };

  const handleToggleOnboardingItem = async (itemId, currentChecked) => {
    try {
      setSaving(true);
      const nextChecked = !currentChecked;
      await api.patch(`/admin/internship/onboarding-item/${itemId}`, {
        checked: nextChecked,
        status: nextChecked ? "completed" : "pending"
      });
      toast.success("Item status updated");
      await refresh();
    } catch (err) { toast.error(err.message || "Toggle failed"); } finally { setSaving(false); }
  };

  const handleCreateBiweekly = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/reviews/biweekly", {
        person_id: Number(id),
        period_start: biweeklyForm.period_start,
        period_end: biweeklyForm.period_end
      });
      toast.success("Biweekly check-in period opened");
      setShowBiweeklyModal(false);
      await refresh();
    } catch (err) { toast.error(err.message || "Creation failed"); } finally { setSaving(false); }
  };

  const handleInternSubmitBiweekly = async (reviewId) => {
    try {
      setSaving(true);
      await api.post(`/admin/internship/reviews/biweekly/${reviewId}/intern-submit`, {
        responses: internResponses
      });
      toast.success("Self-reflection response submitted!");
      setSelectedBiweekly(null);
      await refresh();
    } catch (err) { toast.error(err.message || "Submission failed"); } finally { setSaving(false); }
  };

  const handleManagerGradeBiweekly = async (reviewId) => {
    try {
      setSaving(true);
      const actionItemsParsed = managerGradeForm.action_items
        ? managerGradeForm.action_items.split("\n").map(line => ({ task: line.trim(), due: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] })).filter(x => x.task)
        : [];
      await api.post(`/admin/internship/reviews/biweekly/${reviewId}/manager-submit`, {
        score_progress: Number(managerGradeForm.score_progress),
        blockers: managerGradeForm.blockers,
        strengths: managerGradeForm.strengths,
        action_items: actionItemsParsed,
        responses: { "manager_general_notes": managerGradeForm.notes || "Completed progress check-in." }
      });
      toast.success("Biweekly check-in graded and finalized!");
      setSelectedBiweekly(null);
      await refresh();
    } catch (err) { toast.error(err.message || "Grading failed"); } finally { setSaving(false); }
  };

  const handleCompileMilestone = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/reviews/milestone/compile", {
        person_id: Number(id),
        review_type: milestoneForm.review_type
      });
      toast.success("Milestone review compiled successfully!");
      setShowMilestoneModal(false);
      await refresh();
    } catch (err) { toast.error(err.message || "Compilation failed"); } finally { setSaving(false); }
  };

  const handleApproveAiMilestone = async (reviewId, approved = true) => {
    try {
      setSaving(true);
      await api.post(`/admin/internship/reviews/milestone/${reviewId}/approve-ai`, { approved });
      toast.success(approved ? "AI draft recommendation approved" : "Draft approval revoked");
      await refresh();
    } catch (err) { toast.error(err.message || "Approval update failed"); } finally { setSaving(false); }
  };

  const handleFinalizeMilestone = async (reviewId, decision) => {
    try {
      setSaving(true);
      const res = await api.post(`/admin/internship/reviews/milestone/${reviewId}/finalize`, {
        decision
      });
      if (res.data?.code === "APPROVAL_REQUIRED") {
        toast.info(res.data.message || "Approval required to finalize this decision");
      } else {
        toast.success(`Milestone finalized with decision: ${decision}`);
      }
      setSelectedMilestone(null);
      await refresh();
    } catch (err) { toast.error(err.message || "Finalization failed"); } finally { setSaving(false); }
  };

  const handleSaveEmployment = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/people/${id}/employment`, {
        ...employmentForm,
        manager_person_id: employmentForm.manager_person_id ? Number(employmentForm.manager_person_id) : null,
        mentor_person_id: employmentForm.mentor_person_id ? Number(employmentForm.mentor_person_id) : null,
      });
      toast.success("Employment updated");
      await refresh();
    } catch (err) { toast.error(err.message || "Update failed"); } finally { setSaving(false); }
  };

  const handleAddCheckin = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/people/${id}/checkins`, checkinForm);
      setCheckinForm(EMPTY_CHECKIN);
      toast.success("Check-in added");
      await refresh();
    } catch (err) { toast.error(err.message || "Add failed"); } finally { setSaving(false); }
  };

  const handleConvert = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/people/${id}/convert-to-full-time`, convertForm);
      toast.success("Intern converted to full-time");
      setShowConvertModal(false);
      await refresh();
    } catch (err) { toast.error(err.message || "Conversion failed"); } finally { setSaving(false); }
  };

  const handleTerminate = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/people/${id}/terminate`, {});
      toast.success("Person terminated");
      setShowTerminateConfirm(false);
      await refresh();
    } catch (err) { toast.error(err.message || "Termination failed"); } finally { setSaving(false); }
  };

  if (loading) return <PageLoader message="Loading person details..." />;

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="person-detail-page">
      <div className="page-header" style={{ marginBottom: '2rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <Link to="/ui/people" style={{ display: 'flex', alignItems: 'center', color: 'var(--color-primary)' }}><ArrowLeft size={16}/>&nbsp;Back to Portal</Link>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className="avatar-circle" style={{ width: '60px', height: '60px', fontSize: '1.5rem' }}>
              {person?.first_name?.[0]}{person?.last_name?.[0]}
            </div>
            <div>
              <h1 className="page-title">{person?.full_name}</h1>
              <p className="page-subtitle">{person?.email} • <span className="badge badge-success">{activeEmployment?.employment_type || "No active employment"}</span></p>
            </div>
          </div>
        </div>
        <div className="page-header-actions" style={{ display: 'flex', gap: '1rem' }}>
          {activeEmployment?.employment_type === "intern" && (
             <button className="btn-glass" onClick={() => setShowConvertModal(true)}>Convert to Full-time</button>
          )}
          <button className="btn-glass-danger" onClick={() => setShowTerminateConfirm(true)}>Terminate</button>
        </div>
      </div>

      <div className="grid grid-3">
        {/* Column 1: Identity & Status */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="glass-panel">
             <div className="glass-header"><h3><User size={18}/> Profile Identity</h3></div>
             <div className="person-form-grid" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <Input label="First Name" value={profileForm.first_name} onChange={(e) => setProfileForm((f) => ({ ...f, first_name: e.target.value }))} />
                <Input label="Last Name" value={profileForm.last_name} onChange={(e) => setProfileForm((f) => ({ ...f, last_name: e.target.value }))} />
                <Input label="Email" value={profileForm.email} onChange={(e) => setProfileForm((f) => ({ ...f, email: e.target.value }))} />
                <Input label="Phone" value={profileForm.phone} onChange={(e) => setProfileForm((f) => ({ ...f, phone: e.target.value }))} />
                <Select label="Active" value={profileForm.is_active ? "true" : "false"} onChange={(e) => setProfileForm((f) => ({ ...f, is_active: e.target.value === "true" }))}>
                  <option value="true">Active</option>
                  <option value="false">Inactive</option>
                </Select>
                <Input label="Taiga Username" value={profileForm.taiga_username} onChange={(e) => setProfileForm((f) => ({ ...f, taiga_username: e.target.value }))} />
                <Input label="Mattermost Username" value={profileForm.mattermost_username} onChange={(e) => setProfileForm((f) => ({ ...f, mattermost_username: e.target.value }))} />
                <Input label="Assigned Projects (comma-separated)" value={profileForm.assigned_projects} onChange={(e) => setProfileForm((f) => ({ ...f, assigned_projects: e.target.value }))} />
                <Input label="Signed Documents (JSON or comma-separated)" value={profileForm.signed_documents} onChange={(e) => setProfileForm((f) => ({ ...f, signed_documents: e.target.value }))} />
                <Input label="Risk Flags (comma-separated)" value={profileForm.risk_flags} onChange={(e) => setProfileForm((f) => ({ ...f, risk_flags: e.target.value }))} />
                <div>
                  <label className="input-label">Growth & Development Summary</label>
                  <TextArea rows={3} value={profileForm.growth_summary} onChange={(e) => setProfileForm((f) => ({ ...f, growth_summary: e.target.value }))} />
                </div>
                <Button variant="primary" loading={saving} onClick={handleSaveProfile} style={{ marginTop: '0.5rem' }}>Save Profile</Button>
             </div>
          </div>

          <div className="glass-panel">
            <div className="glass-header"><h3><Briefcase size={18}/> Current Employment</h3></div>
            <div className="person-form-grid" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
               <Select label="Type" value={employmentForm.employment_type} onChange={(e) => setEmploymentForm((f) => ({ ...f, employment_type: e.target.value }))}>
                  {metadata.employment_types.map((type) => <option key={type} value={type}>{type}</option>)}
               </Select>
               <Input label="Title" value={employmentForm.title} onChange={(e) => setEmploymentForm((f) => ({ ...f, title: e.target.value }))} />
               <Input label="Start Date" type="date" value={employmentForm.start_date || ""} onChange={(e) => setEmploymentForm((f) => ({ ...f, start_date: e.target.value }))} />
               <Select label="Manager" value={employmentForm.manager_person_id || ""} onChange={(e) => setEmploymentForm((f) => ({ ...f, manager_person_id: e.target.value }))}>
                 <option value="">Unassigned</option>
                 {(metadata.managers || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
               </Select>
               <Button variant="primary" loading={saving} onClick={handleSaveEmployment} style={{ marginTop: '0.5rem' }}>Save Employment</Button>
            </div>
          </div>

          <div className="glass-panel">
              <div className="glass-header"><h3><FileText size={18}/> Comp & Contracts</h3></div>
              <div className="person-form-grid" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                 <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                   <Select label="Comp Type" value={employmentForm.compensation_type} onChange={(e) => setEmploymentForm((f) => ({ ...f, compensation_type: e.target.value }))}>
                     <option value="">Unpaid</option>
                     <option value="salary">Salary</option>
                     <option value="stipend">Stipend</option>
                     <option value="hourly">Hourly</option>
                   </Select>
                   <Select label="Currency" value={employmentForm.currency} onChange={(e) => setEmploymentForm((f) => ({ ...f, currency: e.target.value }))}>
                     <option value="USD">USD ($)</option>
                     <option value="EUR">EUR (€)</option>
                     <option value="GBP">GBP (£)</option>
                   </Select>
                 </div>
                 <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                   <Input label="Amount" type="number" value={employmentForm.salary_amount} onChange={(e) => setEmploymentForm((f) => ({ ...f, salary_amount: e.target.value }))} />
                   <Select label="Frequency" value={employmentForm.payment_frequency} onChange={(e) => setEmploymentForm((f) => ({ ...f, payment_frequency: e.target.value }))}>
                     <option value="">N/A</option>
                     <option value="weekly">Weekly</option>
                     <option value="bi-weekly">Bi-weekly</option>
                     <option value="monthly">Monthly</option>
                   </Select>
                 </div>
                 <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                   <Input label="Contract Signed" type="date" value={employmentForm.contract_signed_date || ""} onChange={(e) => setEmploymentForm((f) => ({ ...f, contract_signed_date: e.target.value }))} />
                   <Select label="Payment Status" value={employmentForm.payment_status} onChange={(e) => setEmploymentForm((f) => ({ ...f, payment_status: e.target.value }))}>
                     <option value="pending">Pending</option>
                     <option value="cleared">Cleared</option>
                     <option value="overdue">Overdue</option>
                   </Select>
                 </div>
                 <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                   <Input label="Amount Paid" type="number" value={employmentForm.amount_paid} onChange={(e) => setEmploymentForm((f) => ({ ...f, amount_paid: e.target.value }))} />
                   <Input label="Outstanding" type="number" value={employmentForm.amount_outstanding} onChange={(e) => setEmploymentForm((f) => ({ ...f, amount_outstanding: e.target.value }))} />
                 </div>
                 <Button variant="primary" loading={saving} onClick={handleSaveEmployment} style={{ marginTop: '0.5rem' }}>Update Contracts</Button>
              </div>
          </div>
        </div>

        {/* Column 2: Progress & Performance Check-ins */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="glass-panel">
              <div className="glass-header"><h3><CheckSquare size={18}/> Onboarding Radar</h3></div>
              <div className="progress-inline" style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                <div style={{ flex: 1, background: 'var(--color-bg-tertiary)', height: '8px', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ width: `${onboardingProgress.progress_percent || 0}%`, background: 'var(--color-primary)', height: '100%' }} />
                </div>
                <span style={{ fontWeight: 'bold' }}>{onboardingProgress.progress_percent || 0}%</span>
              </div>
              {onboardingItems.length === 0 ? (
                <div style={{ textAlign: "center", padding: "1rem" }}>
                  <p className="text-muted" style={{ marginBottom: '1rem' }}>No onboarding checklist initialized.</p>
                  <button className="btn-primary" onClick={handleInitializeOnboarding} disabled={saving} style={{ width: '100%' }}>
                    Initialize Onboarding Checklist
                  </button>
                </div>
              ) : (
                onboardingItems.map((item) => (
                  <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)' }}>
                    <div>
                      <span style={{ textDecoration: item.checked ? 'line-through' : 'none', color: item.checked ? 'var(--color-text-secondary)' : 'var(--color-text-primary)', fontSize: 'var(--font-size-sm)' }}>
                        {item.title}
                      </span>
                      {(item.due_date || item.owner_role) && (
                        <span style={{ display: 'block', fontSize: 'var(--font-size-xs)', color: item.status === 'overdue' ? 'var(--color-danger)' : 'var(--color-text-muted)' }}>
                          {item.due_date ? `Due: ${item.due_date} ` : ''}{item.status === 'overdue' ? '(Overdue) ' : ''}{item.owner_role ? `• Owner: ${item.owner_role}` : ''}
                        </span>
                      )}
                    </div>
                    <button 
                      className={`badge ${item.checked ? 'badge-success' : 'badge-neutral'}`}
                      style={{ border: 'none', cursor: 'pointer' }}
                      onClick={() => handleToggleOnboardingItem(item.id, item.checked)}
                      disabled={saving}
                    >
                      {item.checked ? 'Done' : 'Pending'}
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="glass-panel">
               <div className="glass-header"><h3><MessagesSquare size={18}/> Performance Check-ins</h3></div>
               <div style={{ marginBottom: '1rem' }}>
                 <Input placeholder="Check-in Summary" value={checkinForm.summary} onChange={(e) => setCheckinForm((f) => ({ ...f, summary: e.target.value }))} />
                 <div style={{ marginTop: '0.5rem' }}>
                    <TextArea placeholder="Detailed notes..." rows={2} value={checkinForm.notes} onChange={(e) => setCheckinForm((f) => ({ ...f, notes: e.target.value }))} />
                 </div>
                 <button className="btn-glass" onClick={handleAddCheckin} style={{ marginTop: '0.5rem', width: '100%', justifyContent: 'center' }}>+ Add Log</button>
               </div>
               <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                 {checkins.length === 0 ? <p className="text-muted">No check-ins.</p> : checkins.map(c => (
                   <div key={c.id} style={{ padding: '0.75rem', background: 'var(--color-bg-tertiary)', borderRadius: 'var(--radius-md)', marginBottom: '0.5rem' }}>
                     <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                       <strong style={{ color: 'var(--color-text-primary)' }}>{c.summary}</strong>
                       <small className="text-muted">{formatDate(c.created_at)}</small>
                     </div>
                     <p style={{ margin: 0, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>{c.notes || "-"}</p>
                   </div>
                 ))}
               </div>
            </div>

            {/* SaaS Biweekly Reviews Card */}
            <div className="glass-panel">
              <div className="glass-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3>📅 Biweekly Reviews</h3>
                <button className="btn-glass" style={{ fontSize: 'var(--font-size-xs)', padding: '0.25rem 0.5rem' }} onClick={() => setShowBiweeklyModal(true)}>
                  + Open Period
                </button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
                {biweeklyReviews.length === 0 ? <p className="text-muted">No biweekly reviews created.</p> : biweeklyReviews.map(rev => (
                  <div key={rev.id} style={{ padding: '0.75rem', background: 'var(--color-bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <strong style={{ fontSize: 'var(--font-size-sm)' }}>
                        {rev.period_start} to {rev.period_end}
                      </strong>
                      <span className={`badge ${rev.status === 'completed' ? 'badge-success' : 'badge-neutral'}`}>
                        {rev.status}
                      </span>
                    </div>
                    {rev.score_progress && (
                      <div style={{ fontSize: 'var(--font-size-sm)', marginBottom: '0.25rem' }}>
                        Progress Score: <strong style={{ color: 'var(--color-primary)' }}>{rev.score_progress}/5</strong>
                      </div>
                    )}
                    {rev.ai_summary && (
                      <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)', fontStyle: 'italic', margin: '0.25rem 0' }}>
                        {rev.ai_summary}
                      </p>
                    )}

                    {rev.status === 'pending_intern' && (
                      <button className="btn-primary" style={{ width: '100%', marginTop: '0.5rem', fontSize: 'var(--font-size-xs)' }} onClick={() => setSelectedBiweekly(rev)}>
                        Submit Intern Reflection
                      </button>
                    )}
                    {rev.status === 'pending_manager' && (
                      <button className="btn-glass" style={{ width: '100%', marginTop: '0.5rem', fontSize: 'var(--font-size-xs)' }} onClick={() => setSelectedBiweekly(rev)}>
                        Grade & Complete Review
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* SaaS Milestone Reviews Card */}
            <div className="glass-panel">
              <div className="glass-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3>🏆 Milestone Scorecards</h3>
                <button className="btn-glass" style={{ fontSize: 'var(--font-size-xs)', padding: '0.25rem 0.5rem' }} onClick={() => setShowMilestoneModal(true)}>
                  Compile Scorecard
                </button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
                {milestoneReviews.length === 0 ? <p className="text-muted">No milestones compiled.</p> : milestoneReviews.map(m => (
                  <div key={m.id} style={{ padding: '0.75rem', background: 'var(--color-bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <strong style={{ textTransform: 'capitalize' }}>{m.review_type.replace('_', ' ')} Review</strong>
                      <span className={`badge ${m.status === 'released' ? 'badge-success' : 'badge-neutral'}`}>
                        {m.status}
                      </span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: 'var(--font-size-sm)', marginBottom: '0.5rem' }}>
                      <div>Avg Score: <strong>{m.compiled_score}/5</strong></div>
                      <div>Onboarding: <strong>{m.onboarding_progress}%</strong></div>
                    </div>
                    
                    {m.taiga_activity_summary && (
                      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)', marginBottom: '0.5rem' }}>
                        Taiga Ticket Count: <strong>{m.taiga_activity_summary.completed_tasks || 0}</strong> | Participation Score: <strong>{m.taiga_activity_summary.participation_score || 0}%</strong>
                      </div>
                    )}

                    {m.ai_recommendations && (
                      <div style={{ background: 'var(--color-bg-primary)', padding: '0.5rem', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--color-primary)', marginBottom: '0.5rem' }}>
                        <div style={{ fontSize: 'var(--font-size-xs)', fontWeight: 'bold', color: 'var(--color-text-primary)' }}>AI Recommendation:</div>
                        <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)', margin: 0 }}>{m.ai_recommendations}</p>
                        {!m.ai_recommendations_approved && m.status === 'draft' && (
                          <button className="btn-glass" style={{ fontSize: '10px', padding: '2px 6px', marginTop: '4px' }} onClick={() => handleApproveAiMilestone(m.id, true)}>
                            Approve Draft Recommendation
                          </button>
                        )}
                        {m.ai_recommendations_approved && m.status === 'draft' && (
                          <button className="btn-glass" style={{ fontSize: '10px', padding: '2px 6px', marginTop: '4px' }} onClick={() => handleApproveAiMilestone(m.id, false)}>
                            Revoke Approval
                          </button>
                        )}
                      </div>
                    )}

                    {m.report_card_json?.competencies && Object.keys(m.report_card_json.competencies).length > 0 && (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.25rem 0.75rem', fontSize: 'var(--font-size-xs)', color: 'var(--color-text-secondary)', marginBottom: '0.5rem' }}>
                        {Object.entries(m.report_card_json.competencies).map(([name, score]) => (
                          <div key={name} style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ textTransform: 'capitalize' }}>{name.replace(/_/g, ' ')}</span>
                            <strong style={{ color: 'var(--color-text-primary)' }}>{score}</strong>
                          </div>
                        ))}
                      </div>
                    )}

                    {m.status === 'draft' && (
                      <>
                        {!m.ai_recommendations_approved && (
                          <p className="text-muted" style={{ fontSize: 'var(--font-size-xs)', margin: '0.25rem 0' }}>
                            Review and approve the draft recommendation to unlock decisions.
                          </p>
                        )}
                        <div style={{ display: 'flex', gap: '0.25rem', marginTop: '0.5rem' }}>
                          <button className="btn-primary" style={{ flex: 1, fontSize: '10px', padding: '4px' }} onClick={() => handleFinalizeMilestone(m.id, 'convert')} disabled={!m.ai_recommendations_approved}>
                            Convert
                          </button>
                          <button className="btn-glass" style={{ flex: 1, fontSize: '10px', padding: '4px' }} onClick={() => handleFinalizeMilestone(m.id, 'extend')} disabled={!m.ai_recommendations_approved}>
                            Extend
                          </button>
                          <button className="btn-glass-danger" style={{ flex: 1, fontSize: '10px', padding: '4px' }} onClick={() => handleFinalizeMilestone(m.id, 'release')} disabled={!m.ai_recommendations_approved}>
                            Release
                          </button>
                        </div>
                      </>
                    )}
                    {m.status === 'released' && m.final_decision && (
                      <div style={{ fontSize: 'var(--font-size-sm)', marginTop: '0.5rem', fontWeight: 'bold' }}>
                        Final Decision: <span className="text-gradient" style={{ textTransform: 'uppercase' }}>{m.final_decision}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
         </div>

        {/* Column 3: HR + IT Assets & Audit */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
           <div className="glass-panel">
             <div className="glass-header"><h3><Key size={18}/> Access & Assets</h3></div>
             {accessAssignments.length === 0 ? <p className="text-muted">No system access provisioned</p> : accessAssignments.map((entry) => (
                <div key={entry.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)' }}>
                  <div>
                    <strong style={{ display: 'block', color: 'var(--color-text-primary)' }}>{entry.system_name}</strong>
                    <span style={{ fontSize: 'var(--font-size-sm)' }}>{entry.access_level}</span>
                  </div>
                  <span className={`badge ${entry.status === 'active' ? 'badge-success' : 'badge-neutral'}`}>{entry.status}</span>
                </div>
              ))}
           </div>

           <div className="glass-panel">
             <div className="glass-header"><h3><Clock size={18}/> Timeline</h3></div>
             <div className="history-list" style={{ maxHeight: '400px', overflowY: 'auto' }}>
               {employmentHistory.length === 0 ? <p className="text-muted">No history.</p> : employmentHistory.map((emp) => (
                 <div key={emp.id} style={{ position: 'relative', paddingLeft: '1.5rem', marginBottom: '1rem', borderLeft: '2px solid var(--color-primary-alpha)' }}>
                   <div style={{ position: 'absolute', left: '-5px', top: '0', width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-primary)' }}></div>
                   <strong style={{ display: 'block', color: 'var(--color-text-primary)' }}>{emp.employment_type}</strong>
                   <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
                     {emp.start_date || "?"} to {emp.end_date || "Present"}
                   </span>
                 </div>
               ))}
               <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                 <h4 className="text-muted" style={{ marginBottom: '0.5rem', fontSize: 'var(--font-size-sm)' }}>Recent Audits</h4>
                 {auditLogs.slice(0, 3).map((log) => (
                    <div key={log.id} style={{ fontSize: 'var(--font-size-sm)', marginBottom: '0.25rem' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>{formatDate(log.created_at)}:</span> {log.action}
                    </div>
                 ))}
               </div>
             </div>
           </div>
        </div>
      </div>

      <Modal isOpen={showConvertModal} onClose={() => setShowConvertModal(false)} title="Convert Intern to Full-time">
         <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
          <Input label="New Title" value={convertForm.title} onChange={(e) => setConvertForm((f) => ({ ...f, title: e.target.value }))} />
          <Input label="Start Date" type="date" value={convertForm.start_date} onChange={(e) => setConvertForm((f) => ({ ...f, start_date: e.target.value }))} />
          <Button variant="primary" loading={saving} onClick={handleConvert}>Convert Now</Button>
         </div>
      </Modal>

      <Modal isOpen={showBiweeklyModal} onClose={() => setShowBiweeklyModal(false)} title="Open Biweekly Performance Check-in">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
          <Input type="date" label="Period Start Date" value={biweeklyForm.period_start} onChange={(e) => setBiweeklyForm(f => ({ ...f, period_start: e.target.value }))} />
          <Input type="date" label="Period End Date" value={biweeklyForm.period_end} onChange={(e) => setBiweeklyForm(f => ({ ...f, period_end: e.target.value }))} />
          <Button variant="primary" loading={saving} disabled={!biweeklyForm.period_start || !biweeklyForm.period_end} onClick={handleCreateBiweekly}>Open Period</Button>
        </div>
      </Modal>

      <Modal isOpen={!!selectedBiweekly} onClose={() => setSelectedBiweekly(null)} title="Biweekly Performance Check-in Detail">
        {selectedBiweekly && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
            <div>Period: <strong>{selectedBiweekly.period_start} to {selectedBiweekly.period_end}</strong></div>
            <div>Status: <span className="badge badge-neutral" style={{ textTransform: 'uppercase' }}>{selectedBiweekly.status}</span></div>

            {selectedBiweekly.status === 'pending_intern' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <h4>Intern Self Reflection</h4>
                <TextArea 
                  label="Accomplishments & Learnings" 
                  rows={3} 
                  placeholder="What did you achieve in this period? Any learnings?" 
                  onChange={(e) => setInternResponses({ accomplishments: e.target.value })} 
                />
                <Button variant="primary" loading={saving} onClick={() => handleInternSubmitBiweekly(selectedBiweekly.id)}>
                  Submit Self Reflection
                </Button>
              </div>
            )}

            {selectedBiweekly.status === 'pending_manager' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <h4>Manager Progress Grading</h4>
                <div>
                  <label className="input-label">Intern Accomplishments Reflection:</label>
                  <p style={{ fontStyle: 'italic', color: 'var(--color-text-secondary)', background: 'var(--color-bg-tertiary)', padding: '0.5rem', borderRadius: 'var(--radius-sm)' }}>
                    {selectedBiweekly.intern_responses?.accomplishments || "No response submitted."}
                  </p>
                </div>
                <Select label="Progress Score" value={managerGradeForm.score_progress} onChange={(e) => setManagerGradeForm(f => ({ ...f, score_progress: e.target.value }))}>
                  <option value="5">5 - Excellent (Exceeding expectations)</option>
                  <option value="4">4 - High (Meeting expectations fully)</option>
                  <option value="3">3 - Satisfactory (Minor gaps)</option>
                  <option value="2">2 - Needs Improvement (Unresolved blockers)</option>
                  <option value="1">1 - Unsatisfactory (Significant concerns)</option>
                </Select>
                <Input label="Blockers identified" placeholder="None" value={managerGradeForm.blockers} onChange={(e) => setManagerGradeForm(f => ({ ...f, blockers: e.target.value }))} />
                <Input label="Strengths demonstrated" placeholder="Adaptability, velocity" value={managerGradeForm.strengths} onChange={(e) => setManagerGradeForm(f => ({ ...f, strengths: e.target.value }))} />
                <TextArea label="Action Items (one per line)" rows={2} placeholder="Review credentials config&#10;Complete security quiz" value={managerGradeForm.action_items} onChange={(e) => setManagerGradeForm(f => ({ ...f, action_items: e.target.value }))} />
                <TextArea label="General evaluation notes" rows={2} placeholder="Completed evaluation..." value={managerGradeForm.notes} onChange={(e) => setManagerGradeForm(f => ({ ...f, notes: e.target.value }))} />
                <Button variant="primary" loading={saving} onClick={() => handleManagerGradeBiweekly(selectedBiweekly.id)}>
                  Grade and Complete Review
                </Button>
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal isOpen={showMilestoneModal} onClose={() => setShowMilestoneModal(false)} title="Compile Milestone Performance Scorecard">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
          <Select label="Milestone Review Type" value={milestoneForm.review_type} onChange={(e) => setMilestoneForm(f => ({ ...f, review_type: e.target.value }))}>
            <option value="3_month">3-Month Midterm Evaluation</option>
            <option value="6_month">6-Month Final Evaluation</option>
          </Select>
          <p className="text-muted" style={{ fontSize: 'var(--font-size-xs)' }}>
            Compiles average biweekly checkin grades, onboarding checklist progress, and fetches mock integration activity indicators from Taiga & Mattermost.
          </p>
          <Button variant="primary" loading={saving} onClick={handleCompileMilestone}>Compile Scorecard</Button>
        </div>
      </Modal>

      <ConfirmModal
        isOpen={showTerminateConfirm}
        onClose={() => setShowTerminateConfirm(false)}
        onConfirm={handleTerminate}
        title="Terminate Employment"
        message="This action will offboard the employee and revoke active access. Ensure tasks are handed over."
        confirmText="Confirm Termination"
        variant="danger"
        loading={saving}
      />
    </motion.div>
  );
}
