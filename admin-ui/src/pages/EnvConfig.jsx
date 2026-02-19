import { useEffect, useState, useCallback } from "react";
import api from "../utils/api";
import Card, { CardHeader, CardBody } from "../components/ui/Card";
import Button from "../components/ui/Button";
import Input, { Select } from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { PageLoader } from "../components/ui/Spinner";
import { useToast } from "../components/ui/Toast";
import "./EnvConfig.css";

const ENVIRONMENTS = ["dev", "staging", "prod"];

export default function EnvConfig() {
  const toast = useToast();

  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [activeEnv, setActiveEnv] = useState("dev");
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [configLoading, setConfigLoading] = useState(false);
  const [showProjectModal, setShowProjectModal] = useState(false);
  const [showVarModal, setShowVarModal] = useState(false);
  const [editingConfig, setEditingConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [projectForm, setProjectForm] = useState({ name: "", description: "" });
  const [varForm, setVarForm] = useState({
    key: "",
    value: "",
    description: "",
    is_secret: false,
  });

  const fetchProjects = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get("/admin/env-projects");
      setProjects(res.data.items || res.data || []);
    } catch {
      toast.error("Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const fetchConfigs = useCallback(async () => {
    if (!selectedProject) return;
    try {
      setConfigLoading(true);
      const res = await api.get(
        `/admin/env-projects/${selectedProject.id}/configs?environment=${activeEnv}`
      );
      setConfigs(res.data.items || res.data || []);
    } catch {
      toast.error("Failed to load configs");
    } finally {
      setConfigLoading(false);
    }
  }, [selectedProject, activeEnv, toast]);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  const handleCreateProject = async () => {
    if (!projectForm.name.trim()) {
      toast.error("Project name is required");
      return;
    }
    try {
      setSaving(true);
      await api.post("/admin/env-projects", projectForm);
      toast.success("Project created");
      setShowProjectModal(false);
      setProjectForm({ name: "", description: "" });
      fetchProjects();
    } catch (err) {
      toast.error(err.message || "Failed to create project");
    } finally {
      setSaving(false);
    }
  };

  const handleAddVar = async () => {
    if (!varForm.key.trim() || !varForm.value.trim()) {
      toast.error("Key and value are required");
      return;
    }
    try {
      setSaving(true);
      await api.post(`/admin/env-projects/${selectedProject.id}/configs`, {
        ...varForm,
        environment: activeEnv,
      });
      toast.success("Variable added");
      setShowVarModal(false);
      setVarForm({ key: "", value: "", description: "", is_secret: false });
      fetchConfigs();
    } catch (err) {
      toast.error(err.message || "Failed to add variable");
    } finally {
      setSaving(false);
    }
  };

  const handleInlineEdit = async (config) => {
    if (!editingConfig || editingConfig.value === config.value) {
      setEditingConfig(null);
      return;
    }
    try {
      await api.put(
        `/admin/env-projects/${selectedProject.id}/configs/${config.id}`,
        { value: editingConfig.value }
      );
      toast.success("Variable updated");
      setEditingConfig(null);
      fetchConfigs();
    } catch (err) {
      toast.error(err.message || "Failed to update");
    }
  };

  const handleDeleteConfig = async (configId) => {
    try {
      await api.delete(
        `/admin/env-projects/${selectedProject.id}/configs/${configId}`
      );
      toast.success("Variable deleted");
      fetchConfigs();
    } catch (err) {
      toast.error(err.message || "Failed to delete");
    }
  };

  const handleExport = async () => {
    try {
      const res = await api.get(
        `/admin/env-projects/${selectedProject.id}/export?environment=${activeEnv}`
      );
      const blob = new Blob([res.data], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${selectedProject.name}-${activeEnv}.env`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Exported .env file");
    } catch (err) {
      toast.error(err.message || "Failed to export");
    }
  };

  if (loading) {
    return <PageLoader message="Loading projects..." />;
  }

  return (
    <div className="envconfig-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Environment Config</h1>
          <p className="page-subtitle">Manage environment variables across projects</p>
        </div>
        <div className="page-header-actions">
          <Button variant="primary" onClick={() => setShowProjectModal(true)}>
            + Add Project
          </Button>
        </div>
      </div>

      <div className="envconfig-layout">
        {/* Left: Project List */}
        <div className="project-list">
          {projects.length === 0 ? (
            <div className="empty-projects">
              <p>No projects yet</p>
              <Button variant="primary" size="sm" onClick={() => setShowProjectModal(true)}>
                Create Project
              </Button>
            </div>
          ) : (
            projects.map((project) => (
              <div
                key={project.id}
                className={`project-card ${selectedProject?.id === project.id ? "active" : ""}`}
                onClick={() => {
                  setSelectedProject(project);
                  setActiveEnv("dev");
                }}
              >
                <div className="project-card-name">{project.name}</div>
                {project.description && (
                  <div className="project-card-desc">{project.description}</div>
                )}
                <div className="project-card-count">
                  {project.config_count ?? 0} variables
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right: Config Panel */}
        <div className="config-panel">
          {!selectedProject ? (
            <div className="empty-state">
              <div className="empty-state-icon">📋</div>
              <p className="empty-state-title">Select a project</p>
              <p className="empty-state-text">Choose a project from the left to manage its configuration</p>
            </div>
          ) : (
            <>
              <div className="config-header">
                <div className="env-tabs">
                  {ENVIRONMENTS.map((env) => (
                    <button
                      key={env}
                      className={`env-tab ${activeEnv === env ? "active" : ""}`}
                      onClick={() => setActiveEnv(env)}
                    >
                      {env}
                    </button>
                  ))}
                </div>
                <div className="config-actions">
                  <Button variant="secondary" size="sm" onClick={handleExport}>
                    Export .env
                  </Button>
                  <Button variant="primary" size="sm" onClick={() => setShowVarModal(true)}>
                    + Add Variable
                  </Button>
                </div>
              </div>

              {configLoading ? (
                <PageLoader message="Loading configs..." />
              ) : configs.length === 0 ? (
                <div className="empty-state">
                  <p className="empty-state-title">No variables for {activeEnv}</p>
                  <p className="empty-state-text">Add your first environment variable</p>
                  <Button variant="primary" onClick={() => setShowVarModal(true)}>
                    Add Variable
                  </Button>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Key</th>
                        <th>Value</th>
                        <th>Description</th>
                        <th>Secret</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {configs.map((config) => (
                        <tr key={config.id}>
                          <td className="config-key">{config.key}</td>
                          <td className="config-value">
                            {editingConfig?.id === config.id ? (
                              <input
                                className="inline-edit-input"
                                value={editingConfig.value}
                                onChange={(e) =>
                                  setEditingConfig({ ...editingConfig, value: e.target.value })
                                }
                                onBlur={() => handleInlineEdit(config)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") handleInlineEdit(config);
                                  if (e.key === "Escape") setEditingConfig(null);
                                }}
                                autoFocus
                              />
                            ) : (
                              <span
                                className="editable-value"
                                onClick={() =>
                                  setEditingConfig({
                                    id: config.id,
                                    value: config.is_secret ? "" : config.value,
                                  })
                                }
                              >
                                {config.is_secret ? "••••••••" : config.value}
                              </span>
                            )}
                          </td>
                          <td className="text-muted">{config.description || "-"}</td>
                          <td>
                            {config.is_secret ? (
                              <Badge variant="warning">Secret</Badge>
                            ) : (
                              <Badge variant="default">Plain</Badge>
                            )}
                          </td>
                          <td>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="danger"
                              onClick={() => handleDeleteConfig(config.id)}
                            >
                              Delete
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Add Project Modal */}
      <Modal
        isOpen={showProjectModal}
        onClose={() => {
          setShowProjectModal(false);
          setProjectForm({ name: "", description: "" });
        }}
        title="Add Project"
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowProjectModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreateProject} loading={saving}>Create</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Project Name *"
            value={projectForm.name}
            onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })}
            placeholder="e.g., my-api"
          />
          <Input
            label="Description"
            value={projectForm.description}
            onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
            placeholder="Short description"
          />
        </div>
      </Modal>

      {/* Add Variable Modal */}
      <Modal
        isOpen={showVarModal}
        onClose={() => {
          setShowVarModal(false);
          setVarForm({ key: "", value: "", description: "", is_secret: false });
        }}
        title={`Add Variable (${activeEnv})`}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowVarModal(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleAddVar} loading={saving}>Add</Button>
          </>
        }
      >
        <div className="form-stack">
          <Input
            label="Key *"
            value={varForm.key}
            onChange={(e) => setVarForm({ ...varForm, key: e.target.value })}
            placeholder="e.g., DATABASE_URL"
          />
          <Input
            label="Value *"
            type={varForm.is_secret ? "password" : "text"}
            value={varForm.value}
            onChange={(e) => setVarForm({ ...varForm, value: e.target.value })}
            placeholder="Enter value"
          />
          <Input
            label="Description"
            value={varForm.description}
            onChange={(e) => setVarForm({ ...varForm, description: e.target.value })}
            placeholder="What is this variable for?"
          />
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={varForm.is_secret}
              onChange={(e) => setVarForm({ ...varForm, is_secret: e.target.checked })}
            />
            Mark as secret (value will be masked)
          </label>
        </div>
      </Modal>
    </div>
  );
}
