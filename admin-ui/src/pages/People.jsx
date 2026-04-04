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
import { motion } from "framer-motion";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip as RechartsTooltip, BarChart, Bar, XAxis, YAxis } from "recharts";
import { Users, Activity, Briefcase, Plus, Download } from 'lucide-react';
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

const COLORS = ['#2ad2ff', '#7695ff', '#ffb549', '#24c783'];

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

  // Derive simple aggregations for visual dashboard based on current page subset
  const typeCounts = people.reduce((acc, p) => {
    const type = p.active_employment?.employment_type || "unassigned";
    acc[type] = (acc[type] || 0) + 1;
    return acc;
  }, {});

  const pieData = Object.keys(typeCounts).map(key => ({ name: key, value: typeCounts[key] }));

  if (loading) {
    return <PageLoader message="Loading premium management hub..." />;
  }

  return (
    <motion.div 
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="people-page"
    >
      <div className="page-header">
        <div>
          <h1 className="page-title text-gradient">Workforce Command Center</h1>
          <p className="page-subtitle">Manage, monitor, and scale your global talent pool.</p>
        </div>
        <div className="page-header-actions" style={{ display: 'flex', gap: '1rem' }}>
          {approvedExportRequestId && (
            <span className="pending-approval-tag">Pending export approval #{approvedExportRequestId}</span>
          )}
          <button className="btn-glass" onClick={handleExport}>
            <Download size={16} /> Export CSV
          </button>
          <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
            <Plus size={16} /> Add Talent
          </button>
        </div>
      </div>

      {/* DASHBOARD WIDGETS */}
      <div className="grid grid-3" style={{ marginBottom: '2rem' }}>
        <motion.div whileHover={{ scale: 1.02 }} className="glass-panel">
          <div className="glass-header">
            <h3><Users size={20} color="#2ad2ff" /> Total Roster</h3>
          </div>
          <div className="metric-value">{pagination.total}</div>
          <div className="metric-label">Active Employees & Interns</div>
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} className="glass-panel">
          <div className="glass-header">
            <h3><Briefcase size={20} color="#7695ff" /> Composition</h3>
          </div>
          <div style={{ height: '100px' }}>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={30} outerRadius={45} paddingAngle={5}>
                    {pieData.map((entry, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip contentStyle={{ background: '#070d1a', border: '1px solid #273a5d', color: '#edf3ff' }} />
                </PieChart>
              </ResponsiveContainer>
            ) : <p className="text-muted">No data available.</p>}
          </div>
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} className="glass-panel">
           <div className="glass-header">
            <h3><Activity size={20} color="#24c783" /> Active Cohorts</h3>
          </div>
          <div className="metric-value">{metadata.cohorts?.length || 0}</div>
          <div className="metric-label">Running Internship Programs</div>
        </motion.div>
      </div>

      <div className="glass-panel">
        <div className="glass-header">
          <h3>Directory</h3>
        </div>
        
        <div className="people-filters" style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
            <Input
              placeholder="Search by name or email"
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            />
            <Select value={filters.employment_type} onChange={(e) => setFilters((f) => ({ ...f, employment_type: e.target.value }))}>
              <option value="">All Types</option>
              {metadata.employment_types.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </Select>
            <Select value={filters.intern_track} onChange={(e) => setFilters((f) => ({ ...f, intern_track: e.target.value }))}>
              <option value="">All Tracks</option>
              {metadata.intern_tracks.map((track) => (
                <option key={track} value={track}>{track}</option>
              ))}
            </Select>
            <Select value={filters.status} onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}>
              <option value="">All Status</option>
              {metadata.employment_statuses.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </Select>
            {hasActiveFilters && (
              <button className="btn-glass" onClick={() => setFilters({search: "", employment_type: "", intern_track: "", status: "", team: "", cohort: "", manager_person_id: ""})}>
                Clear
              </button>
            )}
        </div>

        <div className="table-responsive">
          {people.length === 0 ? (
            <div className="empty-state" style={{ padding: '3rem', textAlign: 'center' }}>
              <p className="text-muted">No records found. Start adding people to your directory.</p>
            </div>
          ) : (
            <>
              <table>
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Role & Dept</th>
                    <th>Status</th>
                    <th>Manager</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {people.map((person) => (
                    <tr key={person.id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                          <div className="avatar-circle">
                            {person.first_name?.[0]}{person.last_name?.[0]}
                          </div>
                          <div>
                            <strong style={{ display: 'block', color: 'var(--color-text-primary)' }}>{person.full_name}</strong>
                            <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>{person.email}</span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 500 }}>{person.active_employment?.title || person.active_employment?.employment_type || "-"}</div>
                        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>{person.department || person.team || "Unassigned"}</div>
                      </td>
                      <td>
                        {person.active_employment?.status === "active" ? (
                           <span className="badge badge-success">Active</span>
                        ) : (
                           <span className="badge badge-neutral">{person.active_employment?.status || "Inactive"}</span>
                        )}
                      </td>
                      <td>{person.active_employment?.manager_name || "-"}</td>
                      <td>
                        <Link to={`/ui/people/${person.id}`} className="btn-glass" style={{ padding: '0.25rem 0.75rem' }}>View Profile</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ marginTop: '1.5rem' }}>
                <Pagination
                  page={pagination.page}
                  pages={pagination.pages}
                  total={pagination.total}
                  pageSize={pagination.page_size}
                  onPageChange={fetchPeople}
                />
              </div>
            </>
          )}
        </div>
      </div>

      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Onboard New Talent"
        footer={(
          <>
            <button className="btn-glass" onClick={() => setShowCreateModal(false)}>Cancel</button>
            <button className="btn-primary" disabled={saving} onClick={handleCreatePerson}>Complete Onboarding</button>
          </>
        )}
      >
        <div className="people-form-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <Input label="First Name" value={formData.first_name} onChange={(e) => setFormData((f) => ({ ...f, first_name: e.target.value }))} />
          <Input label="Last Name" value={formData.last_name} onChange={(e) => setFormData((f) => ({ ...f, last_name: e.target.value }))} />
          <Input label="Email" type="email" value={formData.email} onChange={(e) => setFormData((f) => ({ ...f, email: e.target.value }))} />
          <Input label="Phone" value={formData.phone} onChange={(e) => setFormData((f) => ({ ...f, phone: e.target.value }))} />
          <Input label="Team" value={formData.team} onChange={(e) => setFormData((f) => ({ ...f, team: e.target.value }))} />
          <Input label="Department" value={formData.department} onChange={(e) => setFormData((f) => ({ ...f, department: e.target.value }))} />
          <Select label="Employment Type" value={formData.employment_type} onChange={(e) => setFormData((f) => ({ ...f, employment_type: e.target.value }))}>
            {metadata.employment_types.map((type) => <option key={type} value={type}>{type}</option>)}
          </Select>
          <Input label="Title" value={formData.title} onChange={(e) => setFormData((f) => ({ ...f, title: e.target.value }))} />
          <Input label="Start Date" type="date" value={formData.start_date} onChange={(e) => setFormData((f) => ({ ...f, start_date: e.target.value }))} />
          <Input label="Notes" value={formData.notes} onChange={(e) => setFormData((f) => ({ ...f, notes: e.target.value }))} />
        </div>
      </Modal>
    </motion.div>
  );
}
