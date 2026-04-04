import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sparkles, Users, Lock, ChevronRight, BarChart, Bot, Activity } from 'lucide-react';
import './LandingPage.css';

export default function LandingPage() {
  return (
    <div className="landing-page">
      <nav className="landing-nav">
        <div className="landing-brand">
          <Sparkles color="#2ad2ff" /> ControlHub
        </div>
        <div className="nav-actions">
          <Link to="/ui/login" className="btn-glass">Sign In</Link>
          <Link to="/ui/dashboard" className="btn-primary">Go to Console</Link>
        </div>
      </nav>

      <section className="hero-section">
        <div className="hero-bg-glow"></div>
        <motion.div 
          className="hero-content"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <h1 className="hero-title">Intelligent Workforce Management</h1>
          <p className="hero-subtitle">
            Scale your organization effortlessly with a premium HR dashboard and an embedded AI Copilot designed to handle metrics, reports, and onboarding in seconds.
          </p>
          <div className="hero-actions">
            <Link to="/ui/dashboard" className="btn-primary" style={{ padding: '0.8rem 2rem', fontSize: '1.1rem' }}>
              Launch Console <ChevronRight size={18} />
            </Link>
          </div>
        </motion.div>
      </section>

      <section className="demo-section">
        <motion.div 
          className="demo-container"
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <div className="demo-header">
            <h2>Experience The Platform</h2>
            <p className="text-muted">Interactive demonstration of our core capabilities.</p>
          </div>

          <div className="demo-grid">
            {/* Visual Demo 1: The HR Dashboard */}
            <motion.div 
              className="demo-widget"
              whileHover={{ y: -5 }}
            >
              <h3><BarChart /> Metrics Dashboard</h3>
              <p className="text-muted" style={{ marginBottom: '1.5rem' }}>Visualize intern cohorts, departments, and cross-functional teams in real-time.</p>
              
              <div style={{ display: 'flex', gap: '1rem', flexDirection: 'column' }}>
                <div style={{ background: 'var(--color-bg-inset)', padding: '1rem', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}><Users size={20} color="var(--color-primary)"/> <span>Active Engineers</span></div>
                  <strong style={{ fontSize: '1.25rem' }}>24</strong>
                </div>
                <div style={{ background: 'var(--color-bg-inset)', padding: '1rem', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}><Activity size={20} color="var(--color-success)"/> <span>Intern Retention</span></div>
                  <strong style={{ fontSize: '1.25rem', color: 'var(--color-success)' }}>94%</strong>
                </div>
              </div>
            </motion.div>

            {/* Visual Demo 2: The AI Agent */}
            <motion.div 
              className="demo-widget box-glow"
              whileHover={{ y: -5 }}
              style={{ borderColor: 'rgba(42, 210, 255, 0.3)' }}
            >
              <h3><Bot /> AI Management Copilot</h3>
              <p className="text-muted">Chat with the intelligent agent embedded across your dashboard to rapidly export data and track changes.</p>
              
              <div className="demo-chat-box">
                <motion.div 
                   className="chat-msg chat-user"
                   initial={{ opacity: 0, x: 20 }}
                   whileInView={{ opacity: 1, x: 0 }}
                   viewport={{ once: true }}
                   transition={{ delay: 0.5 }}
                >
                  Generate a CSV report of the Summer Design Cohort.
                </motion.div>
                <motion.div 
                   className="chat-msg chat-agent"
                   initial={{ opacity: 0, x: -20 }}
                   whileInView={{ opacity: 1, x: 0 }}
                   viewport={{ once: true }}
                   transition={{ delay: 1.5 }}
                >
                  Analyzing cohort data... <br/><br/>
                  <span style={{ color: 'var(--color-primary)' }}>✓ Export request approved. Ready for download.</span>
                </motion.div>
              </div>
            </motion.div>

          </div>
        </motion.div>
      </section>
    </div>
  );
}
