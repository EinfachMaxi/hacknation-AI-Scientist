import type {
  AgentEvent,
  AgentMessage,
  ExperimentPlan,
  ExperimentRun,
  RunGraphSnapshot,
  StreamEvent,
} from '../types/plan'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
const PLAN_STORAGE_KEY = 'ai-scientist-plan'

export interface GeneratePlanRequest {
  prompt: string
  experiment_type?: string
  use_mock?: boolean
}

export interface StartRunRequest {
  prompt: string
  experiment_type?: string
  use_mock?: boolean
}

export interface StartRunResponse {
  run_id: string
  status: 'pending' | 'running'
}

export function savePlan(plan: ExperimentPlan): void {
  localStorage.setItem(`${PLAN_STORAGE_KEY}:${plan.plan_id}`, JSON.stringify(plan))
}

export function loadPlan(planId: string): ExperimentPlan | null {
  const raw = localStorage.getItem(`${PLAN_STORAGE_KEY}:${planId}`)
  if (!raw) {
    return null
  }
  try {
    return JSON.parse(raw) as ExperimentPlan
  } catch {
    return null
  }
}

export async function generatePlan(request: GeneratePlanRequest): Promise<ExperimentPlan> {
  const response = await fetch(`${API_BASE_URL}/generate-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error('Plan-Generierung fehlgeschlagen')
  }
  const plan = (await response.json()) as ExperimentPlan
  savePlan(plan)
  return plan
}

export async function startRun(request: StartRunRequest): Promise<StartRunResponse> {
  const response = await fetch(`${API_BASE_URL}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error('Run konnte nicht gestartet werden')
  }
  return (await response.json()) as StartRunResponse
}

export async function getRun(runId: string): Promise<ExperimentRun> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}`)
  if (!response.ok) {
    throw new Error('Run Status konnte nicht geladen werden')
  }
  return (await response.json()) as ExperimentRun
}

export async function getRunEvents(runId: string): Promise<AgentEvent[]> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/events`)
  if (!response.ok) {
    throw new Error('Run Events konnten nicht geladen werden')
  }
  return (await response.json()) as AgentEvent[]
}

export async function getRunGraph(runId: string): Promise<RunGraphSnapshot> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/graph`)
  if (!response.ok) {
    throw new Error('Run Graph konnte nicht geladen werden')
  }
  return (await response.json()) as RunGraphSnapshot
}

export async function getRunMessages(runId: string): Promise<AgentMessage[]> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/messages`)
  if (!response.ok) {
    throw new Error('Run Messages konnten nicht geladen werden')
  }
  return (await response.json()) as AgentMessage[]
}

export async function getRunPlan(runId: string): Promise<ExperimentPlan> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/plan`)
  if (!response.ok) {
    throw new Error('Plan fuer Run nicht verfuegbar')
  }
  const plan = (await response.json()) as ExperimentPlan
  savePlan(plan)
  return plan
}

export async function streamGeneratePlan(
  request: GeneratePlanRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal
): Promise<ExperimentPlan | null> {
  const response = await fetch(`${API_BASE_URL}/generate-plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error('SSE-Stream konnte nicht gestartet werden')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalPlan: ExperimentPlan | null = null

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''

    for (const chunk of chunks) {
      if (!chunk.startsWith('data: ')) {
        continue
      }
      const data = chunk.slice(6)
      try {
        const event = JSON.parse(data) as StreamEvent
        onEvent(event)
        if (event.phase === 'complete' && event.payload.plan) {
          finalPlan = event.payload.plan as ExperimentPlan
          savePlan(finalPlan)
        }
      } catch {
        // ignore malformed chunks
      }
    }
  }

  return finalPlan
}
