import type {
  AcceptDraftResponse,
  AgentEvent,
  AgentMessage,
  BackendAgent,
  ExperimentPlan,
  ExperimentRun,
  ExperimentSummary,
  KnowledgeCandidates,
  KnowledgeChatResponse,
  KnowledgeEdge,
  KnowledgeNode,
  KnowledgeProposal,
  RunGraphSnapshot,
  StreamEvent,
} from '../types/plan'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
const PLAN_STORAGE_KEY = 'ai-scientist-plan'
const LATEST_PLAN_KEY = 'ai-scientist-latest-plan-id'
const ACTIVE_RUN_KEY = 'ai-scientist-active-run-id'

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
  localStorage.setItem(LATEST_PLAN_KEY, plan.plan_id)
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

export function getLatestPlanId(): string | null {
  return localStorage.getItem(LATEST_PLAN_KEY)
}

export function getActiveRunId(): string | null {
  return localStorage.getItem(ACTIVE_RUN_KEY)
}

export function setActiveRunId(runId: string | null): void {
  if (runId) {
    localStorage.setItem(ACTIVE_RUN_KEY, runId)
  } else {
    localStorage.removeItem(ACTIVE_RUN_KEY)
  }
}

export async function generatePlan(request: GeneratePlanRequest): Promise<ExperimentPlan> {
  const response = await fetch(`${API_BASE_URL}/generate-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error('Plan generation failed')
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
    throw new Error('Could not start run')
  }
  return (await response.json()) as StartRunResponse
}

export async function listRecentPlans(): Promise<ExperimentSummary[]> {
  const response = await fetch(`${API_BASE_URL}/plans`)
  if (!response.ok) {
    throw new Error('Could not load plans')
  }
  return (await response.json()) as ExperimentSummary[]
}

export async function fetchBackendAgents(): Promise<BackendAgent[]> {
  const response = await fetch(`${API_BASE_URL}/agents`)
  if (!response.ok) {
    throw new Error('Could not load agents')
  }
  const data = (await response.json()) as { agents: BackendAgent[] }
  return data.agents ?? []
}

export async function getRun(runId: string): Promise<ExperimentRun> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}`)
  if (!response.ok) {
    throw new Error('Could not load run status')
  }
  return (await response.json()) as ExperimentRun
}

export async function getRunEvents(runId: string): Promise<AgentEvent[]> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/events`)
  if (!response.ok) {
    throw new Error('Could not load run events')
  }
  return (await response.json()) as AgentEvent[]
}

export async function getRunGraph(runId: string): Promise<RunGraphSnapshot> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/graph`)
  if (!response.ok) {
    throw new Error('Could not load run graph')
  }
  return (await response.json()) as RunGraphSnapshot
}

export async function getRunMessages(runId: string): Promise<AgentMessage[]> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/messages`)
  if (!response.ok) {
    throw new Error('Could not load run messages')
  }
  return (await response.json()) as AgentMessage[]
}

export async function getRunPlan(runId: string): Promise<ExperimentPlan> {
  const response = await fetch(`${API_BASE_URL}/runs/${runId}/plan`)
  if (!response.ok) {
    throw new Error('Plan for run is not available')
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
    throw new Error('Could not start SSE stream')
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

// === Knowledge Graph API ====================================================

export async function acceptPlanDraft(planId: string): Promise<AcceptDraftResponse> {
  const response = await fetch(`${API_BASE_URL}/plans/${planId}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!response.ok) {
    throw new Error('Could not accept draft')
  }
  return (await response.json()) as AcceptDraftResponse
}

export interface KnowledgeFetchOptions {
  status?: 'active' | 'pending' | 'archived' | 'all'
}

export interface KnowledgeListResponse {
  nodes: KnowledgeNode[]
  edges: KnowledgeEdge[]
}

export async function fetchKnowledgeGraph(
  options: KnowledgeFetchOptions = {},
): Promise<KnowledgeListResponse> {
  const params = new URLSearchParams()
  if (options.status) {
    params.set('status', options.status)
  }
  const query = params.toString()
  const response = await fetch(
    `${API_BASE_URL}/knowledge${query ? `?${query}` : ''}`,
  )
  if (!response.ok) {
    throw new Error('Could not load knowledge graph')
  }
  return (await response.json()) as KnowledgeListResponse
}

export interface KnowledgeChatRequest {
  query: string
  top_k?: number
  experiment_type?: string
}

export async function askKnowledgeChat(
  request: KnowledgeChatRequest,
): Promise<KnowledgeChatResponse> {
  const response = await fetch(`${API_BASE_URL}/knowledge/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error('Knowledge chat failed')
  }
  return (await response.json()) as KnowledgeChatResponse
}

export async function proposeKnowledgeSave(
  payload: KnowledgeCandidates,
  options?: { sourceRef?: string | null; createdBy?: string },
): Promise<KnowledgeProposal> {
  const response = await fetch(`${API_BASE_URL}/knowledge/proposals`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kind: 'chat_insight',
      source_ref: options?.sourceRef ?? null,
      payload,
      created_by: options?.createdBy ?? 'chat-user',
    }),
  })
  if (!response.ok) {
    throw new Error('Could not create proposal')
  }
  return (await response.json()) as KnowledgeProposal
}

export async function confirmKnowledgeProposal(
  proposalId: string,
): Promise<AcceptDraftResponse> {
  const response = await fetch(
    `${API_BASE_URL}/knowledge/proposals/${proposalId}/confirm`,
    { method: 'POST' },
  )
  if (!response.ok) {
    throw new Error('Could not confirm proposal')
  }
  return (await response.json()) as AcceptDraftResponse
}

export async function rejectKnowledgeProposal(
  proposalId: string,
): Promise<{ status: string; id: string }> {
  const response = await fetch(
    `${API_BASE_URL}/knowledge/proposals/${proposalId}/reject`,
    { method: 'POST' },
  )
  if (!response.ok) {
    throw new Error('Could not reject proposal')
  }
  return (await response.json()) as { status: string; id: string }
}
