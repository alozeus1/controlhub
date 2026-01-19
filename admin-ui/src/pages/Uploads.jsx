import { useEffect, useState } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Pagination from "../components/ui/Pagination";
import { PageLoader } from "../components/ui/Spinner";
import "./Uploads.css";

const normalizeArray = (response) => {
  if (!response) return [];
  if (Array.isArray(response)) return response;
  if (response.data?.items) return response.data.items;
  if (response.items) return response.items;
  if (Array.isArray(response.data)) return response.data;
  return [];
};

export default function Uploads() {
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0, page_size: 20 });

  const fetchUploads = async (page = 1) => {
    try {
      setLoading(true);
      const res = await api.get(`/admin/uploads?page=${page}&page_size=20`);
      const items = normalizeArray(res);
      setUploads(items);
      setPagination({
        page: res.data?.page || 1,
        pages: res.data?.pages || 1,
        total: res.data?.total || items.length,
        page_size: res.data?.page_size || 20,
      });
    } catch (err) {
      console.error("Failed to load uploads:", err);
      setUploads([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUploads(1);
  }, []);

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="uploads-page">
      <div className="page-header">
        <h1 className="page-title">File Uploads</h1>
        <p className="page-subtitle">View uploaded files and their storage details</p>
      </div>

      <Card>
        <CardHeader title={`${pagination.total} Uploads`} />
        <CardBody>
          {loading ? (
            <PageLoader message="Loading uploads..." />
          ) : uploads.length === 0 ? (
            <div className="empty-state">
              <p>No uploads found</p>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>User</th>
                    <th>Filename</th>
                    <th>S3 Key</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.map((u) => (
                    <tr key={u.id}>
                      <td>{u.id}</td>
                      <td>{u.user_id}</td>
                      <td>{u.filename}</td>
                      <td className="font-mono text-muted">{u.s3_key}</td>
                      <td className="text-muted">{formatDate(u.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                page={pagination.page}
                pages={pagination.pages}
                total={pagination.total}
                pageSize={pagination.page_size}
                onPageChange={fetchUploads}
              />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
