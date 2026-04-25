import { useState, useEffect } from 'react'
import './LiveAgentProgress.css'

interface AgentLog { text: string; type: 'default' | 'primary' | 'secondary' | 'error' | 'pending'; }
interface Agent { id: string; name: string; icon: string; progress: number; status: string; color: 'secondary' | 'primary' | 'tertiary' | 'dormant'; logs: AgentLog[]; active: boolean; }

const initialAgents: Agent[] = [
  { id: 'literature', name: 'Literature Scout', icon: 'menu_book', progress: 80, status: 'EXTRACTING', color: 'secondary', active: true,
    logs: [
      { text: '> Initializing PubMed Query...', type: 'primary' },
      { text: '> GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=nanostructured+lipid+carriers', type: 'default' },
      { text: '> 243 results found. Filtering for diabetic models...', type: 'secondary' },
      { text: '> Extracting methodology from PMC8745321...', type: 'default' },
      { text: '_ Analyzing pharmacokinetic profiles...', type: 'pending' },
    ],
  },
  { id: 'protocol', name: 'Protocol Designer', icon: 'architecture', progress: 45, status: 'STRUCTURING STEPS', color: 'primary', active: true,
    logs: [
      { text: '> Awaiting inputs from Literature Scout...', type: 'default' },
      { text: '> Received partial context: NLC synthesis parameters.', type: 'default' },
      { text: '> Structuring Phase 1: NLC Preparation', type: 'primary' },
      { text: '> Establishing sonication intervals (3x 30s at 40W)', type: 'default' },
      { text: '_ Generating phase diagrams for lipid selection...', type: 'pending' },
    ],
  },
  { id: 'materials', name: 'Materials Agent', icon: 'science', progress: 20, status: 'IDENTIFYING CATALOG NUMBERS', color: 'tertiary', active: true,
    logs: [
      { text: '> Initializing inventory cross-reference...', type: 'default' },
      { text: '> Querying Lab Alpha-7 local database...', type: 'default' },
      { text: '> Warning: Precirol ATO 5 stock low (45g remaining)', type: 'error' },
      { text: '> POST https://api.sigmaaldrich.com/v1/catalog/search?query=Resolvin+D1', type: 'default' },
      { text: '_ Awaiting vendor API response...', type: 'pending' },
    ],
  },
  { id: 'budget', name: 'Budget Agent', icon: 'account_balance', progress: 0, status: 'DORMANT', color: 'dormant', active: false, logs: [] },
]

export default function LiveAgentProgress() {
  const [agents, setAgents] = useState(initialAgents)
  const [elapsed, setElapsed] = useState(165)

  useEffect(() => { const i = setInterval(() => setElapsed((p) => p + 1), 1000); return () => clearInterval(i) }, [])
  useEffect(() => {
    const i = setInterval(() => {
      setAgents((prev) => prev.map((a) => (!a.active || a.progress >= 100) ? a : { ...a, progress: Math.min(100, a.progress + Math.random() * 3) }))
    }, 2000)
    return () => clearInterval(i)
  }, [])

  const fmt = (s: number) => `${Math.floor(s/3600).toString().padStart(2,'0')}:${Math.floor((s%3600)/60).toString().padStart(2,'0')}:${(s%60).toString().padStart(2,'0')}`
  const colorMap: Record<string, string> = { secondary: 'var(--secondary)', primary: 'var(--primary)', tertiary: 'var(--tertiary)', dormant: 'var(--outline-variant)' }

  return (
    <div className="live-progress" id="live-agent-progress-page">
      <div className="live-progress__container">
        <section className="live-progress__banner animate-fadeIn" id="hypothesis-banner">
          <div className="live-progress__banner-gradient"></div>
          <div className="live-progress__banner-content">
            <div className="live-progress__banner-icon">
              <span className="material-symbols-outlined animate-pulse" style={{ fontSize: 30, color: 'var(--primary)' }}>model_training</span>
              <div className="live-progress__ping"></div>
              <div className="live-progress__ping-static"></div>
            </div>
            <div style={{ flex: 1 }}>
              <h1 className="font-headline-md" style={{ color: 'var(--on-surface)', marginBottom: 8 }}>Generating Experimental Protocol</h1>
              <p className="font-body-base" style={{ color: 'var(--on-surface-variant)', maxWidth: 800 }}>
                <span style={{ fontWeight: 700, color: 'var(--primary)' }}>Hypothesis:</span>{' '}
                Application of nanostructured lipid carriers (NLCs) loaded with specialized pro-resolving mediators (SPMs) will significantly accelerate tissue regeneration in compromised diabetic wound models.
              </p>
            </div>
            <div style={{ flexShrink: 0, textAlign: 'right' }}>
              <div className="font-data-mono" style={{ color: 'var(--primary)', marginBottom: 4 }}>T+ {fmt(elapsed)}</div>
              <div className="live-progress__swarm-badge font-label-caps">SWARM ACTIVE</div>
            </div>
          </div>
        </section>

        <section className="live-progress__grid" id="agent-grid">
          {agents.map((agent, i) => (
            <div key={agent.id} className={`agent-card ${!agent.active ? 'agent-card--dormant' : ''} animate-fadeIn`} style={{ animationDelay: `${0.1 + i * 0.1}s` }} id={`agent-card-${agent.id}`}>
              <div className="agent-card__progress-track"><div className="agent-card__progress-fill" style={{ width: `${Math.round(agent.progress)}%`, background: colorMap[agent.color], transition: 'width 0.5s ease' }} /></div>
              <div className="agent-card__header">
                <div className="agent-card__header-left">
                  <div className={`agent-card__icon agent-card__icon--${agent.color}`}><span className="material-symbols-outlined" style={{ fontSize: 16 }}>{agent.icon}</span></div>
                  <h3 className="agent-card__name">{agent.name}</h3>
                </div>
                <span className="font-data-mono" style={{ color: colorMap[agent.color], fontSize: 13 }}>{Math.round(agent.progress)}% COMPLETE</span>
              </div>
              <div className={`agent-card__terminal ${!agent.active ? 'agent-card__terminal--dormant' : ''}`}>
                {agent.active ? agent.logs.map((log, j) => (
                  <div key={j} className={`agent-card__log agent-card__log--${log.type}`}>{log.text}</div>
                )) : (
                  <div className="agent-card__waiting"><span className="material-symbols-outlined" style={{ opacity: 0.5, marginBottom: 8 }}>hourglass_empty</span><div>Waiting for Materials Agent...</div></div>
                )}
              </div>
              <div className="agent-card__footer">
                <span className="font-label-caps" style={{ color: 'var(--outline)', fontSize: 10 }}>STATUS: {agent.status}</span>
                <div className="agent-card__bars">
                  {Array.from({ length: 5 }, (_, k) => <div key={k} className="agent-card__bar" style={{ background: k < Math.round((agent.progress / 100) * 5) ? colorMap[agent.color] : '#334155' }} />)}
                </div>
              </div>
            </div>
          ))}
        </section>
      </div>
    </div>
  )
}
