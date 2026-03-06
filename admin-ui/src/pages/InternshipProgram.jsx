import { useCallback, useEffect, useMemo, useState } from "react";
import api from "../utils/api";
import Card, { CardBody, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select, TextArea } from "../components/ui/Input";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./InternshipProgram.css";

const EMPTY_PROGRAM_FORM = {
  name: "",
  description: "",
  start_date: "",
  end_date: "",
  status: "planned",
};

const EMPTY_COHORT_FORM = {
  program_id: "",
  name: "",
  track: "",
  status: "active",
  start_date: "",
  end_date: "",
};

const EMPTY_MEMBER_FORM = {
  cohort_id: "",
  person_id: "",
  role: "intern",
};

const EMPTY_TEMPLATE_FORM = {
  title: "",
  description: "",
  is_active: true,
};

export default function InternshipProgram() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [metadata, setMetadata] = useState({
    program_statuses: [],
    cohort_statuses: [],
    cohort_member_roles: [],
  });
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

  const selectedCohort = useMemo(
    () => cohorts.find((item) => String(item.id) === String(selectedCohortId)),
    [cohorts, selectedCohortId]
  );

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
      setMemberForm((prev) => ({ ...prev, cohort_id: String(first.id) }));
    }
  }, [selectedCohortId]);

  const loadMembers = useCallback(async (cohortId) => {
    if (!cohortId) {
      setMembers([]);
      return;
    }
    const res = await api.get(`/admin/internship/cohorts/${cohortId}/members`);
    setMembers(res.data.items || []);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await loadBaseData();
      } catch (err) {
        if (err.response?.data?.code === "FEATURE_DISABLED") {
          toast.error("Internship Program feature is disabled");
          return;
        }
        toast.error(err.response?.data?.error || err.message || "Failed to load internship program page");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadBaseData, toast]);

  useEffect(() => {
    loadMembers(selectedCohortId).catch((err) => {
      toast.error(err.response?.data?.error || err.message || "Failed to load cohort members");
    });
  }, [loadMembers, selectedCohortId, toast]);

  const refresh = async () => {
    await loadBaseData();
    await loadMembers(selectedCohortId);
  };

  const createProgram = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/programs", programForm);
      toast.success("Program created");
      setProgramForm(EMPTY_PROGRAM_FORM);
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to create program");
    } finally {
      setSaving(false);
    }
  };

  const createCohort = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/cohorts", {
        ...cohortForm,
        program_id: Number(cohortForm.program_id),
      });
      toast.success("Cohort created");
      setCohortForm(EMPTY_COHORT_FORM);
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to create cohort");
    } finally {
      setSaving(false);
    }
  };

  const addMember = async () => {
    try {
      setSaving(true);
      await api.post(`/admin/internship/cohorts/${memberForm.cohort_id}/members`, {
        person_id: Number(memberForm.person_id),
        role: memberForm.role,
      });
      toast.success("Member added to cohort");
      await loadMembers(memberForm.cohort_id);
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to add cohort member");
    } finally {
      setSaving(false);
    }
  };

  const removeMember = async (member) => {
    try {
      setSaving(true);
      await api.delete(`/admin/internship/cohorts/${member.cohort_id}/members/${member.id}`);
      toast.success("Member removed");
      await loadMembers(member.cohort_id);
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to remove member");
    } finally {
      setSaving(false);
    }
  };

  const createTemplate = async () => {
    try {
      setSaving(true);
      await api.post("/admin/internship/onboarding/templates", templateForm);
      toast.success("Onboarding template item created");
      setTemplateForm(EMPTY_TEMPLATE_FORM);
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to create onboarding item");
    } finally {
      setSaving(false);
    }
  };

  const toggleTemplate = async (item) => {
    try {
      setSaving(true);
      await api.patch(`/admin/internship/onboarding/templates/${item.id}`, {
        is_active: !item.is_active,
      });
      toast.success("Onboarding template updated");
      await refresh();
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to update onboarding item");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <PageLoader message="Loading internship program..." />;
  }

  return (
    <div className="internship-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Internship Program</h1>
          <p className="page-subtitle">Manage programs, cohorts, onboarding templates, and cohort assignments</p>
        </div>
        <div className="page-header-actions">
          <Button variant="secondary" onClick={refresh}>Refresh</Button>
        </div>
      </div>

      <div className="internship-grid">
        <Card>
          <CardHeader title="Programs" subtitle={`${programs.length} total`} />
          <CardBody>
            <div className="internship-form-grid">
              <Input label="Name" value={programForm.name} onChange={(e) => setProgramForm((prev) => ({ ...prev, name: e.target.value }))} />
              <Select label="Status" value={programForm.status} onChange={(e) => setProgramForm((prev) => ({ ...prev, status: e.target.value }))}>
                {metadata.program_statuses.map((status) => <option key={status} value={status}>{status}</option>)}
              </Select>
              <Input label="Start Date" type="date" value={programForm.start_date} onChange={(e) => setProgramForm((prev) => ({ ...prev, start_date: e.target.value }))} />
              <Input label="End Date" type="date" value={programForm.end_date} onChange={(e) => setProgramForm((prev) => ({ ...prev, end_date: e.target.value }))} />
            </div>
            <TextArea label="Description" rows={2} value={programForm.description} onChange={(e) => setProgramForm((prev) => ({ ...prev, description: e.target.value }))} />
            <div className="actions-row">
              <Button variant="primary" loading={saving} onClick={createProgram}>Create Program</Button>
            </div>

            <div className="table-wrap">
              <table className="internship-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Dates</th>
                  </tr>
                </thead>
                <tbody>
                  {programs.map((program) => (
                    <tr key={program.id}>
                      <td>
                        <div className="cell-stack">
                          <strong>{program.name}</strong>
                          <span>{program.description || "-"}</span>
                        </div>
                      </td>
                      <td>{program.status}</td>
                      <td>{program.start_date || "-"} → {program.end_date || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Cohorts" subtitle={`${cohorts.length} total`} />
          <CardBody>
            <div className="internship-form-grid">
              <Select label="Program" value={cohortForm.program_id} onChange={(e) => setCohortForm((prev) => ({ ...prev, program_id: e.target.value }))}>
                <option value="">Select program</option>
                {programs.map((program) => <option key={program.id} value={program.id}>{program.name}</option>)}
              </Select>
              <Input label="Cohort Name" value={cohortForm.name} onChange={(e) => setCohortForm((prev) => ({ ...prev, name: e.target.value }))} />
              <Input label="Track" value={cohortForm.track} onChange={(e) => setCohortForm((prev) => ({ ...prev, track: e.target.value }))} />
              <Select label="Status" value={cohortForm.status} onChange={(e) => setCohortForm((prev) => ({ ...prev, status: e.target.value }))}>
                {metadata.cohort_statuses.map((status) => <option key={status} value={status}>{status}</option>)}
              </Select>
              <Input label="Start Date" type="date" value={cohortForm.start_date} onChange={(e) => setCohortForm((prev) => ({ ...prev, start_date: e.target.value }))} />
              <Input label="End Date" type="date" value={cohortForm.end_date} onChange={(e) => setCohortForm((prev) => ({ ...prev, end_date: e.target.value }))} />
            </div>
            <div className="actions-row">
              <Button variant="primary" loading={saving} onClick={createCohort}>Create Cohort</Button>
            </div>

            <div className="table-wrap">
              <table className="internship-table">
                <thead>
                  <tr>
                    <th>Cohort</th>
                    <th>Track</th>
                    <th>Status</th>
                    <th>Program</th>
                  </tr>
                </thead>
                <tbody>
                  {cohorts.map((cohort) => (
                    <tr key={cohort.id} className={String(selectedCohortId) === String(cohort.id) ? "selected-row" : ""} onClick={() => {
                      setSelectedCohortId(String(cohort.id));
                      setMemberForm((prev) => ({ ...prev, cohort_id: String(cohort.id) }));
                    }}>
                      <td>{cohort.name}</td>
                      <td>{cohort.track}</td>
                      <td>{cohort.status}</td>
                      <td>{cohort.program_name || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="internship-grid">
        <Card>
          <CardHeader title="Cohort Membership" subtitle={selectedCohort ? `${selectedCohort.name} members` : "Select a cohort"} />
          <CardBody>
            <div className="internship-form-grid">
              <Select label="Cohort" value={memberForm.cohort_id} onChange={(e) => {
                setMemberForm((prev) => ({ ...prev, cohort_id: e.target.value }));
                setSelectedCohortId(e.target.value);
              }}>
                <option value="">Select cohort</option>
                {cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}
              </Select>
              <Select label="Person" value={memberForm.person_id} onChange={(e) => setMemberForm((prev) => ({ ...prev, person_id: e.target.value }))}>
                <option value="">Select person</option>
                {internCandidates.map((person) => <option key={person.id} value={person.id}>{person.full_name} ({person.email})</option>)}
              </Select>
              <Select label="Role" value={memberForm.role} onChange={(e) => setMemberForm((prev) => ({ ...prev, role: e.target.value }))}>
                {metadata.cohort_member_roles.map((role) => <option key={role} value={role}>{role}</option>)}
              </Select>
            </div>
            <div className="actions-row">
              <Button variant="primary" loading={saving} onClick={addMember} disabled={!memberForm.cohort_id || !memberForm.person_id}>Add Member</Button>
            </div>

            <div className="table-wrap">
              <table className="internship-table">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Role</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {members.length === 0 ? (
                    <tr><td colSpan={3}>No members yet.</td></tr>
                  ) : members.map((member) => (
                    <tr key={member.id}>
                      <td>
                        <div className="cell-stack">
                          <strong>{member.person_name}</strong>
                          <span>{member.person_email}</span>
                        </div>
                      </td>
                      <td>{member.role}</td>
                      <td>
                        <Button variant="danger" size="sm" loading={saving} onClick={() => removeMember(member)}>Remove</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Onboarding Templates" subtitle={`${templates.length} checklist templates`} />
          <CardBody>
            <div className="internship-form-grid">
              <Input label="Title" value={templateForm.title} onChange={(e) => setTemplateForm((prev) => ({ ...prev, title: e.target.value }))} />
              <Select label="Active" value={templateForm.is_active ? "true" : "false"} onChange={(e) => setTemplateForm((prev) => ({ ...prev, is_active: e.target.value === "true" }))}>
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </Select>
            </div>
            <TextArea label="Description" rows={2} value={templateForm.description} onChange={(e) => setTemplateForm((prev) => ({ ...prev, description: e.target.value }))} />
            <div className="actions-row">
              <Button variant="primary" loading={saving} onClick={createTemplate}>Create Template Item</Button>
            </div>

            <div className="template-list">
              {templates.map((template) => (
                <div key={template.id} className="template-item">
                  <div>
                    <strong>{template.title}</strong>
                    <p>{template.description || "-"}</p>
                  </div>
                  <div className="template-actions">
                    <span className={`status-pill ${template.is_active ? "active" : "inactive"}`}>{template.is_active ? "Active" : "Inactive"}</span>
                    <Button variant="secondary" size="sm" loading={saving} onClick={() => toggleTemplate(template)}>
                      {template.is_active ? "Disable" : "Enable"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
