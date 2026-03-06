import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
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
    } else {
      setOnboardingItems([]);
      setOnboardingProgress({ done: 0, total: 0, progress_percent: 0 });
    }

    if (completionRes.status === "fulfilled") {
      setCompletionChecklist(completionRes.value.data.checklist || {
        project_submitted: false,
        evaluation_done: false,
        admin_validated: false,
      });
    } else {
      setCompletionChecklist({
        project_submitted: false,
        evaluation_done: false,
        admin_validated: false,
      });
    }

    if (certificatesRes.status === "fulfilled") {
      setCertificates(certificatesRes.value.data.items || []);
    } else {
      setCertificates([]);
    }
  }, [hydrateForms, id]);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await fetchAll();
      } catch (err) {
        if (err.response?.data?.code === "FEATURE_DISABLED") {
          toast.error("People module is disabled");
          navigate("/ui/dashboard");
          return;
        }
        toast.error(err.response?.data?.error || err.message || "Failed to load person details");
        navigate("/ui/people");
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchAll, navigate, toast]);

  const refresh = async () => {
    await fetchAll();
  };

  const handleSaveProfile = async () => {
    try {
      setSaving(true);
      await api.patch(`/admin/people/${id}`, profileForm);
      toast.success("Profile updated");
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to update profile");
    } finally {
      setSaving(false);
    }
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
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to update employment");
    } finally {
      setSaving(false);
    }
  };

  const handleAddCheckin = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/people/${id}/checkins`, checkinForm);
      setCheckinForm(EMPTY_CHECKIN);
      toast.success("Check-in added");
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to add check-in");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleOnboardingItem = async (item) => {
    try {
      setSaving(true);
      await api.put(`/admin/internship/people/${id}/onboarding/${item.template_item_id}/check`, {
        checked: !item.checked,
      });
      toast.success("Onboarding progress updated");
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to update onboarding progress");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveCompletion = async () => {
    try {
      setSaving(true);
      await api.put(`/admin/internship/people/${id}/completion`, completionChecklist);
      toast.success("Completion checklist updated");
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to update completion checklist");
    } finally {
      setSaving(false);
    }
  };

  const handleIssueCertificate = async () => {
    try {
      setSaving(true);
      const res = await api.post(`/admin/internship/people/${id}/certificate`, certificateForm);
      if (res.data?.code === "APPROVAL_REQUIRED") {
        toast.success(`Approval required (#${res.data.approval_request?.id})`);
      } else {
        toast.success("Certificate issued");
        setCertificateForm({ pdf_url: "" });
      }
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to issue certificate");
    } finally {
      setSaving(false);
    }
  };

  const handleConvert = async () => {
    try {
      setSaving(true);
      const res = await api.post(`/admin/people/${id}/convert-to-full-time`, convertForm);
      if (res.data?.code === "APPROVAL_REQUIRED") {
        toast.success(`Approval required (#${res.data.approval_request?.id})`);
      } else {
        toast.success("Intern converted to full-time");
      }
      setShowConvertModal(false);
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Conversion failed");
    } finally {
      setSaving(false);
    }
  };

  const handleTerminate = async () => {
    try {
      setSaving(true);
      const res = await api.post(`/admin/people/${id}/terminate`, {});
      if (res.data?.code === "APPROVAL_REQUIRED") {
        toast.success(`Approval required (#${res.data.approval_request?.id})`);
      } else {
        toast.success("Person terminated");
      }
      setShowTerminateConfirm(false);
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Termination failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <PageLoader message="Loading person details..." />;
  }

  return (
    <div className="person-detail-page">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            <Link to="/ui/people">People</Link>
            <span>/</span>
            <span>{person?.full_name}</span>
          </div>
          <h1 className="page-title">{person?.full_name}</h1>
          <p className="page-subtitle">{person?.email} • {activeEmployment?.employment_type || "No active employment"}</p>
        </div>
        <div className="page-header-actions">
          {activeEmployment?.employment_type === "intern" && (
            <Button variant="secondary" onClick={() => setShowConvertModal(true)}>Convert to Full-time</Button>
          )}
          <Button variant="danger" onClick={() => setShowTerminateConfirm(true)}>Terminate</Button>
        </div>
      </div>

      <div className="person-detail-grid">
        <Card>
          <CardHeader title="Profile" />
          <CardBody>
            <div className="person-form-grid">
              <Input label="First Name" value={profileForm.first_name} onChange={(e) => setProfileForm((f) => ({ ...f, first_name: e.target.value }))} />
              <Input label="Last Name" value={profileForm.last_name} onChange={(e) => setProfileForm((f) => ({ ...f, last_name: e.target.value }))} />
              <Input label="Email" value={profileForm.email} onChange={(e) => setProfileForm((f) => ({ ...f, email: e.target.value }))} />
              <Input label="Phone" value={profileForm.phone} onChange={(e) => setProfileForm((f) => ({ ...f, phone: e.target.value }))} />
              <Input label="Team" value={profileForm.team} onChange={(e) => setProfileForm((f) => ({ ...f, team: e.target.value }))} />
              <Input label="Department" value={profileForm.department} onChange={(e) => setProfileForm((f) => ({ ...f, department: e.target.value }))} />
              <Input label="Cohort" value={profileForm.cohort} onChange={(e) => setProfileForm((f) => ({ ...f, cohort: e.target.value }))} />
              <Select label="Active" value={profileForm.is_active ? "true" : "false"} onChange={(e) => setProfileForm((f) => ({ ...f, is_active: e.target.value === "true" }))}>
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </Select>
            </div>
            <div className="actions-row">
              <Button variant="primary" loading={saving} onClick={handleSaveProfile}>Save Profile</Button>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Employment" subtitle="Active employment contract and reporting lines" />
          <CardBody>
            <div className="person-form-grid">
              <Select label="Employment Type" value={employmentForm.employment_type} onChange={(e) => setEmploymentForm((f) => ({ ...f, employment_type: e.target.value }))}>
                {metadata.employment_types.map((type) => <option key={type} value={type}>{type}</option>)}
              </Select>
              <Select
                label="Intern Track"
                value={employmentForm.intern_track}
                disabled={employmentForm.employment_type !== "intern"}
                onChange={(e) => setEmploymentForm((f) => ({ ...f, intern_track: e.target.value }))}
              >
                <option value="">None</option>
                {metadata.intern_tracks.map((track) => <option key={track} value={track}>{track}</option>)}
              </Select>
              <Select label="Status" value={employmentForm.status} onChange={(e) => setEmploymentForm((f) => ({ ...f, status: e.target.value }))}>
                {metadata.employment_statuses.map((status) => <option key={status} value={status}>{status}</option>)}
              </Select>
              <Input label="Title" value={employmentForm.title} onChange={(e) => setEmploymentForm((f) => ({ ...f, title: e.target.value }))} />
              <Input label="Start Date" type="date" value={employmentForm.start_date || ""} onChange={(e) => setEmploymentForm((f) => ({ ...f, start_date: e.target.value }))} />
              <Input label="End Date" type="date" value={employmentForm.end_date || ""} onChange={(e) => setEmploymentForm((f) => ({ ...f, end_date: e.target.value }))} />
              <Select label="Manager" value={employmentForm.manager_person_id || ""} onChange={(e) => setEmploymentForm((f) => ({ ...f, manager_person_id: e.target.value }))}>
                <option value="">Unassigned</option>
                {(metadata.managers || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Select>
              <Select label="Mentor" value={employmentForm.mentor_person_id || ""} onChange={(e) => setEmploymentForm((f) => ({ ...f, mentor_person_id: e.target.value }))}>
                <option value="">Unassigned</option>
                {(metadata.managers || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </Select>
            </div>
            <TextArea
              label="Notes"
              rows={3}
              value={employmentForm.notes}
              onChange={(e) => setEmploymentForm((f) => ({ ...f, notes: e.target.value }))}
            />
            <div className="actions-row">
              <Button variant="primary" loading={saving} onClick={handleSaveEmployment}>Save Employment</Button>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Check-ins" subtitle="Mentor/manager notes and feedback" />
          <CardBody>
            <div className="checkin-form">
              <Input
                label="Summary"
                value={checkinForm.summary}
                onChange={(e) => setCheckinForm((f) => ({ ...f, summary: e.target.value }))}
              />
              <TextArea
                label="Notes"
                rows={3}
                value={checkinForm.notes}
                onChange={(e) => setCheckinForm((f) => ({ ...f, notes: e.target.value }))}
              />
              <Button variant="primary" loading={saving} onClick={handleAddCheckin}>Add Check-in</Button>
            </div>
            <div className="history-list">
              {checkins.length === 0 ? <p className="empty-text">No check-ins yet</p> : checkins.map((checkin) => (
                <div key={checkin.id} className="history-item">
                  <div className="history-item-header">
                    <strong>{checkin.summary}</strong>
                    <span>{new Date(checkin.created_at).toLocaleString()}</span>
                  </div>
                  <p>{checkin.notes || "-"}</p>
                  <small>By {checkin.author_email}</small>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Employment History" />
          <CardBody>
            <div className="history-list">
              {employmentHistory.length === 0 ? <p className="empty-text">No history</p> : employmentHistory.map((emp) => (
                <div key={emp.id} className="history-item">
                  <div className="history-item-header">
                    <strong>{emp.employment_type}</strong>
                    <span>{emp.status}</span>
                  </div>
                  <p>{emp.title || "-"}</p>
                  <small>{emp.start_date || "-"} → {emp.end_date || "present"}</small>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Access Assignments" />
          <CardBody>
            <div className="history-list">
              {accessAssignments.length === 0 ? <p className="empty-text">No access assignments</p> : accessAssignments.map((entry) => (
                <div key={entry.id} className="history-item">
                  <div className="history-item-header">
                    <strong>{entry.system_name}</strong>
                    <span>{entry.status}</span>
                  </div>
                  <p>{entry.access_level}</p>
                  <small>Assigned by {entry.assigned_by_email}</small>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Onboarding Progress" subtitle={`${onboardingProgress.done}/${onboardingProgress.total} items completed`} />
          <CardBody>
            <div className="progress-inline">
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${onboardingProgress.progress_percent || 0}%` }} />
              </div>
              <span className="progress-label">{onboardingProgress.progress_percent || 0}%</span>
            </div>
            <div className="history-list">
              {onboardingItems.length === 0 ? <p className="empty-text">No onboarding templates found</p> : onboardingItems.map((item) => (
                <div key={item.template_item_id} className="history-item">
                  <div className="history-item-header">
                    <strong>{item.title}</strong>
                    <span>{item.checked ? "Completed" : "Pending"}</span>
                  </div>
                  <p>{item.description || "-"}</p>
                  <div className="actions-row">
                    <Button variant="secondary" size="sm" loading={saving} onClick={() => handleToggleOnboardingItem(item)}>
                      {item.checked ? "Mark Pending" : "Mark Complete"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Completion & Certificates" subtitle="Closeout checklist and certificate issuance" />
          <CardBody>
            <div className="person-form-grid">
              <Select
                label="Project Submitted"
                value={completionChecklist.project_submitted ? "true" : "false"}
                onChange={(e) => setCompletionChecklist((prev) => ({ ...prev, project_submitted: e.target.value === "true" }))}
              >
                <option value="false">No</option>
                <option value="true">Yes</option>
              </Select>
              <Select
                label="Evaluation Done"
                value={completionChecklist.evaluation_done ? "true" : "false"}
                onChange={(e) => setCompletionChecklist((prev) => ({ ...prev, evaluation_done: e.target.value === "true" }))}
              >
                <option value="false">No</option>
                <option value="true">Yes</option>
              </Select>
              <Select
                label="Admin Validated"
                value={completionChecklist.admin_validated ? "true" : "false"}
                onChange={(e) => setCompletionChecklist((prev) => ({ ...prev, admin_validated: e.target.value === "true" }))}
              >
                <option value="false">No</option>
                <option value="true">Yes</option>
              </Select>
            </div>
            <div className="actions-row">
              <Button variant="primary" loading={saving} onClick={handleSaveCompletion}>Save Completion Checklist</Button>
            </div>

            <Input
              label="Certificate PDF URL (optional)"
              value={certificateForm.pdf_url}
              onChange={(e) => setCertificateForm((prev) => ({ ...prev, pdf_url: e.target.value }))}
            />
            <div className="actions-row">
              <Button variant="secondary" loading={saving} onClick={handleIssueCertificate}>Issue Certificate</Button>
            </div>

            <div className="history-list">
              {certificates.length === 0 ? <p className="empty-text">No certificates issued</p> : certificates.map((certificate) => (
                <div key={certificate.id} className="history-item">
                  <div className="history-item-header">
                    <strong>{certificate.certificate_no}</strong>
                    <span>{new Date(certificate.issued_at).toLocaleString()}</span>
                  </div>
                  <p>{certificate.pdf_url || "-"}</p>
                  <small>Issued by {certificate.issued_by_email || "System"}</small>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Audit Trail" subtitle="Recent people-related changes" />
          <CardBody>
            <div className="history-list">
              {auditLogs.length === 0 ? <p className="empty-text">No audit records</p> : auditLogs.map((log) => (
                <div key={log.id} className="history-item">
                  <div className="history-item-header">
                    <strong>{log.action}</strong>
                    <span>{new Date(log.created_at).toLocaleString()}</span>
                  </div>
                  <p>{log.actor_email || "System"}</p>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>

      <Modal
        isOpen={showConvertModal}
        onClose={() => setShowConvertModal(false)}
        title="Convert Intern to Full-time"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setShowConvertModal(false)}>Cancel</Button>
            <Button variant="primary" loading={saving} onClick={handleConvert}>Convert</Button>
          </>
        )}
      >
        <Input label="New Title" value={convertForm.title} onChange={(e) => setConvertForm((f) => ({ ...f, title: e.target.value }))} />
        <Input label="Start Date" type="date" value={convertForm.start_date} onChange={(e) => setConvertForm((f) => ({ ...f, start_date: e.target.value }))} />
        <TextArea label="Notes" rows={3} value={convertForm.notes} onChange={(e) => setConvertForm((f) => ({ ...f, notes: e.target.value }))} />
      </Modal>

      <ConfirmModal
        isOpen={showTerminateConfirm}
        onClose={() => setShowTerminateConfirm(false)}
        onConfirm={handleTerminate}
        title="Terminate Person"
        message="This action can trigger governance approvals and will mark active employment as terminated."
        confirmText="Terminate"
        variant="danger"
        loading={saving}
      />
    </div>
  );
}
