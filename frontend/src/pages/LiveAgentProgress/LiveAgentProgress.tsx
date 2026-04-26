import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { getRun, getRunEvents, getRunPlan } from '../../lib/api'
import { supabase } from '../../lib/supabase'
import type { AgentEvent } from '../../types/plan'
import './LiveAgentProgress.css'

interface AgentLog { text: string; type: 'default' | 'primary' | 'secondary' | 'error' }
interface Agent { id: string; name: string; icon: string; progress: number; status: string; color: 'secondary' | 'primary' | 'tertiary' | 'dormant'; logs: AgentLog[]; active: boolean }
interface AgentMessage { id: string; from: string; to: string; text: string; level: 'info' | 'success' | 'warn' }
type AgentLogType = AgentLog['type']
type AgentMessageLevel = AgentMessage['level']

const initialAgents: Agent[] = [
  { id: 'literature', name: 'Literature Scout', icon: 'menu_book', progress: 0, status: 'WAITING', color: 'secondary', active: true, logs: [] },
  { id: 'protocol', name: 'Protocol Designer', icon: 'architecture', progress: 0, status: 'WAITING', color: 'primary', active: true, logs: [] },
  { id: 'materials', name: 'Materials Agent', icon: 'science', progress: 0, status: 'WAITING', color: 'tertiary', active: true, logs: [] },
  { id: 'budget', name: 'Budget Agent', icon: 'payments', progress: 0, status: 'WAITING', color: 'secondary', active: false, logs: [] },
  { id: 'timeline', name: 'Timeline Agent', icon: 'calendar_month', progress: 0, status: 'WAITING', color: 'primary', active: false, logs: [] },
  { id: 'review', name: 'Review Agent', icon: 'fact_check', progress: 0, status: 'WAITING', color: 'dormant', active: false, logs: [] },
]

const eventStatus: Record<string, string> = {
  starting: 'STARTING',
  progress: 'RUNNING',
  complete: 'COMPLETE',
  error: 'FAILED',
}

export default function LiveAgentProgress() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [agents, setAgents] = useState(initialAgents)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [streamError, setStreamError] = useState<string | null>(null)
  const seenEventIdsRef = useRef<Set<string>>(new Set())
  const hypothesis = (location.state as { hypothesis?: string } | null)?.hypothesis ?? 'Noch kein Hypothesis-Text uebergeben.'
  const runId = (location.state as { runId?: string } | null)?.runId ?? id ?? ''

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
    let isCancelled = false
    let poll: ReturnType<typeof setInterval> | null = null
    let channel: { unsubscribe?: () => void } | null = null
    const mapEventToAgent = (event: AgentEvent): string => event.agent === 'orchestrator' ? 'review' : event.agent

    const newMessageId = (): string =>
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `msg-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`

    const handleEvent = (event: AgentEvent): void => {
      if (isCancelled) {
        return
      }
      if (seenEventIdsRef.current.has(event.event_id)) {
        return
      }
      seenEventIdsRef.current.add(event.event_id)
      const target = mapEventToAgent(event)
      const messageId = newMessageId()
      setAgents((prev) =>
        prev.map((agent) => {
          if (agent.id !== target) {
            return agent
          }
          const done =
            event.phase === 'complete' ||
            event.phase === 'error' ||
            event.status === 'completed' ||
            event.status === 'failed'
          const logType: AgentLogType = event.phase === 'error' ? 'error' : 'default'
          return {
            ...agent,
            active: true,
            color: event.phase === 'error' ? 'tertiary' : agent.color,
            progress: done ? 100 : Math.min(100, Math.max(20, agent.progress + 20)),
            status: eventStatus[event.phase] ?? agent.status,
            logs: [{ text: `> ${event.agent}: ${event.phase}`, type: logType }, ...agent.logs].slice(0, 4),
          }
        })
      )
      const level: AgentMessageLevel = event.phase === 'error' ? 'warn' : 'info'
      setMessages((prev) => [
        {
          id: messageId,
          from: event.from_agent ?? event.agent,
          to: event.to_agent ?? 'UI',
          text: event.message ?? `${event.phase} (${event.status})`,
          level,
        },
        ...prev,
      ].slice(0, 6))
    }

    const run = async (): Promise<void> => {
      try {
        if (!runId) {
          throw new Error('run_id fehlt. Bitte Run neu starten.')
        }
        const history = await getRunEvents(runId)
        history.forEach(handleEvent)

        let knownSeq = history.length ? Math.max(...history.map((e) => e.sequence)) : 0
        const channelName = `run-${runId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        channel = supabase
          ? supabase
              .channel(channelName)
              .on(
                'postgres_changes',
                { event: 'INSERT', schema: 'public', table: 'agent_events', filter: `run_id=eq.${runId}` },
                (payload) => {
                  const event = payload.new as AgentEvent
                  if (event.sequence > knownSeq) {
                    knownSeq = event.sequence
                    handleEvent(event)
                  }
                }
              )
              .subscribe()
          : null

        poll = setInterval(async () => {
          if (isCancelled) return
          const latestEvents = await getRunEvents(runId)
          latestEvents
            .filter((event) => event.sequence > knownSeq)
            .sort((a, b) => a.sequence - b.sequence)
            .forEach((event) => {
              knownSeq = event.sequence
              handleEvent(event)
            })
          let status
          try {
            status = await getRun(runId)
          } catch (error) {
            // The run row can appear a moment after start in some environments.
            // Keep polling instead of failing the whole page on transient 404.
            if (error instanceof Error && error.message.includes('Run Status konnte nicht geladen werden')) {
              return
            }
            throw error
          }
          if (status.status === 'completed' && status.plan_id) {
            const plan = await getRunPlan(runId)
            if (!isCancelled) {
              navigate(`/experiments/${plan.plan_id}`, { state: { plan } })
            }
          } else if (status.status === 'failed') {
            setStreamError(status.error_message ?? 'Run fehlgeschlagen')
          }
        }, 1500)

      } catch (error) {
        if (isCancelled) {
          return
        }
        setStreamError(error instanceof Error ? error.message : 'Unbekannter Streaming-Fehler')
      }
    }

    void run()
    return () => {
      isCancelled = true
      if (poll) {
        clearInterval(poll)
      }
      if (channel && supabase) {
        supabase.removeChannel(channel as never)
      }
    }
  }, [hypothesis, navigate, runId])

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
                <strong>{Math.round(agents[5]?.progress ?? 0)}%</strong>
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
            {streamError ? (
              <div className="network-messages__item network-messages__item--warn">
                <span className="font-label-caps">Stream Error</span>
                <p>{streamError}</p>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  )
}
