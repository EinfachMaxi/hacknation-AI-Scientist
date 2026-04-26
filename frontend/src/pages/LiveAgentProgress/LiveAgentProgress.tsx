import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { getRun, getRunEvents, getRunPlan } from '../../lib/api'
import { supabase } from '../../lib/supabase'
import type { AgentEvent, AgentId } from '../../types/plan'
import './LiveAgentProgress.css'

interface AgentLog { text: string; type: 'default' | 'primary' | 'secondary' | 'error' }
interface AgentMessage { id: string; from: string; to: string; text: string; level: 'info' | 'success' | 'warn' }
type AgentLogType = AgentLog['type']
type AgentRuntimeState = 'idle' | 'running' | 'completed' | 'failed'
type AgentColor = 'secondary' | 'primary' | 'tertiary' | 'dormant'
type EdgeKey = 'literature->budget' | 'literature->timeline' | 'protocol->timeline' | 'materials->budget' | 'budget->review' | 'timeline->review'
type GraphNodeKey = Exclude<AgentId, 'orchestrator'>

interface AgentConfig {
  id: Exclude<AgentId, 'orchestrator'>
  name: string
  icon: string
  baseColor: AgentColor
}

interface AgentViewModel extends AgentConfig {
  progress: number
  status: string
  color: AgentColor
  logs: AgentLog[]
  active: boolean
  runtimeState: AgentRuntimeState
}

const agentsConfig: AgentConfig[] = [
  { id: 'literature', name: 'Literature Scout', icon: 'menu_book', baseColor: 'secondary' },
  { id: 'protocol', name: 'Protocol Designer', icon: 'architecture', baseColor: 'primary' },
  { id: 'materials', name: 'Materials Agent', icon: 'science', baseColor: 'tertiary' },
  { id: 'budget', name: 'Budget Agent', icon: 'payments', baseColor: 'secondary' },
  { id: 'timeline', name: 'Timeline Agent', icon: 'calendar_month', baseColor: 'primary' },
  { id: 'review', name: 'Review Agent', icon: 'fact_check', baseColor: 'dormant' },
]

const statusLabels: Record<AgentRuntimeState, string> = {
  idle: 'IDLE',
  running: 'RUNNING',
  completed: 'COMPLETED',
  failed: 'FAILED',
}

const graphNodeKeys: GraphNodeKey[] = ['literature', 'protocol', 'materials', 'budget', 'timeline', 'review']

const seededRandom = (seed: number): (() => number) => {
  let value = seed % 2147483647
  if (value <= 0) {
    value += 2147483646
  }
  return () => {
    value = (value * 16807) % 2147483647
    return (value - 1) / 2147483646
  }
}

const layoutSeedFromRunId = (value: string): number =>
  value.split('').reduce((acc, char, index) => acc + char.charCodeAt(0) * (index + 17), 811)

const graphEdges: Array<{ key: EdgeKey; from: GraphNodeKey; to: GraphNodeKey }> = [
  { key: 'literature->budget', from: 'literature', to: 'budget' },
  { key: 'literature->timeline', from: 'literature', to: 'timeline' },
  { key: 'protocol->timeline', from: 'protocol', to: 'timeline' },
  { key: 'materials->budget', from: 'materials', to: 'budget' },
  { key: 'budget->review', from: 'budget', to: 'review' },
  { key: 'timeline->review', from: 'timeline', to: 'review' },
]

export default function LiveAgentProgress() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [streamError, setStreamError] = useState<string | null>(null)
  const seenEventIdsRef = useRef<Set<string>>(new Set())
  const seenRunSeqRef = useRef<Set<string>>(new Set())
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

  const mapEventToAgent = (event: AgentEvent): Exclude<AgentId, 'orchestrator'> =>
    event.agent === 'orchestrator' ? 'review' : event.agent

  const runtimeStateFromEvent = (event: AgentEvent): AgentRuntimeState => {
    if (event.phase === 'error' || event.status === 'failed') {
      return 'failed'
    }
    if (event.phase === 'complete' || event.status === 'completed') {
      return 'completed'
    }
    return 'running'
  }

  const ingestEvent = (event: AgentEvent): void => {
    const seqKey = `${event.run_id}:${event.sequence}`
    if (seenEventIdsRef.current.has(event.event_id) || seenRunSeqRef.current.has(seqKey)) {
      return
    }
    seenEventIdsRef.current.add(event.event_id)
    seenRunSeqRef.current.add(seqKey)
    setEvents((prev) => [...prev, event].sort((a, b) => a.sequence - b.sequence))
  }

  const agents = useMemo<AgentViewModel[]>(() => {
    const grouped = new Map<string, AgentEvent[]>()
    events.forEach((event) => {
      const key = mapEventToAgent(event)
      grouped.set(key, [...(grouped.get(key) ?? []), event])
    })
    return agentsConfig.map((config) => {
      const agentEvents = grouped.get(config.id) ?? []
      const lastEvent = agentEvents[agentEvents.length - 1]
      const runtimeState: AgentRuntimeState = lastEvent ? runtimeStateFromEvent(lastEvent) : 'idle'
      const progress =
        runtimeState === 'completed'
          ? 100
          : runtimeState === 'failed'
            ? Math.max(15, Math.min(95, agentEvents.length * 20))
            : runtimeState === 'running'
              ? Math.max(20, Math.min(90, agentEvents.length * 20))
              : 0
      const color: AgentColor =
        runtimeState === 'failed' ? 'tertiary' : runtimeState === 'completed' ? config.baseColor : config.baseColor
      const logs: AgentLog[] = agentEvents
        .slice(-4)
        .reverse()
        .map((event) => {
          const logType: AgentLogType = event.phase === 'error' ? 'error' : 'default'
          return {
            text: `> ${event.agent}: ${event.phase}${event.message ? ` - ${event.message}` : ''}`,
            type: logType,
          }
        })

      return {
        ...config,
        progress,
        status: statusLabels[runtimeState],
        color,
        logs,
        active: runtimeState !== 'idle',
        runtimeState,
      }
    })
  }, [events])

  const messages = useMemo<AgentMessage[]>(() => {
    return events
      .filter((event) => event.from_agent || event.to_agent || event.message)
      .slice()
      .reverse()
      .slice(0, 8)
      .map((event) => ({
        id: event.event_id,
        from: event.from_agent ?? event.agent,
        to: event.to_agent ?? 'UI',
        text: event.message ?? `${event.phase} (${event.status})`,
        level: event.phase === 'error' ? 'warn' : event.phase === 'complete' ? 'success' : 'info',
      }))
  }, [events])

  const edgeState = useMemo<Record<EdgeKey, boolean>>(() => {
    const byAgent = new Map<string, AgentRuntimeState>()
    agents.forEach((agent) => byAgent.set(agent.id, agent.runtimeState))
    const linkEvents = events.filter((event) => event.from_agent && event.to_agent)
    const lastByLink = new Map<string, AgentEvent>()
    linkEvents.forEach((event) => {
      lastByLink.set(`${event.from_agent}->${event.to_agent}`, event)
    })
    const isLinkActive = (from: string, to: string): boolean => {
      const link = lastByLink.get(`${from}->${to}`)
      if (!link) {
        return false
      }
      const fromState = byAgent.get(from) ?? 'idle'
      const toState = byAgent.get(to) ?? 'idle'
      const fromLive = fromState === 'running' || fromState === 'completed'
      const toLive = toState === 'running' || toState === 'completed'
      return fromLive || toLive
    }
    return {
      'literature->budget': isLinkActive('literature', 'budget'),
      'literature->timeline': isLinkActive('literature', 'timeline'),
      'protocol->timeline': isLinkActive('protocol', 'timeline'),
      'materials->budget': isLinkActive('materials', 'budget'),
      'budget->review': isLinkActive('budget', 'review'),
      'timeline->review': isLinkActive('timeline', 'review'),
    }
  }, [agents, events])

  const graphNodes = useMemo(
    () => ({
      literature: agents.find((agent) => agent.id === 'literature'),
      protocol: agents.find((agent) => agent.id === 'protocol'),
      materials: agents.find((agent) => agent.id === 'materials'),
      budget: agents.find((agent) => agent.id === 'budget'),
      timeline: agents.find((agent) => agent.id === 'timeline'),
      review: agents.find((agent) => agent.id === 'review'),
    }),
    [agents]
  )

  const graphLayout = useMemo<Record<GraphNodeKey, { x: number; y: number; label: string }>>(() => {
    const rand = seededRandom(layoutSeedFromRunId(runId || 'fallback-graph-seed'))
    const points: Array<{ x: number; y: number }> = []
    const minDist = 14
    const makePoint = (): { x: number; y: number } => ({ x: 10 + rand() * 80, y: 12 + rand() * 76 })

    graphNodeKeys.forEach(() => {
      let candidate = makePoint()
      let attempts = 0
      while (
        attempts < 120 &&
        points.some((p) => Math.hypot(p.x - candidate.x, p.y - candidate.y) < minDist)
      ) {
        candidate = makePoint()
        attempts += 1
      }
      points.push(candidate)
    })

    return graphNodeKeys.reduce((acc, nodeKey, index) => {
      acc[nodeKey] = {
        x: points[index].x,
        y: points[index].y,
        label: agentsConfig.find((agent) => agent.id === nodeKey)?.name ?? nodeKey,
      }
      return acc
    }, {} as Record<GraphNodeKey, { x: number; y: number; label: string }>)
  }, [runId])

  useEffect(() => { const i = setInterval(() => setElapsed((p) => p + 1), 1000); return () => clearInterval(i) }, [])
  useEffect(() => {
    let isCancelled = false
    let poll: ReturnType<typeof setInterval> | null = null
    let channel: { unsubscribe?: () => void } | null = null
    const syncMissingEvents = async (knownSeq: number): Promise<number> => {
      const latestEvents = await getRunEvents(runId)
      let nextKnownSeq = knownSeq
      latestEvents
        .filter((event) => event.sequence > knownSeq)
        .sort((a, b) => a.sequence - b.sequence)
        .forEach((event) => {
          nextKnownSeq = Math.max(nextKnownSeq, event.sequence)
          ingestEvent(event)
        })
      return nextKnownSeq
    }
    const run = async (): Promise<void> => {
      try {
        if (!runId) {
          throw new Error('run_id fehlt. Bitte Run neu starten.')
        }
        setEvents([])
        seenEventIdsRef.current.clear()
        seenRunSeqRef.current.clear()

        const history = await getRunEvents(runId)
        history.forEach(ingestEvent)

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
                    ingestEvent(event)
                  }
                }
              )
              .subscribe(async (status) => {
                if (isCancelled) {
                  return
                }
                if (status === 'SUBSCRIBED' || status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
                  knownSeq = await syncMissingEvents(knownSeq)
                }
              })
          : null

        poll = setInterval(async () => {
          if (isCancelled) return
          knownSeq = await syncMissingEvents(knownSeq)
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
              <div
                key={agent.id}
                className={`agent-card agent-card--${agent.runtimeState} ${!agent.active ? 'agent-card--dormant' : ''} animate-fadeIn`}
                style={{ animationDelay: `${0.1 + i * 0.1}s` }}
                id={`agent-card-${agent.id}`}
              >
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
              <svg className="network-graph__canvas" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                <g className="network-graph__dust">
                  {Array.from({ length: 26 }, (_, i) => (
                    <circle
                      key={`dust-${i}`}
                      cx={8 + ((i * 37) % 84)}
                      cy={10 + ((i * 29) % 80)}
                      r={(i % 4) * 0.25 + 0.18}
                      className="network-graph__dust-point"
                    />
                  ))}
                </g>
                <defs>
                  <marker id="network-arrow-idle" markerWidth="5" markerHeight="5" refX="4.5" refY="2.5" orient="auto">
                    <path d="M0,0 L5,2.5 L0,5 z" className="network-graph__arrow network-graph__arrow--idle" />
                  </marker>
                  <marker id="network-arrow-active" markerWidth="5" markerHeight="5" refX="4.5" refY="2.5" orient="auto">
                    <path d="M0,0 L5,2.5 L0,5 z" className="network-graph__arrow network-graph__arrow--active" />
                  </marker>
                </defs>
                {graphEdges.map((edge) => {
                  const from = graphLayout[edge.from]
                  const to = graphLayout[edge.to]
                  const active = edgeState[edge.key]
                  const cx = (from.x + to.x) / 2
                  const cy = (from.y + to.y) / 2
                  const offset = from.y < to.y ? 8 : -8
                  return (
                    <path
                      key={edge.key}
                      d={`M ${from.x} ${from.y} Q ${cx} ${cy + offset} ${to.x} ${to.y}`}
                      className={`network-graph__line ${active ? 'network-graph__line--active' : ''}`}
                      markerEnd={`url(#${active ? 'network-arrow-active' : 'network-arrow-idle'})`}
                    />
                  )
                })}
                {(Object.keys(graphLayout) as GraphNodeKey[]).map((nodeKey) => {
                  const cfg = graphLayout[nodeKey]
                  const agent = graphNodes[nodeKey]
                  const state = agent?.runtimeState ?? 'idle'
                  const progress = Math.round(agent?.progress ?? 0)
                  return (
                    <g key={nodeKey} className={`network-graph__node-group network-graph__node-group--${state}`} transform={`translate(${cfg.x}, ${cfg.y})`}>
                      <title>{`${cfg.label}: ${statusLabels[state]} (${progress}%)`}</title>
                      <circle className="network-graph__node-ring" r="2.6" />
                      <circle className="network-graph__node-core" r="1.85" />
                      <text className="network-graph__node-label" x="3.4" y="-2.8" textAnchor="start">{cfg.label}</text>
                    </g>
                  )
                })}
              </svg>
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
