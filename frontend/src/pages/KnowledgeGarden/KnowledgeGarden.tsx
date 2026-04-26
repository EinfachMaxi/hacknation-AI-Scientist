import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  askKnowledgeChat,
  confirmKnowledgeProposal,
  fetchKnowledgeGraph,
  proposeKnowledgeSave,
} from '../../lib/api'
import type {
  KnowledgeChatCitation,
  KnowledgeChatResponse,
  KnowledgeEdge,
  KnowledgeNode,
  KnowledgeNodeType,
} from '../../types/plan'
import './KnowledgeGarden.css'

type GraphNodeType =
  | 'experiment'
  | 'correction'
  | 'reagent'
  | 'claim'
  | 'literature'
  | 'chat_insight'
  | 'entity'

interface RawNode {
  id: string
  type: GraphNodeType
  title?: string
  conf?: string
  applied?: number
  abstract?: string
}

interface RawEdge {
  f: string
  t: string
  h?: boolean
}

interface SimNode extends RawNode {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  degree: number
  cluster: number
}

interface ClusterCenter {
  x: number
  y: number
  size: number
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: KnowledgeChatCitation[]
  proposed?: KnowledgeNode | null
  proposedEdges?: KnowledgeEdge[]
  saveState?: 'idle' | 'pending' | 'saved' | 'rejected'
}

const seedNodes: RawNode[] = [
  { id: 'EXP-992', type: 'experiment', title: 'Quantum Alignment Vector', conf: '94.2%', applied: 128, abstract: 'Observation of stable quantum states under high thermal load.' },
  { id: 'COR-001', type: 'correction', title: 'Substrate cleaning duration', conf: '88%', applied: 12 },
  { id: 'RGT-01', type: 'reagent', title: 'Graphene Oxide 2mg/mL', applied: 21 },
  { id: 'EXP-841', type: 'experiment', title: 'GO Sensor Calibration', conf: '91%', applied: 47 },
  { id: 'RGT-02', type: 'reagent', title: 'Argon UHP', applied: 5 },
  { id: 'COR-002', type: 'correction', title: 'Ramp rate 5°C/min', conf: '93%', applied: 8 },
  { id: 'RGT-03', type: 'reagent', title: 'Au Wire 99.99%', applied: 4 },
  { id: 'EXP-100', type: 'experiment', title: 'Baseline Resistance Drift', conf: '76%', applied: 3 },
  { id: 'COR-003', type: 'correction', title: 'N2 Purge Time', applied: 2 },
]

const seedEdges: RawEdge[] = [
  { f: 'EXP-992', t: 'COR-001' },
  { f: 'EXP-992', t: 'RGT-01' },
  { f: 'EXP-992', t: 'EXP-841', h: true },
  { f: 'EXP-992', t: 'RGT-02' },
  { f: 'EXP-841', t: 'COR-002' },
  { f: 'EXP-841', t: 'RGT-03' },
  { f: 'COR-001', t: 'EXP-100' },
  { f: 'COR-001', t: 'COR-003' },
]

const tc: Record<GraphNodeType, { dot: string; icon: string; label: string }> = {
  experiment: { dot: 'var(--primary)', icon: 'science', label: 'EXPERIMENT' },
  correction: { dot: 'var(--tertiary)', icon: 'tune', label: 'CORRECTION' },
  reagent: { dot: 'var(--secondary)', icon: 'water_drop', label: 'REAGENT' },
  claim: { dot: 'var(--tertiary)', icon: 'fact_check', label: 'CLAIM' },
  literature: { dot: 'var(--secondary)', icon: 'menu_book', label: 'LITERATURE' },
  chat_insight: { dot: 'var(--primary)', icon: 'lightbulb', label: 'INSIGHT' },
  entity: { dot: 'var(--outline)', icon: 'category', label: 'ENTITY' },
}

const FORCE = {
  repulsion: 5200,
  springLength: 110,
  springStrength: 0.045,
  centerStrength: 0.012,
  damping: 0.82,
  maxVelocity: 9,
  collisionPadding: 6,
}

function makeId(): string {
  return `m-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`
}

function mapApiNode(node: {
  id: string
  node_type: KnowledgeNodeType
  title?: string | null
  content?: string | null
  times_applied?: number
  confidence?: number
}): RawNode {
  return {
    id: node.id,
    type: (node.node_type as GraphNodeType) ?? 'entity',
    title: node.title ?? node.id,
    conf: node.confidence != null ? `${Math.round(node.confidence * 100)}%` : undefined,
    applied: node.times_applied ?? 1,
    abstract: node.content ?? undefined,
  }
}

function computeClusters(
  rawNodes: RawNode[],
  rawEdges: RawEdge[],
): { clusters: Map<string, number>; sizes: number[] } {
  const parent = new Map<string, string>()
  for (const n of rawNodes) {
    parent.set(n.id, n.id)
  }
  const find = (id: string): string => {
    let cur = id
    while ((parent.get(cur) ?? cur) !== cur) {
      const next = parent.get(cur) ?? cur
      parent.set(cur, parent.get(next) ?? next)
      cur = parent.get(cur) ?? cur
    }
    return cur
  }
  const union = (a: string, b: string): void => {
    const ra = find(a)
    const rb = find(b)
    if (ra !== rb) {
      parent.set(ra, rb)
    }
  }
  for (const e of rawEdges) {
    if (parent.has(e.f) && parent.has(e.t)) {
      union(e.f, e.t)
    }
  }
  const counts = new Map<string, number>()
  for (const n of rawNodes) {
    const r = find(n.id)
    counts.set(r, (counts.get(r) ?? 0) + 1)
  }
  const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1])
  const rootIndex = new Map<string, number>()
  const sizes: number[] = []
  ordered.forEach(([root, count], i) => {
    rootIndex.set(root, i)
    sizes.push(count)
  })
  const clusters = new Map<string, number>()
  for (const n of rawNodes) {
    clusters.set(n.id, rootIndex.get(find(n.id)) ?? 0)
  }
  return { clusters, sizes }
}

function clusterCenters(sizes: number[], w: number, h: number): ClusterCenter[] {
  if (!sizes.length) {
    return []
  }
  const cx = w / 2
  const cy = h / 2
  if (sizes.length === 1) {
    return [{ x: cx, y: cy, size: sizes[0] }]
  }
  const golden = Math.PI * (3 - Math.sqrt(5))
  const margin = Math.min(w, h) * 0.16
  const maxRadius = Math.max(Math.min(w, h) / 2 - margin, 60)
  const total = sizes.length
  return sizes.map((size, i) => {
    if (i === 0) {
      return { x: cx, y: cy, size }
    }
    const t = Math.sqrt(i / Math.max(total - 1, 1))
    const r = t * maxRadius
    const a = i * golden
    return { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r, size }
  })
}

function buildSim(rawNodes: RawNode[], rawEdges: RawEdge[], w: number, h: number): SimNode[] {
  const degree = new Map<string, number>()
  for (const e of rawEdges) {
    degree.set(e.f, (degree.get(e.f) ?? 0) + 1)
    degree.set(e.t, (degree.get(e.t) ?? 0) + 1)
  }
  const { clusters, sizes } = computeClusters(rawNodes, rawEdges)
  const centers = clusterCenters(sizes, w, h)
  const fallback: ClusterCenter = { x: w / 2, y: h / 2, size: 1 }
  return rawNodes.map((n, i) => {
    const cluster = clusters.get(n.id) ?? 0
    const center = centers[cluster] ?? fallback
    const localCount = Math.max(sizes[cluster] ?? 1, 1)
    const angle = (Math.PI * 2 * i) / localCount + (i % 2 === 0 ? 0 : 0.4)
    const spread = 60 + Math.sqrt(localCount) * 22
    const ringRadius = spread + (i % 5) * 18 + Math.random() * 14
    const deg = degree.get(n.id) ?? 0
    const base = 14
    const radius = base + Math.min(deg, 10) * 2.6
    return {
      ...n,
      x: center.x + Math.cos(angle) * ringRadius,
      y: center.y + Math.sin(angle) * ringRadius,
      vx: 0,
      vy: 0,
      radius,
      degree: deg,
      cluster,
    }
  })
}

function step(nodes: SimNode[], edges: RawEdge[], w: number, h: number, alpha: number): void {
  if (!nodes.length) {
    return
  }
  const cx = w / 2
  const cy = h / 2
  const map = new Map(nodes.map((n) => [n.id, n]))

  let maxCluster = 0
  for (const n of nodes) {
    if (n.cluster > maxCluster) {
      maxCluster = n.cluster
    }
  }
  const sizes = new Array<number>(maxCluster + 1).fill(0)
  for (const n of nodes) {
    sizes[n.cluster] += 1
  }
  const centers = clusterCenters(sizes, w, h)
  const fallback: ClusterCenter = { x: cx, y: cy, size: 1 }

  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i]
      const b = nodes[j]
      const dx = b.x - a.x
      const dy = b.y - a.y
      const distSq = Math.max(dx * dx + dy * dy, 30)
      const dist = Math.sqrt(distSq)
      const sameCluster = a.cluster === b.cluster
      const repulsion = sameCluster ? FORCE.repulsion : FORCE.repulsion * 1.6
      const force = (repulsion / distSq) * alpha
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      a.vx -= fx
      a.vy -= fy
      b.vx += fx
      b.vy += fy
    }
  }

  for (const e of edges) {
    const a = map.get(e.f)
    const b = map.get(e.t)
    if (!a || !b) {
      continue
    }
    const dx = b.x - a.x
    const dy = b.y - a.y
    const dist = Math.sqrt(dx * dx + dy * dy) || 0.1
    const delta = dist - FORCE.springLength
    const force = delta * FORCE.springStrength * alpha
    const fx = (dx / dist) * force
    const fy = (dy / dist) * force
    a.vx += fx
    a.vy += fy
    b.vx -= fx
    b.vy -= fy
  }

  for (const n of nodes) {
    const center = centers[n.cluster] ?? fallback
    const localPull = FORCE.centerStrength * (centers.length > 1 ? 1.4 : 1)
    n.vx += (center.x - n.x) * localPull * alpha
    n.vy += (center.y - n.y) * localPull * alpha
    if (centers.length > 1) {
      n.vx += (cx - n.x) * FORCE.centerStrength * 0.18 * alpha
      n.vy += (cy - n.y) * FORCE.centerStrength * 0.18 * alpha
    }
  }

  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i]
      const b = nodes[j]
      const dx = b.x - a.x
      const dy = b.y - a.y
      const minDist = a.radius + b.radius + FORCE.collisionPadding
      const distSq = dx * dx + dy * dy
      if (distSq < minDist * minDist && distSq > 0.001) {
        const dist = Math.sqrt(distSq)
        const overlap = (minDist - dist) / 2
        const px = (dx / dist) * overlap
        const py = (dy / dist) * overlap
        a.x -= px
        a.y -= py
        b.x += px
        b.y += py
      }
    }
  }

  for (const n of nodes) {
    n.vx *= FORCE.damping
    n.vy *= FORCE.damping
    const speed = Math.hypot(n.vx, n.vy)
    if (speed > FORCE.maxVelocity) {
      n.vx = (n.vx / speed) * FORCE.maxVelocity
      n.vy = (n.vy / speed) * FORCE.maxVelocity
    }
    n.x += n.vx
    n.y += n.vy
    const margin = n.radius + 18
    n.x = Math.max(margin, Math.min(w - margin, n.x))
    n.y = Math.max(margin, Math.min(h - margin, n.y))
  }
}

function curvedPath(ax: number, ay: number, bx: number, by: number, lift: number): string {
  const dx = bx - ax
  const dy = by - ay
  const dist = Math.hypot(dx, dy) || 1
  const nx = -dy / dist
  const ny = dx / dist
  const offset = lift * Math.min(28, dist * 0.18)
  const cpx = (ax + bx) / 2 + nx * offset
  const cpy = (ay + by) / 2 + ny * offset
  return `M ${ax.toFixed(1)} ${ay.toFixed(1)} Q ${cpx.toFixed(1)} ${cpy.toFixed(1)} ${bx.toFixed(1)} ${by.toFixed(1)}`
}

type GraphSource = 'loading' | 'database' | 'seed'

export default function KnowledgeGarden() {
  const [rawNodes, setRawNodes] = useState<RawNode[]>([])
  const [rawEdges, setRawEdges] = useState<RawEdge[]>([])
  const [positions, setPositions] = useState<SimNode[]>([])
  const [selId, setSelId] = useState<string | null>(null)
  const [hov, setHov] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [size, setSize] = useState({ w: 800, h: 600 })
  const [graphSource, setGraphSource] = useState<GraphSource>('loading')

  const canvasRef = useRef<HTMLDivElement | null>(null)
  const simRef = useRef<SimNode[]>([])
  const alphaRef = useRef(1)
  const sizeRef = useRef(size)
  const edgesRef = useRef<RawEdge[]>([])
  const frameRef = useRef<number | null>(null)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatScrollRef = useRef<HTMLDivElement | null>(null)
  const [pendingSave, setPendingSave] = useState<{ message: ChatMessage; proposed: KnowledgeNode; edges: KnowledgeEdge[] } | null>(null)
  const [saveSubmitting, setSaveSubmitting] = useState(false)
  const [toast, setToast] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    sizeRef.current = size
  }, [size])

  useEffect(() => {
    edgesRef.current = rawEdges
  }, [rawEdges])

  useEffect(() => {
    const el = canvasRef.current
    if (!el) {
      return
    }
    const update = (): void => {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.height > 0) {
        setSize({ w: r.width, h: r.height })
      }
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!rawNodes.length) {
      simRef.current = []
      setPositions([])
      return
    }
    simRef.current = buildSim(rawNodes, rawEdges, sizeRef.current.w, sizeRef.current.h)
    alphaRef.current = 1
    setPositions(simRef.current.map((n) => ({ ...n })))
  }, [rawNodes, rawEdges])

  useEffect(() => {
    const loop = (): void => {
      if (alphaRef.current > 0.0035 && simRef.current.length) {
        step(simRef.current, edgesRef.current, sizeRef.current.w, sizeRef.current.h, alphaRef.current)
        alphaRef.current *= 0.992
        setPositions(simRef.current.map((n) => ({ ...n })))
      }
      frameRef.current = requestAnimationFrame(loop)
    }
    frameRef.current = requestAnimationFrame(loop)
    return () => {
      if (frameRef.current != null) {
        cancelAnimationFrame(frameRef.current)
      }
    }
  }, [])

  const reheat = useCallback((amount = 0.35) => {
    alphaRef.current = Math.max(alphaRef.current, amount)
  }, [])

  const applySeedFallback = useCallback((): void => {
    setRawNodes(seedNodes)
    setRawEdges(seedEdges)
    setSelId((prev) => prev ?? seedNodes[0]?.id ?? null)
    setGraphSource('seed')
  }, [])

  const reloadGraph = useCallback(async (): Promise<void> => {
    setGraphSource((prev) => (prev === 'loading' ? prev : 'loading'))
    try {
      const data = await fetchKnowledgeGraph({ status: 'active' })
      if (!data.nodes.length) {
        applySeedFallback()
        return
      }
      const mapped = data.nodes.slice(0, 80).map(mapApiNode)
      const visible = new Set(mapped.map((n) => n.id))
      const edges: RawEdge[] = data.edges
        .filter((e) => visible.has(e.source_id) && visible.has(e.target_id))
        .map((e) => ({ f: e.source_id, t: e.target_id }))
      setRawNodes(mapped)
      setRawEdges(edges)
      setSelId((prev) => (prev && visible.has(prev) ? prev : mapped[0]?.id ?? null))
      setGraphSource('database')
    } catch {
      applySeedFallback()
    }
  }, [applySeedFallback])

  useEffect(() => {
    void reloadGraph()
  }, [reloadGraph])

  useEffect(() => {
    chatScrollRef.current?.scrollTo({ top: chatScrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>()
    for (const e of rawEdges) {
      if (!map.has(e.f)) {
        map.set(e.f, new Set())
      }
      if (!map.has(e.t)) {
        map.set(e.t, new Set())
      }
      map.get(e.f)?.add(e.t)
      map.get(e.t)?.add(e.f)
    }
    return map
  }, [rawEdges])

  const nodeIndex = useMemo(() => {
    const m = new Map<string, SimNode>()
    for (const n of positions) {
      m.set(n.id, n)
    }
    return m
  }, [positions])

  const focusId = hov ?? selId
  const focusNeighbors = useMemo(() => {
    if (!focusId) {
      return null
    }
    const set = new Set<string>([focusId])
    adjacency.get(focusId)?.forEach((id) => set.add(id))
    return set
  }, [adjacency, focusId])

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) {
      return new Set(positions.map((n) => n.id))
    }
    const set = new Set<string>()
    for (const n of positions) {
      if (n.id.toLowerCase().includes(q) || (n.title ?? '').toLowerCase().includes(q)) {
        set.add(n.id)
      }
    }
    return set
  }, [filter, positions])

  const selectedNode = focusId ? nodeIndex.get(focusId) ?? null : null
  const selectedConnections = useMemo(() => {
    if (!selId) {
      return [] as { id: string; label: string; type: GraphNodeType }[]
    }
    const set = adjacency.get(selId)
    if (!set) {
      return []
    }
    const out: { id: string; label: string; type: GraphNodeType }[] = []
    for (const id of set) {
      const n = nodeIndex.get(id)
      if (n) {
        out.push({ id, label: n.title ?? id, type: n.type })
      }
    }
    return out
  }, [adjacency, nodeIndex, selId])

  const focusFromCitation = useCallback(
    (citation: KnowledgeChatCitation) => {
      if (nodeIndex.has(citation.node_id)) {
        setSelId(citation.node_id)
        reheat(0.25)
      }
    },
    [nodeIndex, reheat],
  )

  const handleSubmit = async (event?: React.FormEvent): Promise<void> => {
    if (event) {
      event.preventDefault()
    }
    const trimmed = chatInput.trim()
    if (!trimmed || chatLoading) {
      return
    }
    const userMsg: ChatMessage = { id: makeId(), role: 'user', content: trimmed }
    setMessages((prev) => [...prev, userMsg])
    setChatInput('')
    setChatLoading(true)
    try {
      const response: KnowledgeChatResponse = await askKnowledgeChat({ query: trimmed, top_k: 6 })
      const assistant: ChatMessage = {
        id: makeId(),
        role: 'assistant',
        content: response.answer,
        citations: response.citations,
        proposed: response.proposed_save,
        proposedEdges: response.proposed_edges ?? [],
        saveState: 'idle',
      }
      setMessages((prev) => [...prev, assistant])
    } catch (err) {
      const assistant: ChatMessage = {
        id: makeId(),
        role: 'assistant',
        content: err instanceof Error ? err.message : 'Chat failed.',
      }
      setMessages((prev) => [...prev, assistant])
    } finally {
      setChatLoading(false)
    }
  }

  const showToast = useCallback((kind: 'success' | 'error', text: string) => {
    setToast({ kind, text })
    window.setTimeout(() => setToast(null), 3000)
  }, [])

  const openSaveDialog = (message: ChatMessage): void => {
    if (!message.proposed) {
      return
    }
    setPendingSave({ message, proposed: message.proposed, edges: message.proposedEdges ?? [] })
  }
  const closeSaveDialog = (): void => {
    if (saveSubmitting) {
      return
    }
    setPendingSave(null)
  }

  const persistSave = async (): Promise<void> => {
    if (!pendingSave) {
      return
    }
    setSaveSubmitting(true)
    try {
      const proposal = await proposeKnowledgeSave({ nodes: [pendingSave.proposed], edges: pendingSave.edges })
      const result = await confirmKnowledgeProposal(proposal.id)
      setMessages((prev) =>
        prev.map((m) => (m.id === pendingSave.message.id ? { ...m, saveState: 'saved' as const } : m)),
      )
      showToast('success', `Gespeichert · ${result.inserted_nodes} neu, ${result.merged_nodes} dedupliziert`)
      setPendingSave(null)
      void reloadGraph()
    } catch (err) {
      showToast('error', err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaveSubmitting(false)
    }
  }

  const dismissProposal = (message: ChatMessage): void => {
    if (!message.proposed) {
      return
    }
    // Reject ist eine reine UI-Entscheidung -- wir muessen die Proposal NICHT
    // erst in der DB anlegen, nur um sie sofort zu rejecten. Das vermeidet
    // unnoetige Muell-Rows in `knowledge_proposals`.
    setMessages((prev) => prev.map((m) => (m.id === message.id ? { ...m, saveState: 'rejected' as const } : m)))
  }

  return (
    <div className="kg" id="knowledge-garden-page">
      <div className="kg__canvas" ref={canvasRef}>
        <div className="kg__dotbg" />

        {graphSource === 'loading' && (
          <div className="kg__status kg__status--loading" role="status" aria-live="polite">
            <span className="material-symbols-outlined kg__status-icon" aria-hidden>hourglass_top</span>
            <span className="font-data-mono">Loading Knowledge Graph…</span>
          </div>
        )}
        {graphSource === 'seed' && (
          <div className="kg__status kg__status--seed" role="status">
            <span className="material-symbols-outlined kg__status-icon" aria-hidden>info</span>
            <span className="font-data-mono">Demo graph — accept a draft to see real nodes.</span>
          </div>
        )}

        <div className="kg__ctrl" id="graph-controls">
          <div className="kg__ctrl-inner">
            <button className="kg__btn" title="Reset Layout" onClick={() => { reheat(1); }}>
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>auto_fix_high</span>
            </button>
            <button className="kg__btn" title="Reload data" onClick={() => void reloadGraph()}>
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>refresh</span>
            </button>
          </div>
        </div>

        <div className="kg__legend" id="graph-legend">
          <h4 className="font-label-caps" style={{ color: 'var(--on-surface-variant)', marginBottom: 12 }}>Node Legend</h4>
          {[
            { c: 'var(--primary)', l: 'Experiments / Insights' },
            { c: 'var(--tertiary)', l: 'Corrections / Claims' },
            { c: 'var(--secondary)', l: 'Reagents / Literature' },
          ].map((x) => (
            <div key={x.l} className="kg__legend-item">
              <div className="kg__legend-dot" style={{ background: x.c }} />
              <span className="font-data-mono" style={{ fontSize: 12, color: 'var(--on-surface)' }}>{x.l}</span>
            </div>
          ))}
        </div>

        <svg className="kg__edges" width={size.w} height={size.h} aria-hidden>
          <defs>
            <linearGradient id="edge-active" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.95" />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity="0.55" />
            </linearGradient>
          </defs>
          {rawEdges.map((e, i) => {
            const a = nodeIndex.get(e.f)
            const b = nodeIndex.get(e.t)
            if (!a || !b) {
              return null
            }
            const lift = i % 2 === 0 ? 1 : -1
            const path = curvedPath(a.x, a.y, b.x, b.y, lift)
            const isFocus = focusId != null && (e.f === focusId || e.t === focusId)
            const isDim = focusId != null && !isFocus
            const stroke = isFocus ? 'url(#edge-active)' : 'var(--outline-variant)'
            const opacity = isDim ? 0.1 : isFocus ? 0.95 : e.h ? 0.6 : 0.4
            const width = isFocus ? 1.6 : e.h ? 1.4 : 1
            return (
              <path
                key={`${e.f}-${e.t}-${i}`}
                d={path}
                fill="none"
                stroke={stroke}
                strokeWidth={width}
                strokeOpacity={opacity}
                strokeLinecap="round"
                style={{ transition: 'stroke-opacity 0.18s ease, stroke-width 0.18s ease' }}
              />
            )
          })}
        </svg>

        {positions.map((n) => {
          const c = tc[n.type] ?? tc.entity
          const isSel = selId === n.id
          const isHov = hov === n.id
          const isFocused = isSel || isHov
          const isInFocus = !focusNeighbors || focusNeighbors.has(n.id)
          const isVisible = filtered.has(n.id)
          const dim = !isVisible || (focusId != null && !isInFocus)
          const diameter = n.radius * 2
          return (
            <button
              key={n.id}
              type="button"
              className={`kg__node ${isSel ? 'kg__node--sel' : ''} ${dim ? 'kg__node--dim' : ''} ${isFocused ? 'kg__node--focus' : ''}`}
              style={{
                left: n.x,
                top: n.y,
                width: diameter,
                height: diameter,
                ['--kg-node-color' as string]: c.dot,
              }}
              onClick={() => {
                setSelId(n.id)
                reheat(0.18)
              }}
              onMouseEnter={() => setHov(n.id)}
              onMouseLeave={() => setHov(null)}
              id={`node-${n.id}`}
              aria-label={n.title ?? n.id}
            >
              <span className="kg__node-core" />
              {n.degree >= 4 && (
                <span className="material-symbols-outlined kg__node-icon" aria-hidden>{c.icon}</span>
              )}
              {isFocused && (
                <span className="kg__node-label font-data-mono">
                  {(n.title ?? n.id).slice(0, 32)}
                </span>
              )}
            </button>
          )
        })}
      </div>

      <div className="kg__panel" id="node-detail-panel">
        <div className="kg__filter">
          <div className="kg__filter-in">
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: 'var(--outline)' }}>filter_list</span>
            <input className="font-data-mono" placeholder="Filter nodes..." value={filter} onChange={(e) => setFilter(e.target.value)} id="node-filter-input" />
          </div>
        </div>
        <div className="kg__detail">
          <div className="kg__dh">
            <div className="kg__di">
              <span className="material-symbols-outlined" style={{ fontSize: 20, color: 'var(--on-surface-variant)' }}>{tc[selectedNode?.type ?? 'entity']?.icon ?? 'science'}</span>
            </div>
            <div>
              <h3 className="font-headline-md" style={{ color: 'var(--on-surface)', marginBottom: 4, fontWeight: 500, letterSpacing: '-0.01em' }}>
                {selectedNode?.title ?? selectedNode?.id ?? '—'}
              </h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <span className="kg__tag kg__tag--blue font-label-caps">{(selectedNode?.id ?? '').slice(0, 18)}</span>
                <span className="kg__tag kg__tag--neutral font-label-caps">{tc[selectedNode?.type ?? 'entity'].label}</span>
              </div>
            </div>
          </div>
          <div className="kg__db">
            <div className="kg__stats">
              <div>
                <div className="font-label-caps" style={{ color: 'var(--outline)', fontSize: 10, marginBottom: 4 }}>Confidence</div>
                <div className="font-data-mono" style={{ color: 'var(--on-surface)', fontSize: 18 }}>{selectedNode?.conf ?? 'N/A'}</div>
              </div>
              <div>
                <div className="font-label-caps" style={{ color: 'var(--outline)', fontSize: 10, marginBottom: 4 }}>Times Applied</div>
                <div className="font-data-mono" style={{ color: 'var(--on-surface)', fontSize: 18 }}>{selectedNode?.applied ?? 0}</div>
              </div>
            </div>
            <div>
              <h4 className="font-label-caps" style={{ color: 'var(--outline)', marginBottom: 8 }}>ABSTRACT / CONTENT</h4>
              <p className="font-body-base" style={{ color: 'var(--on-surface)', fontSize: 14 }}>{selectedNode?.abstract ?? 'No content available.'}</p>
            </div>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 12 }}>
                <h4 className="font-label-caps" style={{ color: 'var(--outline)' }}>PRIMARY CONNECTIONS</h4>
                <span className="font-data-mono" style={{ color: 'var(--on-surface-variant)', fontSize: 12 }}>
                  {selectedConnections.length} Direct
                </span>
              </div>
              <div className="kg__conn-list">
                {selectedConnections.length === 0 ? (
                  <div className="kg__conn-empty font-body-base">Keine direkten Kanten.</div>
                ) : (
                  selectedConnections.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="kg__conn-item"
                      onClick={() => {
                        setSelId(c.id)
                        reheat(0.2)
                      }}
                    >
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: tc[c.type]?.dot ?? 'var(--outline)', flexShrink: 0 }} />
                      <span className="font-data-mono" style={{ color: 'var(--on-surface)', fontSize: 13 }}>{c.label}</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <aside className="kg__chat" id="knowledge-chat-panel">
        <div className="kg__chat-h">
          <div className="kg__chat-title">
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>forum</span>
            <span className="font-label-caps">ASK YOUR LAB</span>
          </div>
          {messages.length > 0 && (
            <button className="kg__btn" title="Clear chat" onClick={() => setMessages([])}>
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>refresh</span>
            </button>
          )}
        </div>
        <div className="kg__chat-list" ref={chatScrollRef}>
          {messages.length === 0 ? (
            <div className="kg__chat-empty">
              <span className="material-symbols-outlined" style={{ fontSize: 36, color: 'var(--outline)' }}>auto_awesome</span>
              <p className="font-body-base" style={{ color: 'var(--on-surface-variant)' }}>
                Ask your lab. Answers come with citations and can be saved as graph nodes.
              </p>
            </div>
          ) : (
            messages.map((message) => (
              <div key={message.id} className={`kg__msg kg__msg--${message.role}`}>
                <div className="kg__bubble font-body-base">{message.content}</div>
                {message.role === 'assistant' && message.citations && message.citations.length > 0 && (
                  <div className="kg__cites">
                    {message.citations.map((citation) => (
                      <button
                        key={citation.node_id}
                        type="button"
                        className="kg__cite font-data-mono"
                        onClick={() => focusFromCitation(citation)}
                        title={citation.title}
                      >
                        <span className="kg__cite-dot" style={{ background: tc[citation.node_type as GraphNodeType]?.dot ?? 'var(--outline)' }} />
                        {citation.node_id.slice(0, 22)}
                      </button>
                    ))}
                  </div>
                )}
                {message.role === 'assistant' && message.proposed && (
                  <div className="kg__msg-actions">
                    {message.saveState === 'saved' ? (
                      <span className="kg__msg-action kg__msg-action--saved">
                        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>check</span>
                        Gespeichert
                      </span>
                    ) : message.saveState === 'rejected' ? (
                      <span className="kg__msg-action">
                        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>close</span>
                        Verworfen
                      </span>
                    ) : (
                      <>
                        <button type="button" className="kg__msg-action" onClick={() => openSaveDialog(message)}>
                          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>bookmark_add</span>
                          Save to Graph
                        </button>
                        <button type="button" className="kg__msg-action" onClick={() => dismissProposal(message)}>
                          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>delete_sweep</span>
                          Verwerfen
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
          {chatLoading && (
            <div className="kg__msg kg__msg--assistant">
              <div className="kg__bubble font-body-base" style={{ color: 'var(--on-surface-variant)' }}>
                <span className="material-symbols-outlined" style={{ fontSize: 14, verticalAlign: '-2px', marginRight: 6 }}>hourglass_top</span>
                Searching the Knowledge Graph…
              </div>
            </div>
          )}
        </div>
        <form className="kg__chat-form" onSubmit={(e) => void handleSubmit(e)}>
          <textarea
            className="kg__chat-input"
            value={chatInput}
            placeholder="Ask your knowledge…"
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void handleSubmit()
              }
            }}
            rows={1}
            id="knowledge-chat-input"
          />
          <button type="submit" className="kg__chat-send" disabled={chatLoading || !chatInput.trim()} title="Send">
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>send</span>
          </button>
        </form>
      </aside>

      {pendingSave && (
        <div className="kg__dialog-backdrop" onClick={closeSaveDialog}>
          <div className="kg__dialog animate-fadeIn" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="kg__dialog-h">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className="material-symbols-outlined" style={{ color: 'var(--primary)' }}>bookmark_add</span>
                <h3 className="font-headline-md" style={{ fontSize: 16, fontWeight: 500, color: 'var(--on-surface)' }}>Save Insight to Graph</h3>
              </div>
              <button className="kg__btn" onClick={closeSaveDialog} title="Close">
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>close</span>
              </button>
            </div>
            <div className="kg__dialog-body">
              <div className="kg__dialog-row">
                <label>Title</label>
                <div className="kg__dialog-text">{pendingSave.proposed.title}</div>
              </div>
              <div className="kg__dialog-row">
                <label>Type · Confidence</label>
                <div className="font-data-mono" style={{ fontSize: 12, color: 'var(--on-surface-variant)' }}>
                  {pendingSave.proposed.node_type} · {Math.round(pendingSave.proposed.confidence * 100)}%
                </div>
              </div>
              {pendingSave.proposed.content && (
                <div className="kg__dialog-row">
                  <label>Content</label>
                  <div className="kg__dialog-text">{pendingSave.proposed.content}</div>
                </div>
              )}
              {pendingSave.message.citations && pendingSave.message.citations.length > 0 && (
                <div className="kg__dialog-row">
                  <label>Sources ({pendingSave.message.citations.length})</label>
                  <div className="kg__cites">
                    {pendingSave.message.citations.map((c) => (
                      <span key={c.node_id} className="kg__cite font-data-mono">
                        <span className="kg__cite-dot" style={{ background: tc[c.node_type as GraphNodeType]?.dot ?? 'var(--outline)' }} />
                        {c.node_id.slice(0, 22)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="kg__dialog-actions">
              <button className="kg__dialog-btn kg__dialog-btn--ghost font-label-caps" onClick={closeSaveDialog} disabled={saveSubmitting}>Cancel</button>
              <button className="kg__dialog-btn kg__dialog-btn--primary font-label-caps" onClick={() => void persistSave()} disabled={saveSubmitting}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>{saveSubmitting ? 'hourglass_top' : 'check'}</span>
                {saveSubmitting ? 'Saving…' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`kg__toast kg__toast--${toast.kind}`} role="status">
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>{toast.kind === 'success' ? 'check_circle' : 'error'}</span>
          <span className="font-body-base">{toast.text}</span>
        </div>
      )}
    </div>
  )
}
