import { useEffect, useState } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import Pagination from "../components/ui/Pagination";
import { PageLoader } from "../components/ui/Spinner";
import "./Jobs.css";

const normalizeArray = (response) => {
  if (!response) return [];
  if (Array.isArray(response)) return response;
  if (response.data?.items) return response.data.items;
  if (response.items) return response.items;
  if (Array.isArray(response.data)) return response.data;
  return [];
};

const statusVariants = {
  pending: "warning",
  completed: "success",
  failed: "error",
  running: "info",
};

export default function Jobs() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });

  const fetchJobs = async (page = 1) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/jobs?page=${page}&page_size=20`);
      const items = normalizeArray(res);
      setJobs(items);
      setPagination({
        page: res.data?.page || 1,
        pages: res.data?.pages || 1,
        total: res.data?.total || items.length,
        page_size: res.data?.page_size || 20,
      });
    } catch (err) {
      console.error("Failed to load jobs:", err);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs(1);
  }, []);

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="jobs-page">
      <div className="page-header">
        <h1 className="page-title">Background Jobs</h1>
        <p className="page-subtitle">Monitor job status and history</p>
      </div>

      <Card>
        <CardHeader title={`${pagination.total} Jobs`} />
        <CardBody>
          {loading ? (
            <PageLoader message="Loading jobs..." />
          ) : jobs.length === 0 ? (
            <div className="empty-state">
              <p>No jobs found</p>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Job ID</th>
                    <th>User</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.id}>
                      <td>{j.id}</td>
                      <td className="font-mono">{j.job_id}</td>
                      <td>{j.user_id}</td>
                      <td>
                        <Badge variant={statusVariants[j.status] || "default"}>
                          {j.status}
                        </Badge>
                      </td>
                      <td className="text-muted">{formatDate(j.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchJobs}
              />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
