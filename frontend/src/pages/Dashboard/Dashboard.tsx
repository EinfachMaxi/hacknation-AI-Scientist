import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './Dashboard.css'

interface Experiment { id: string; title: string; status: 'completed' | 'in-progress' | 'draft'; timeAgo: string; }
interface AgentStatus { name: string; status: string; statusColor: string; progress: number; }

const recentExperiments: Experiment[] = [
  { id: 'EXP-8492', title: 'Graphene Oxide Sensor Cal...', status: 'completed', timeAgo: '2h ago' },
  { id: 'EXP-8491', title: 'Aptamer Binding Affinity Test', status: 'in-progress', timeAgo: '1d ago' },
]

const agentStatuses: AgentStatus[] = [
  { name: 'LITERATURE_AGENT', status: 'IDLE', statusColor: 'var(--secondary)', progress: 100 },
  { name: 'PLANNING_AGENT', status: 'PROCESSING', statusColor: 'var(--primary)', progress: 66 },
  { name: 'REVIEW_AGENT', status: 'STANDBY', statusColor: 'var(--outline)', progress: 0 },
]

const statusColors: Record<string, string> = { completed: 'var(--secondary)', 'in-progress': 'var(--tertiary)', draft: 'var(--outline)' }

export default function Dashboard() {
  const [hypothesis, setHypothesis] = useState('')
  const navigate = useNavigate()

  return (
    <div className="dashboard knowledge-grid">
      <div className="dashboard__container">
        <section className="dashboard__input-section glass-panel animate-fadeIn" id="hypothesis-input-section">
          <div className="dashboard__input-glow"></div>
          <h1 className="font-headline-md dashboard__title">
            <span className="material-symbols-outlined dashboard__title-icon" style={{ fontVariationSettings: "'FILL' 1" }}>biotech</span>
            Scientific Question Formulation
          </h1>
          <div className="dashboard__textarea-wrapper">
            <textarea className="dashboard__textarea font-data-mono" placeholder="Type your hypothesis (e.g., A paper-based electrochemical biosensor...)" value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} id="hypothesis-textarea" />
            <div className="dashboard__textarea-status font-label-caps">{hypothesis.length > 0 ? `${hypothesis.length} CHARS` : 'AWAITING INPUT'}</div>
          </div>
          <div className="dashboard__input-actions">
            <button className="dashboard__attach-btn glass-panel font-label-caps" id="attach-context-btn">
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>attach_file</span>Attach Context
            </button>
            <button className="dashboard__generate-btn btn-glow font-label-caps" onClick={() => { if (hypothesis.trim()) navigate('/experiments/EXP-8492/progress') }} id="generate-plan-btn">
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>auto_awesome</span>Generate Plan
            </button>
          </div>
        </section>

        <div className="dashboard__grid">
          <section className="dashboard__recent glass-panel animate-fadeIn" style={{ animationDelay: '0.1s' }} id="recent-experiments">
            <div className="dashboard__recent-header">
              <h3 className="font-label-caps dashboard__section-title"><span className="material-symbols-outlined" style={{ fontSize: 14 }}>history</span>Recent Experiments</h3>
              <button className="dashboard__view-all font-label-caps">View All</button>
            </div>
            <div className="dashboard__experiment-list">
              {recentExperiments.map((exp) => (
                <div key={exp.id} className="dashboard__experiment-row" onClick={() => navigate(`/experiments/${exp.id}`)} id={`experiment-${exp.id}`}>
                  <div className="dashboard__experiment-info">
                    <span className="dashboard__experiment-dot" style={{ background: statusColors[exp.status] }}></span>
                    <span className="font-data-mono dashboard__experiment-id">{exp.id}</span>
                    <span className="dashboard__experiment-title">{exp.title}</span>
                  </div>
                  <div className="dashboard__experiment-meta">
                    <span className="dashboard__experiment-time font-label-caps">{exp.timeAgo}</span>
                    <span className="material-symbols-outlined" style={{ fontSize: 16, color: 'var(--outline)' }}>chevron_right</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="dashboard__agents glass-panel animate-fadeIn" style={{ animationDelay: '0.2s' }} id="agent-status-panel">
            <h3 className="font-label-caps dashboard__section-title"><span className="material-symbols-outlined" style={{ fontSize: 14 }}>memory</span>Agent Network Status</h3>
            <div className="dashboard__agent-list">
              {agentStatuses.map((agent) => (
                <div key={agent.name} className="dashboard__agent-item">
                  <div className="dashboard__agent-header">
                    <span className="font-label-caps" style={{ fontSize: 10 }}>{agent.name}</span>
                    <span className="font-label-caps" style={{ fontSize: 10, color: agent.statusColor }}>{agent.status}</span>
                  </div>
                  <div className="dashboard__agent-bar">
                    <div className={`dashboard__agent-bar-fill ${agent.status === 'PROCESSING' ? 'animate-pulse' : ''}`} style={{ width: `${agent.progress}%`, background: agent.statusColor }}></div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
