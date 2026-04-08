import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../utils/api";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import { motion } from "framer-motion";
import { User, Briefcase, MessagesSquare, Clock, Key, CheckSquare, FileText, History, ArrowLeft, MoreSubtitles } from 'lucide-react';
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
      salary_amount: emp.salary_amount !== null ? emp.salary_amount : "",
      currency: emp.currency || "USD",
      contract_signed_date: emp.contract_signed_date || "",
      payment_status: emp.payment_status || "pending",
      amount_paid: emp.amount_paid !== null ? emp.amount_paid : "",
      amount_outstanding: emp.amount_outstanding !== null ? emp.amount_outstanding : "",
      payment_due_date: emp.payment_due_date || "",
      payment_frequency: emp.payment_frequency || "",
      manager_person_id: emp.manager_person_id || "",
      mentor_person_id: emp.mentor_person_id || "",
      notes: emp.notes || "",
    });
  }, []);

  const fetchAll = useCallback(async () => {
    const [personRes, checkinsRes, accessRes, logsRes, metadataRes] = await Promise.all([
      api.get(`/admin/people/${id}`),
      api.get(`/admin/people/${id}/checkins`),
      api.get(`/admin/people/${id}/access-assignments`),
      api.get(`/admin/audit-logs?target_type=person&target_id=${id}&page_size=20`),
      api.get("/admin/people/metadata"),
    ]);
    const payload = personRes.data.person;
    setPerson(payload);
    setEmploymentHistory(personRes.data.employment_history || []);
    setCheckins(checkinsRes.data.items || []);
    setAccessAssignments(accessRes.data.items || []);
    setAuditLogs(logsRes.data.items || []);
    setMetadata(metadataRes.data || {});
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
      await api.patch(`/admin/people/${id}`, profileForm);
      toast.success("Profile updated");
      await refresh();
    } catch (err) { toast.error(err.message || "Update failed"); } finally { setSaving(false); }
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

          {(activeEmployment || true) && (
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
          )}
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
             {onboardingItems.length === 0 ? <p className="text-muted">No items.</p> : onboardingItems.map((item) => (
               <div key={item.template_item_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)' }}>
                 <span>{item.title}</span>
                 {item.checked ? <span className="badge badge-success">Done</span> : <span className="badge badge-neutral">Pending</span>}
               </div>
             ))}
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
              <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                {checkins.length === 0 ? <p className="text-muted">No check-ins.</p> : checkins.map(c => (
                  <div key={c.id} style={{ padding: '0.75rem', background: 'var(--color-bg-tertiary)', borderRadius: 'var(--radius-md)', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                      <strong style={{ color: 'var(--color-text-primary)' }}>{c.summary}</strong>
                      <small className="text-muted">{new Date(c.created_at).toLocaleDateString()}</small>
                    </div>
                    <p style={{ margin: 0, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>{c.notes || "-"}</p>
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
                      <span style={{ color: 'var(--color-text-secondary)' }}>{new Date(log.created_at).toLocaleDateString()}:</span> {log.action}
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
