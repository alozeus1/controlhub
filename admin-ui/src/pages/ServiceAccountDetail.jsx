import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal, { ConfirmModal } from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./ServiceAccountDetail.css";

const SCOPE_OPTIONS = [
  { value: "*", label: "Full Access" },
  { value: "uploads.read", label: "Uploads: Read" },
  { value: "uploads.write", label: "Uploads: Write" },
  { value: "users.read", label: "Users: Read" },
  { value: "jobs.read", label: "Jobs: Read" },
  { value: "jobs.write", label: "Jobs: Write" },
  { value: "audit.read", label: "Audit Logs: Read" },
];

export default function ServiceAccountDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const [account, setAccount] = useState(null);
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateKeyModal, setShowCreateKeyModal] = useState(false);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [newKey, setNewKey] = useState(null);
  const [revokeConfirm, setRevokeConfirm] = useState(null);
  const [keyFormData, setKeyFormData] = useState({ name: "", scopes: ["*"], expires_days: "" });
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [accountRes, keysRes] = await Promise.all([
        api.get(`/admin/service-accounts/${id}`),
        api.get(`/admin/service-accounts/${id}/keys?include_revoked=true`),
      ]);
      setAccount(accountRes.data);
      setKeys(keysRes.data.items || []);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Service accounts feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load service account");
      navigate("/ui/service-accounts");
    } finally {
      setLoading(false);
    }
  }, [id, toast, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreateKey = async () => {
    if (!keyFormData.name.trim()) {
      toast.error("Key name is required");
      return;
    }
    try {
      setSaving(true);
      const payload = {
        name: keyFormData.name,
        scopes: keyFormData.scopes,
      };
      if (keyFormData.expires_days) {
        const days = parseInt(keyFormData.expires_days);
        if (days > 0) {
          const expires = new Date();
          expires.setDate(expires.getDate() + days);
          payload.expires_at = expires.toISOString();
        }
      }
      const res = await api.post(`/admin/service-accounts/${id}/keys`, payload);
      setNewKey(res.data);
      setShowCreateKeyModal(false);
      setShowKeyModal(true);
      setKeyFormData({ name: "", scopes: ["*"], expires_days: "" });
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to create API key");
    } finally {
      setSaving(false);
    }
  };

  const handleRevokeKey = async () => {
    if (!revokeConfirm) return;
    try {
      setSaving(true);
      await api.post(`/admin/keys/${revokeConfirm.id}/revoke`);
      toast.success("API key revoked");
      setRevokeConfirm(null);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Failed to revoke key");
    } finally {
      setSaving(false);
    }
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success("Copied to clipboard");
    } catch (err) {
      toast.error("Failed to copy");
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  const handleScopeChange = (scope) => {
    setKeyFormData((prev) => {
      const scopes = prev.scopes.includes(scope)
        ? prev.scopes.filter((s) => s !== scope)
        : [...prev.scopes, scope];
      return { ...prev, scopes };
    });
  };

  if (loading) {
    return <PageLoader message="Loading service account..." />;
  }

  if (!account) {
    return null;
  }

  return (
    <div className="service-account-detail-page">
      <div className="page-header">
        <div>
          <div className="breadcrumb">
            <Link to="/ui/service-accounts">Service Accounts</Link>
            <span>/</span>
            <span>{account.name}</span>
          </div>
          <h1 className="page-title">{account.name}</h1>
          {account.description && <p className="page-subtitle">{account.description}</p>}
        </div>
        <Badge variant={account.is_active ? "success" : "error"} size="lg">
          {account.is_active ? "Active" : "Inactive"}
        </Badge>
      </div>

      <Card>
        <CardHeader
          title="API Keys"
          action={
            account.is_active && (
              <Button variant="primary" size="sm" onClick={() => setShowCreateKeyModal(true)}>
                + Create Key
              </Button>
            )
          }
        />
        <CardBody>
          {keys.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🔐</div>
              <p className="empty-state-title">No API keys</p>
              <p className="empty-state-text">Create an API key to enable authentication</p>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Key Prefix</th>
                  <th>Scopes</th>
                  <th>Last Used</th>
                  <th>Expires</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id} className={key.revoked_at ? "revoked-row" : ""}>
                    <td className="key-name">{key.name}</td>
                    <td>
                      <code className="key-prefix">{key.key_prefix}...</code>
                    </td>
                    <td>
                      <div className="scopes-cell">
                        {key.scopes?.length ? (
                          key.scopes.slice(0, 2).map((s) => (
                            <Badge key={s} variant="default" size="sm">{s}</Badge>
                          ))
                        ) : (
                          <Badge variant="warning" size="sm">Full Access</Badge>
                        )}
                        {key.scopes?.length > 2 && (
                          <span className="more-scopes">+{key.scopes.length - 2}</span>
                        )}
                      </div>
                    </td>
                    <td className="text-muted">
                      {key.last_used_at ? formatDate(key.last_used_at) : "Never"}
                    </td>
                    <td className="text-muted">
                      {key.expires_at ? formatDate(key.expires_at) : "Never"}
                    </td>
                    <td>
                      {key.revoked_at ? (
                        <Badge variant="error">Revoked</Badge>
                      ) : key.is_valid ? (
                        <Badge variant="success">Active</Badge>
                      ) : (
                        <Badge variant="warning">Expired</Badge>
                      )}
                    </td>
                    <td>
                      {!key.revoked_at && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="danger"
                          onClick={() => setRevokeConfirm(key)}
                        >
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      {/* Create Key Modal */}
      <Modal
        isOpen={showCreateKeyModal}
        onClose={() => setShowCreateKeyModal(false)}
        title="Create API Key"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateKeyModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreateKey} loading={saving}>Create Key</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Key Name"
            value={keyFormData.name}
            onChange={(e) => setKeyFormData({ ...keyFormData, name: e.target.value })}
            placeholder="e.g., Production Deploy Key"
          />
          <div className="form-group">
            <label className="form-label">Scopes</label>
            <div className="scopes-grid">
              {SCOPE_OPTIONS.map((opt) => (
                <label key={opt.value} className="scope-checkbox">
                  <input
                    type="checkbox"
                    checked={keyFormData.scopes.includes(opt.value)}
                    onChange={() => handleScopeChange(opt.value)}
                  />
                  <span>{opt.label}</span>
                </label>
              ))}
            </div>
          </div>
          <Select
            label="Expiration"
            value={keyFormData.expires_days}
            onChange={(e) => setKeyFormData({ ...keyFormData, expires_days: e.target.value })}
          >
            <option value="">Never expires</option>
            <option value="30">30 days</option>
            <option value="90">90 days</option>
            <option value="180">180 days</option>
            <option value="365">1 year</option>
          </Select>
        </div>
      </Modal>

      {/* Show New Key Modal */}
      <Modal
        isOpen={showKeyModal}
        onClose={() => {
          setShowKeyModal(false);
          setNewKey(null);
        }}
        title="API Key Created"
        size="md"
        footer={
          <Button variant="primary" onClick={() => {
            setShowKeyModal(false);
            setNewKey(null);
          }}>
            I've saved the key
          </Button>
        }
      >
        {newKey && (
          <div className="new-key-display">
            <div className="warning-banner">
              <span className="warning-icon">⚠️</span>
              <span>Copy this key now. It will not be shown again!</span>
            </div>
            <div className="key-display">
              <code className="key-value">{newKey.key}</code>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => copyToClipboard(newKey.key)}
              >
                {copied ? "Copied!" : "Copy"}
              </Button>
            </div>
            <div className="key-info">
              <p><strong>Name:</strong> {newKey.api_key.name}</p>
              <p><strong>Prefix:</strong> {newKey.api_key.key_prefix}</p>
            </div>
          </div>
        )}
      </Modal>

      {/* Revoke Confirm */}
      <ConfirmModal
        isOpen={!!revokeConfirm}
        onClose={() => setRevokeConfirm(null)}
        onConfirm={handleRevokeKey}
        title="Revoke API Key"
        message={`Are you sure you want to revoke "${revokeConfirm?.name}"? This action cannot be undone.`}
        confirmText="Revoke Key"
        confirmVariant="danger"
        loading={saving}
      />
    </div>
  );
}
