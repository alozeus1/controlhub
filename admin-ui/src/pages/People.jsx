import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../utils/api";
import Card, { CardBody, CardHeader } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Modal from "../components/ui/Modal";
import Pagination from "../components/ui/Pagination";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./People.css";

const EMPTY_FORM = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  team: "",
  department: "",
  cohort: "",
  employment_type: "full_time",
  intern_track: "",
  title: "",
  manager_person_id: "",
  mentor_person_id: "",
  start_date: "",
  notes: "",
};

export default function People() {
  const toast = useToast();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [people, setPeople] = useState([]);
  const [metadata, setMetadata] = useState({
    employment_types: [],
    employment_statuses: [],
    intern_tracks: [],
    teams: [],
    departments: [],
    cohorts: [],
    managers: [],
  });
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });
  const [filters, setFilters] = useState({
    search: "",
    employment_type: "",
    intern_track: "",
    status: "",
    team: "",
    cohort: "",
    manager_person_id: "",
  });
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formData, setFormData] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [approvedExportRequestId, setApprovedExportRequestId] = useState("");

  const managerOptions = useMemo(() => metadata.managers || [], [metadata.managers]);
  const hasActiveFilters = useMemo(
    () => Object.values(filters).some((value) => Boolean(value)),
    [filters]
  );

  const fetchMetadata = useCallback(async () => {
    const res = await api.get("/admin/people/metadata");
    setMetadata(res.data || {});
  }, []);

  const fetchPeople = useCallback(async (page = 1) => {
    const params = new URLSearchParams({ page, page_size: 20 });
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.append(key, value);
    });
    const res = await api.get(`/admin/people?${params}`);
    setPeople(res.data.items || []);
    setPagination({
      page: res.data.page,
      pages: res.data.pages,
      total: res.data.total,
      page_size: res.data.page_size,
    });
  }, [filters]);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        await Promise.all([fetchMetadata(), fetchPeople(1)]);
      } catch (err) {
        if (err.response?.data?.code === "FEATURE_DISABLED") {
          toast.error("People module is disabled");
          navigate("/ui/dashboard");
          return;
        }
        toast.error(err.message || "Failed to load people directory");
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchMetadata, fetchPeople, navigate, toast]);

  useEffect(() => {
    if (!loading) {
      fetchPeople(1).catch(() => toast.error("Failed to refresh directory"));
    }
  }, [filters, fetchPeople, loading, toast]);

  const handleCreatePerson = async () => {
    try {
      setSaving(true);
      const payload = {
        ...formData,
        manager_person_id: formData.manager_person_id ? Number(formData.manager_person_id) : null,
        mentor_person_id: formData.mentor_person_id ? Number(formData.mentor_person_id) : null,
      };
      if (payload.employment_type !== "intern") {
        payload.intern_track = null;
      }
      await api.post("/admin/people", payload);
      toast.success("Person created");
      setShowCreateModal(false);
      setFormData(EMPTY_FORM);
      await fetchPeople(pagination.page || 1);
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to create person");
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async () => {
    try {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value);
      });
      if (approvedExportRequestId) {
        params.append("approval_request_id", approvedExportRequestId);
      }
      const res = await api.get(`/admin/people/export/csv?${params.toString()}`, { responseType: "blob" });

      if (res.data?.code === "APPROVAL_REQUIRED" && res.data?.approval_request?.id) {
        const requestId = String(res.data.approval_request.id);
        setApprovedExportRequestId(requestId);
        toast.success(`Export requires approval (request #${requestId}). After approval, click Export CSV again.`);
        return;
      }

      const disposition = res.headers["content-disposition"] || "";
      const match = disposition.match(/filename=([^;]+)/i);
      const filename = match?.[1] || "people_directory.csv";

      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename.replace(/"/g, "");
      a.click();
      window.URL.revokeObjectURL(url);
      setApprovedExportRequestId("");
      toast.success("People directory exported");
    } catch (err) {
      toast.error(err.response?.data?.error || err.message || "Failed to export directory");
    }
  };

  if (loading) {
    return <PageLoader message="Loading people directory..." />;
  }

  return (
    <div className="people-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">People Directory</h1>
          <p className="page-subtitle">Manage employees, interns, managers, and mentors in one place</p>
        </div>
        <div className="page-header-actions">
          {approvedExportRequestId && (
            <span className="pending-approval-tag">Pending export approval #{approvedExportRequestId}</span>
          )}
          <Button variant="secondary" onClick={handleExport}>Export CSV</Button>
          <Button variant="primary" onClick={() => setShowCreateModal(true)}>+ Add Person</Button>
        </div>
      </div>

      <Card>
        <CardHeader title={`${pagination.total} people`}>
          <div className="people-filters">
            <Input
              placeholder="Search by name or email"
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            />
            <Select
              value={filters.employment_type}
              onChange={(e) => setFilters((f) => ({ ...f, employment_type: e.target.value }))}
            >
              <option value="">All Types</option>
              {metadata.employment_types.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </Select>
            <Select
              value={filters.intern_track}
              onChange={(e) => setFilters((f) => ({ ...f, intern_track: e.target.value }))}
            >
              <option value="">All Tracks</option>
              {metadata.intern_tracks.map((track) => (
                <option key={track} value={track}>{track}</option>
              ))}
            </Select>
            <Select
              value={filters.status}
              onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            >
              <option value="">All Status</option>
              {metadata.employment_statuses.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </Select>
            <Select
              value={filters.team}
              onChange={(e) => setFilters((f) => ({ ...f, team: e.target.value }))}
            >
              <option value="">All Teams</option>
              {metadata.teams.map((team) => (
                <option key={team} value={team}>{team}</option>
              ))}
            </Select>
            <Select
              value={filters.manager_person_id}
              onChange={(e) => setFilters((f) => ({ ...f, manager_person_id: e.target.value }))}
            >
              <option value="">All Managers</option>
              {managerOptions.map((manager) => (
                <option key={manager.id} value={manager.id}>{manager.name}</option>
              ))}
            </Select>
            <Select
              value={filters.cohort}
              onChange={(e) => setFilters((f) => ({ ...f, cohort: e.target.value }))}
            >
              <option value="">All Cohorts</option>
              {metadata.cohorts.map((cohort) => (
                <option key={cohort} value={cohort}>{cohort}</option>
              ))}
            </Select>
          </div>
          {hasActiveFilters && (
            <div className="people-filter-actions">
              <Button
                variant="secondary"
                onClick={() => setFilters({
                  search: "",
                  employment_type: "",
                  intern_track: "",
                  status: "",
                  team: "",
                  cohort: "",
                  manager_person_id: "",
                })}
              >
                Clear Filters
              </Button>
            </div>
          )}
        </CardHeader>
        <CardBody>
          {people.length === 0 ? (
            <div className="empty-state">
              <p>No records found with the current filters.</p>
              <Button variant="secondary" onClick={() => setShowCreateModal(true)}>Add First Person</Button>
            </div>
          ) : (
            <>
              <table className="people-table">
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Type</th>
                    <th>Track</th>
                    <th>Status</th>
                    <th>Team</th>
                    <th>Manager</th>
                    <th>Cohort</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {people.map((person) => (
                    <tr key={person.id}>
                      <td>
                        <div className="person-cell">
                          <strong>{person.full_name}</strong>
                          <span>{person.email}</span>
                        </div>
                      </td>
                      <td>{person.active_employment?.employment_type || "-"}</td>
                      <td>{person.active_employment?.intern_track || "-"}</td>
                      <td>{person.active_employment?.status || (person.is_active ? "active" : "inactive")}</td>
                      <td>{person.team || "-"}</td>
                      <td>{person.active_employment?.manager_name || "-"}</td>
                      <td>{person.cohort || "-"}</td>
                      <td>
                        <Link to={`/ui/people/${person.id}`} className="person-link">Open</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchPeople}
              />
            </>
          )}
        </CardBody>
      </Card>

      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Add Person"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button variant="primary" loading={saving} onClick={handleCreatePerson}>Create</Button>
          </>
        )}
      >
        <div className="people-form-grid">
          <Input label="First Name" value={formData.first_name} onChange={(e) => setFormData((f) => ({ ...f, first_name: e.target.value }))} />
          <Input label="Last Name" value={formData.last_name} onChange={(e) => setFormData((f) => ({ ...f, last_name: e.target.value }))} />
          <Input label="Email" type="email" value={formData.email} onChange={(e) => setFormData((f) => ({ ...f, email: e.target.value }))} />
          <Input label="Phone" value={formData.phone} onChange={(e) => setFormData((f) => ({ ...f, phone: e.target.value }))} />
          <Input label="Team" value={formData.team} onChange={(e) => setFormData((f) => ({ ...f, team: e.target.value }))} />
          <Input label="Department" value={formData.department} onChange={(e) => setFormData((f) => ({ ...f, department: e.target.value }))} />
          <Input label="Cohort" value={formData.cohort} onChange={(e) => setFormData((f) => ({ ...f, cohort: e.target.value }))} />
          <Input label="Title" value={formData.title} onChange={(e) => setFormData((f) => ({ ...f, title: e.target.value }))} />
          <Select label="Employment Type" value={formData.employment_type} onChange={(e) => setFormData((f) => ({ ...f, employment_type: e.target.value }))}>
            {metadata.employment_types.map((type) => <option key={type} value={type}>{type}</option>)}
          </Select>
          <Select
            label="Intern Track"
            value={formData.intern_track}
            disabled={formData.employment_type !== "intern"}
            onChange={(e) => setFormData((f) => ({ ...f, intern_track: e.target.value }))}
          >
            <option value="">None</option>
            {metadata.intern_tracks.map((track) => <option key={track} value={track}>{track}</option>)}
          </Select>
          <Select
            label="Manager"
            value={formData.manager_person_id}
            onChange={(e) => setFormData((f) => ({ ...f, manager_person_id: e.target.value }))}
          >
            <option value="">Unassigned</option>
            {managerOptions.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </Select>
          <Select
            label="Mentor"
            value={formData.mentor_person_id}
            onChange={(e) => setFormData((f) => ({ ...f, mentor_person_id: e.target.value }))}
          >
            <option value="">Unassigned</option>
            {managerOptions.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </Select>
          <Input
            label="Start Date"
            type="date"
            value={formData.start_date}
            onChange={(e) => setFormData((f) => ({ ...f, start_date: e.target.value }))}
          />
          <Input
            label="Notes"
            value={formData.notes}
            onChange={(e) => setFormData((f) => ({ ...f, notes: e.target.value }))}
          />
        </div>
      </Modal>
    </div>
  );
}
