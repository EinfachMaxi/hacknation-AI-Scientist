import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import './LiveAgentProgress.css'

interface AgentLog { text: string; type: 'default' | 'primary' | 'secondary' | 'error' | 'pending'; }
interface Agent { id: string; name: string; icon: string; progress: number; status: string; color: 'secondary' | 'primary' | 'tertiary' | 'dormant'; logs: AgentLog[]; active: boolean; }
interface AgentMessage { id: string; from: string; to: string; text: string; level: 'info' | 'success' | 'warn'; }

const initialAgents: Agent[] = [
  { id: 'literature', name: 'Literature Scout', icon: 'menu_book', progress: 62, status: 'EXTRACTING', color: 'secondary', active: true,
    logs: [
      { text: '> Initializing PubMed Query...', type: 'primary' },
      { text: '> GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=nanostructured+lipid+carriers', type: 'default' },
      { text: '> 243 results found. Filtering for diabetic models...', type: 'secondary' },
      { text: '> Extracting methodology from PMC8745321...', type: 'default' }
    ],
  },
  { id: 'protocol', name: 'Protocol Designer', icon: 'architecture', progress: 31, status: 'STRUCTURING STEPS', color: 'primary', active: true,
    logs: [
      { text: '> Awaiting inputs from Literature Scout...', type: 'default' },
      { text: '> Received partial context: NLC synthesis parameters.', type: 'default' },
      { text: '> Structuring Phase 1: NLC Preparation', type: 'primary' }
    ],
  },
  { id: 'materials', name: 'Materials Agent', icon: 'science', progress: 18, status: 'IDENTIFYING CATALOG NUMBERS', color: 'tertiary', active: true,
    logs: [
      { text: '> Initializing inventory cross-reference...', type: 'default' },
      { text: '> Querying Lab Alpha-7 local database...', type: 'default' },
      { text: '> Warning: Precirol ATO 5 stock low (45g remaining)', type: 'error' }
    ],
  },
  { id: 'validation', name: 'Validation Agent', icon: 'fact_check', progress: 9, status: 'CROSS-CHECKING', color: 'dormant', active: false, logs: [] },
]

const streamMessages: Omit<AgentMessage, 'id'>[] = [
  { from: 'Literature Scout', to: 'Protocol Designer', text: '3 relevante Methoden mit Erfolgsraten >72% übergeben.', level: 'success' },
  { from: 'Materials Agent', to: 'Protocol Designer', text: 'Materialliste ergänzt, Resolvin D1 hat Lieferzeitrisiko.', level: 'warn' },
  { from: 'Protocol Designer', to: 'Validation Agent', text: 'Draft v0.4 zur Plausibilitätsprüfung bereit.', level: 'info' },
  { from: 'Validation Agent', to: 'Protocol Designer', text: 'Kontrollgruppe ergänzt und Endpunkte präzisiert.', level: 'success' },
  { from: 'Protocol Designer', to: 'Materials Agent', text: 'Bitte alternative Lipidquellen für kritische Reagenzien.', level: 'info' },
  { from: 'Literature Scout', to: 'Validation Agent', text: 'Meta-Analyse mit 41 Studien als Referenz eingespeist.', level: 'success' },
]

export default function LiveAgentProgress() {
  const location = useLocation()
  const [agents, setAgents] = useState(initialAgents)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [, setMessageIndex] = useState(0)
  const [elapsed, setElapsed] = useState(165)
  const hypothesis = (location.state as { hypothesis?: string } | null)?.hypothesis ?? 'Noch kein Hypothesis-Text uebergeben.'

  const colorMap: Record<string, string> = useMemo(
    () => ({
      secondary: 'var(--secondary)',
      primary: 'var(--primary)',
      tertiary: 'var(--tertiary)',
      dormant: 'var(--outline-variant)',
    }),
    []
  )

  useEffect(() => { const i = setInterval(() => setElapsed((p) => p + 1), 1000); return () => clearInterval(i) }, [])
  useEffect(() => {
    const i = setInterval(() => {
      setAgents((prev) =>
        prev.map((a) => {
          if (!a.active || a.progress >= 100) {
            return a
          }

          const increment = Math.random() * 4
          const nextProgress = Math.min(100, a.progress + increment)
          let nextStatus = a.status

          if (a.id === 'literature' && nextProgress > 78) {
            nextStatus = 'SYNTHESIZING EVIDENCE'
          }
          if (a.id === 'protocol' && nextProgress > 55) {
            nextStatus = 'MERGING AGENT INPUTS'
          }
          if (a.id === 'materials' && nextProgress > 52) {
            nextStatus = 'MATCHING VENDOR ALTERNATIVES'
          }
          if (a.id === 'validation' && nextProgress > 35) {
            nextStatus = 'SCORING PROTOCOL QUALITY'
          }

          return { ...a, progress: nextProgress, status: nextStatus }
        })
      )
    }, 2000)
    return () => clearInterval(i)
  }, [])

  useEffect(() => {
    const i = setInterval(() => {
      setMessageIndex((prevIndex) => {
        const next = streamMessages[prevIndex % streamMessages.length]
        const nextMessage: AgentMessage = {
          ...next,
          id: `${Date.now()}-${prevIndex}`,
        }

        setMessages((prevMessages) => [nextMessage, ...prevMessages].slice(0, 6))

        if (next.to === 'Validation Agent') {
          setAgents((prevAgents) =>
            prevAgents.map((agent) =>
              agent.id === 'validation'
                ? { ...agent, active: true, color: 'secondary', status: 'REVIEWING INBOUND SIGNALS' }
                : agent
            )
          )
        }

        return prevIndex + 1
      })
    }, 3000)

    return () => clearInterval(i)
  }, [])

  const fmt = (s: number) => `${Math.floor(s/3600).toString().padStart(2,'0')}:${Math.floor((s%3600)/60).toString().padStart(2,'0')}:${(s%60).toString().padStart(2,'0')}`

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
                {hypothesis}
              </p>
            </div>
            <div style={{ flexShrink: 0, textAlign: 'right' }}>
              <div className="font-data-mono" style={{ color: 'var(--primary)', marginBottom: 4 }}>T+ {fmt(elapsed)}</div>
              <div className="live-progress__swarm-badge font-label-caps">SWARM ACTIVE</div>
            </div>
          </div>
        </section>

        <section className="live-progress__workspace" id="agent-grid">
          <aside className="live-progress__agents-column">
            <div className="live-progress__column-title font-label-caps">
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>dns</span>
              Agent Runtime
            </div>
            {agents.map((agent, i) => (
              <div key={agent.id} className={`agent-card ${!agent.active ? 'agent-card--dormant' : ''} animate-fadeIn`} style={{ animationDelay: `${0.1 + i * 0.1}s` }} id={`agent-card-${agent.id}`}>
                <div className="agent-card__progress-track"><div className="agent-card__progress-fill" style={{ width: `${Math.round(agent.progress)}%`, background: colorMap[agent.color], transition: 'width 0.5s ease' }} /></div>
                <div className="agent-card__header">
                  <div className="agent-card__header-left">
                    <div className={`agent-card__icon agent-card__icon--${agent.color}`}><span className="material-symbols-outlined" style={{ fontSize: 16 }}>{agent.icon}</span></div>
                    <h3 className="agent-card__name">{agent.name}</h3>
                  </div>
                  <span className="font-data-mono" style={{ color: colorMap[agent.color], fontSize: 13 }}>{Math.round(agent.progress)}%</span>
                </div>
                <div className={`agent-card__terminal ${!agent.active ? 'agent-card__terminal--dormant' : ''}`}>
                  {agent.active ? agent.logs.map((log, j) => (
                    <div key={j} className={`agent-card__log agent-card__log--${log.type}`}>{log.text}</div>
                  )) : (
                    <div className="agent-card__waiting"><span className="material-symbols-outlined" style={{ opacity: 0.5, marginBottom: 8 }}>hourglass_empty</span><div>Waiting for upstream signals...</div></div>
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
          </aside>

          <div className="live-progress__network-column glass-panel animate-fadeIn">
            <div className="live-progress__column-title font-label-caps">
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>hub</span>
              Agents Network
            </div>
            <div className="network-graph">
              <svg className="network-graph__lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                <line x1="18" y1="20" x2="48" y2="20" className="network-graph__line network-graph__line--active" />
                <line x1="48" y1="20" x2="78" y2="36" className="network-graph__line network-graph__line--active" />
                <line x1="48" y1="20" x2="78" y2="70" className="network-graph__line network-graph__line--active" />
                <line x1="18" y1="70" x2="48" y2="20" className="network-graph__line" />
                <line x1="18" y1="20" x2="18" y2="70" className="network-graph__line network-graph__line--soft" />
              </svg>
              <div className="network-graph__node network-graph__node--literature">
                <span className="font-label-caps">Literature</span>
                <strong>{Math.round(agents[0]?.progress ?? 0)}%</strong>
              </div>
              <div className="network-graph__node network-graph__node--protocol">
                <span className="font-label-caps">Protocol</span>
                <strong>{Math.round(agents[1]?.progress ?? 0)}%</strong>
              </div>
              <div className="network-graph__node network-graph__node--materials">
                <span className="font-label-caps">Materials</span>
                <strong>{Math.round(agents[2]?.progress ?? 0)}%</strong>
              </div>
              <div className="network-graph__node network-graph__node--validation">
                <span className="font-label-caps">Validation</span>
                <strong>{Math.round(agents[3]?.progress ?? 0)}%</strong>
              </div>
            </div>
            <div className="network-messages">
              <h3 className="font-label-caps network-messages__title">Inter-Agent Communication</h3>
              <div className="network-messages__feed" aria-live="polite">
                {messages.length === 0 ? (
                  <div className="network-messages__item network-messages__item--info">Warte auf erste Nachrichten zwischen den Agents...</div>
                ) : messages.map((message) => (
                  <div key={message.id} className={`network-messages__item network-messages__item--${message.level}`}>
                    <span className="font-label-caps">{message.from} → {message.to}</span>
                    <p>{message.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
