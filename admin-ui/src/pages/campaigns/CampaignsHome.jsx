import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import api from "../../utils/api";
import AppIcon from "../../components/ui/AppIcon";
import Card, { CardHeader, CardBody } from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import { PageLoader } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/Toast";
import "./campaigns.css";

const Stat = ({ label, value, sub, accent }) => (
  <div className="cm-stat">
    <span className={`cm-stat-accent cm-accent-${accent}`} />
    <div className="cm-stat-label">{label}</div>
    <div className="cm-stat-value">{value}</div>
    {sub != null && <div className="cm-stat-sub">{sub}</div>}
  </div>
);

export default function CampaignsHome() {
  const [stats, setStats] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [s, c] = await Promise.all([
        api.get("/admin/email/stats"),
        api.get("/admin/email/campaigns?page=1&page_size=6"),
      ]);
      setStats(s.data);
      setCampaigns(c.data.campaigns || []);
    } catch (err) {
      if (err.response?.data?.code === "FEATURE_DISABLED") {
        toast.error("Email campaigns feature is not enabled");
        navigate("/ui/dashboard");
        return;
      }
      toast.error("Failed to load email overview");
    } finally {
      setLoading(false);
    }
  }, [toast, navigate]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <PageLoader message="Loading email overview…" />;

  const chartData = campaigns
    .filter((c) => c.sent_count > 0)
    .slice(0, 6)
    .reverse()
    .map((c) => ({
      name: c.name.length > 12 ? c.name.slice(0, 12) + "…" : c.name,
      Opens: c.open_count,
      Clicks: c.click_count,
    }));

  const ses = stats?.ses || {};

  return (
    <div className="cm-page">
      <div className="cm-head">
        <div>
          <h1>Email Campaigns</h1>
          <p>Your native marketing engine — contacts, campaigns, and deliverability, sent through Amazon SES.</p>
        </div>
        <Button variant="primary" icon={<AppIcon name="bell" size={16} />} onClick={() => navigate("/ui/email/campaigns")}>
          New campaign
        </Button>
      </div>

      <div className="cm-stats">
        <Stat label="Subscribers" value={(stats?.subscribers ?? 0).toLocaleString()} accent="blue"
              sub={`${stats?.suppressed ?? 0} suppressed`} />
        <Stat label="Campaigns sent" value={stats?.campaigns_sent ?? 0} accent="violet"
              sub={`${(stats?.total_sent ?? 0).toLocaleString()} emails`} />
        <Stat label="Open rate" value={`${stats?.open_rate ?? 0}%`} accent="green" />
        <Stat label="Click rate" value={`${stats?.click_rate ?? 0}%`} accent="amber" />
        <Stat label="Bounce rate" value={`${stats?.bounce_rate ?? 0}%`} accent="red"
              sub={`${stats?.complaint_rate ?? 0}% complaints`} />
      </div>

      <Card>
        <CardHeader title="Engagement by campaign" subtitle="Opens vs clicks across recent sends" />
        <CardBody>
          {chartData.length === 0 ? (
            <div className="cm-empty">
              <h3>No sent campaigns yet</h3>
              <p>Create a campaign, pick a list, and send to see engagement here.</p>
            </div>
          ) : (
            <div style={{ width: "100%", height: 260 }}>
              <ResponsiveContainer>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="name" stroke="#6b7280" fontSize={12} />
                  <YAxis stroke="#6b7280" fontSize={12} allowDecimals={false} />
                  <Tooltip contentStyle={{ background: "#0b1120", border: "1px solid #1f2937", borderRadius: 10 }} />
                  <Bar dataKey="Opens" fill="#34d399" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Clicks" fill="#fbbf24" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardBody>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 16 }}>
        <Card>
          <CardHeader title="Recent campaigns" action={
            <Button variant="ghost" size="sm" onClick={() => navigate("/ui/email/campaigns")}>View all</Button>
          } />
          <CardBody>
            {campaigns.length === 0 ? (
              <div className="cm-empty"><p>No campaigns yet.</p></div>
            ) : (
              <table className="cm-table">
                <thead><tr><th>Name</th><th>Status</th><th>Sent</th><th>Opens</th></tr></thead>
                <tbody>
                  {campaigns.map((c) => (
                    <tr key={c.id} className="cm-row-click" onClick={() => navigate(`/ui/email/campaigns/${c.id}`)}>
                      <td>{c.name}</td>
                      <td><Badge variant={statusVariant(c.status)}>{c.status}</Badge></td>
                      <td>{c.sent_count}</td>
                      <td>{c.open_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="SES health" subtitle="Sending quota & status" />
          <CardBody>
            {ses.available === false ? (
              <p style={{ color: "#9ca3af", fontSize: 13 }}>
                SES status unavailable in this environment (expected with LocalStack).
              </p>
            ) : (
              <div className="cm-health">
                <div className="cm-health-item">24h sent<b>{ses.sent_last_24_hours ?? "—"}</b></div>
                <div className="cm-health-item">24h limit<b>{ses.max_24_hour_send ?? "—"}</b></div>
                <div className="cm-health-item">Max rate/s<b>{ses.max_send_rate ?? "—"}</b></div>
                <div className="cm-health-item">Sending
                  <b><Badge variant={ses.sending_enabled ? "success" : "error"}>
                    {ses.sending_enabled ? "Enabled" : "Paused"}</Badge></b>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function statusVariant(status) {
  return { sent: "success", sending: "info", scheduled: "primary",
    draft: "default", failed: "error", paused: "warning" }[status] || "default";
}
