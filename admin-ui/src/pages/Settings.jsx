import { useState, useEffect } from "react";
import Card, { CardHeader, CardBody, CardFooter } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import { RoleBadge } from "../components/ui/Badge";
import { useToast } from "../components/ui/Toast";
import api from "../utils/api";
import "./Settings.css";

export default function Settings() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const res = await api.get("/auth/me");
        setUser(res.data);
      } catch (err) {
        toast.error("Failed to load user data");
      } finally {
        setLoading(false);
      }
    };
    fetchUser();
  }, []);

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    toast.info("Password change not yet implemented");
  };

  return (
    <div className="settings-page">
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">Manage your account and preferences</p>
      </div>

      <div className="settings-grid">
        <Card>
          <CardHeader title="Account Information" subtitle="Your account details" />
          <CardBody>
            {loading ? (
              <p>Loading...</p>
            ) : user ? (
              <div className="settings-info">
                <div className="settings-row">
                  <span className="settings-label">Email</span>
                  <span className="settings-value">{user.email}</span>
                </div>
                <div className="settings-row">
                  <span className="settings-label">Role</span>
                  <RoleBadge role={user.role} />
                </div>
                <div className="settings-row">
                  <span className="settings-label">Status</span>
                  <span className={`settings-value ${user.is_active ? "text-success" : "text-error"}`}>
                    {user.is_active ? "Active" : "Disabled"}
                  </span>
                </div>
                <div className="settings-row">
                  <span className="settings-label">Member Since</span>
                  <span className="settings-value">
                    {new Date(user.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ) : (
              <p>Unable to load account information</p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Change Password" subtitle="Update your password" />
          <CardBody>
            <form onSubmit={handlePasswordChange} className="settings-form">
              <Input
                type="password"
                label="Current Password"
                placeholder="Enter current password"
              />
              <Input
                type="password"
                label="New Password"
                placeholder="Enter new password"
              />
              <Input
                type="password"
                label="Confirm Password"
                placeholder="Confirm new password"
              />
            </form>
          </CardBody>
          <CardFooter>
            <Button variant="primary" onClick={handlePasswordChange}>
              Update Password
            </Button>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader title="Role Permissions" subtitle="Your access level" />
          <CardBody>
            <div className="role-info">
              <div className="role-header">
                <RoleBadge role={user?.role || "user"} />
              </div>
              <div className="role-permissions">
                <h4>Permissions:</h4>
                <ul>
                  {user?.role === "superadmin" && (
                    <>
                      <li>Full system access</li>
                      <li>Manage all users</li>
                      <li>View audit logs</li>
                      <li>System configuration</li>
                    </>
                  )}
                  {user?.role === "admin" && (
                    <>
                      <li>Manage users (except superadmins)</li>
                      <li>View audit logs</li>
                      <li>Manage uploads and jobs</li>
                    </>
                  )}
                  {user?.role === "viewer" && (
                    <>
                      <li>View users</li>
                      <li>View audit logs</li>
                      <li>View uploads and jobs</li>
                    </>
                  )}
                  {user?.role === "user" && (
                    <>
                      <li>Access own profile</li>
                      <li>View public content</li>
                    </>
                  )}
                </ul>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="System Information" subtitle="Application details" />
          <CardBody>
            <div className="settings-info">
              <div className="settings-row">
                <span className="settings-label">Application</span>
                <span className="settings-value">Web Forx Admin</span>
              </div>
              <div className="settings-row">
                <span className="settings-label">Version</span>
                <span className="settings-value font-mono">1.0.0</span>
              </div>
              <div className="settings-row">
                <span className="settings-label">Environment</span>
                <span className="settings-value">
                  {import.meta.env?.MODE || process.env.NODE_ENV || "development"}
                </span>
              </div>
              <div className="settings-row">
                <span className="settings-label">API Endpoint</span>
                <span className="settings-value font-mono text-muted">
                  {import.meta.env?.VITE_API_URL || process.env.REACT_APP_API_URL || "http://localhost:9000"}
                </span>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
