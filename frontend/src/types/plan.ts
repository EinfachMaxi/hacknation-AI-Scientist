export type NoveltySignal = 'exact_match' | 'similar_work_exists' | 'not_found'
export type ReviewSeverity = 'info' | 'warning' | 'error'
export type AgentId = 'orchestrator' | 'literature' | 'protocol' | 'materials' | 'budget' | 'timeline' | 'review'
export type AgentPhase = 'starting' | 'progress' | 'complete' | 'error'
export type AgentExecutionStatus = 'started' | 'completed' | 'failed'

export interface Reference {
  title: string
  authors?: string
  year?: number
  journal?: string
  doi?: string
  similarity?: string
  key_difference?: string
  url?: string
}

export interface LiteratureQC {
  novelty_signal: NoveltySignal
  references: Reference[]
  summary: string
}

export interface ProtocolStep {
  step_number: number
  action: string
  duration: string
  details: string
  notes?: string
  source?: string
}

export interface Protocol {
  steps: ProtocolStep[]
  total_duration: string
  controls: string[]
}

export interface MaterialItem {
  item: string
  catalog_number: string
  supplier: string
  quantity: string
  unit_price: number
  currency: string
  total_price: number
  storage?: string
  verification: 'verified' | 'suggested_verify'
  verified_via?: 'local_catalog' | 'web'
  match_score?: number
  verification_snippet?: string
  source_url?: string
}

export interface Budget {
  total: number
  currency: string
  breakdown: {
    reagents: number
    consumables: number
    equipment_usage: number
  }
  notes?: string
}

export interface TimelinePhase {
  phase: string
  duration: string
  tasks: string[]
  dependencies: string[]
  start_day: number
}

export interface Timeline {
  phases: TimelinePhase[]
  total_duration: string
}

export interface Validation {
  success_criteria: string[]
  controls: string[]
  statistical_plan: string
}

export interface ReviewIssue {
  severity: ReviewSeverity
  message: string
  path: string
}

export interface ExperimentPlan {
  plan_id: string
  title: string
  hypothesis: string
  literature_qc: LiteratureQC
  protocol: Protocol
  materials: MaterialItem[]
  budget: Budget
  timeline: Timeline
  validation: Validation
  review_issues: ReviewIssue[]
  metadata: Record<string, unknown>
  generated_at: string
  knowledge_nodes_extracted: string[]
}

export interface StreamEvent {
  agent: AgentId
  phase: AgentPhase
  status: AgentExecutionStatus
  payload: Record<string, unknown>
  timestamp?: string
}

export interface AgentEvent {
  event_id: string
  run_id: string
  sequence: number
  agent: AgentId
  phase: AgentPhase
  status: AgentExecutionStatus
  message?: string
  payload: Record<string, unknown>
  from_agent?: AgentId
  to_agent?: AgentId
  timestamp: string
}

export interface ExperimentRun {
  run_id: string
  hypothesis: string
  experiment_type?: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  plan_id?: string
  error_message?: string
  created_at: string
  updated_at: string
}

export interface AgentMessage {
  id?: string
  run_id: string
  sequence: number
  message_type: 'request' | 'response' | 'handoff' | 'broadcast' | 'system'
  from_agent_id?: string
  to_agent_id?: string
  from_agent?: string
  to_agent?: string
  subject?: string
  message?: string
  payload: Record<string, unknown>
  created_at: string
}

export interface GraphNodeTooling {
  allowed_tools: string[]
  tool_calls_count: number
  last_tool_status?: string
}

export interface GraphNodeRationale {
  agent_key: string
  score: number
  matched_capabilities: string[]
  matched_keywords: string[]
  inclusion_reason: string
  depends_on: string[]
}

export interface GraphNode {
  id: string
  label: string
  role: string
  personality?: string
  state: 'pending' | 'ready' | 'running' | 'completed' | 'failed' | 'skipped'
  progress_pct: number
  tooling?: GraphNodeTooling
  rationale?: GraphNodeRationale | null
}

export interface GraphEdge {
  from: string
  to: string
  state: 'idle' | 'active' | 'completed' | 'failed'
  last_message_type?: string
  last_activity_at?: string
  last_tool_activity_at?: string
  last_tool_name?: string
  last_tool_error?: string
}

export interface RunGraphSnapshot {
  nodes: GraphNode[]
  edges: GraphEdge[]
  meta: {
    run_status: 'pending' | 'running' | 'completed' | 'failed'
    updated_at: string
    version: string
    tool_calling_enabled: boolean
  }
}

export type KnowledgeNodeType =
  | 'experiment'
  | 'correction'
  | 'reagent'
  | 'claim'
  | 'entity'
  | 'literature'
  | 'chat_insight'

export type KnowledgeNodeStatus = 'pending' | 'active' | 'archived'
export type KnowledgeSourceType =
  | 'plan_draft'
  | 'user_correction'
  | 'chat_insight'
  | 'literature'
  | 'manual'

export interface KnowledgeNode {
  id: string
  title: string
  node_type: KnowledgeNodeType
  experiment_type?: string | null
  content?: string | null
  metadata: Record<string, unknown>
  tags: string[]
  status: KnowledgeNodeStatus
  source_type: KnowledgeSourceType
  source_ref?: string | null
  confidence: number
  times_applied: number
  created_by?: string | null
  created_at?: string | null
}

export interface KnowledgeEdge {
  source_id: string
  target_id: string
  relationship_type: string
  weight?: number
  source_type?: KnowledgeSourceType
  source_ref?: string | null
}

export interface KnowledgeCandidates {
  nodes: KnowledgeNode[]
  edges: KnowledgeEdge[]
}

export interface AcceptDraftResponse {
  plan_id: string
  inserted_nodes: number
  merged_nodes: number
  inserted_edges: number
  candidate_summary: Record<string, number>
}

export interface KnowledgeChatCitation {
  node_id: string
  title: string
  node_type: KnowledgeNodeType
  score: number
}

export interface KnowledgeChatResponse {
  answer: string
  citations: KnowledgeChatCitation[]
  proposed_save: KnowledgeNode | null
  proposed_edges?: KnowledgeEdge[]
}

export interface ExperimentSummary {
  plan_id: string
  title: string
  hypothesis: string
  generated_at: string
}

export interface BackendAgent {
  id: string | null
  key: string
  name: string
  role: string
  personality: string
  capabilities: string[]
  is_active: boolean
  sort_order: number
  metadata: Record<string, unknown>
}

export interface KnowledgeProposal {
  id: string
  kind: 'plan_draft' | 'chat_insight'
  source_ref?: string | null
  payload: KnowledgeCandidates
  status: 'pending' | 'confirmed' | 'rejected'
  created_by?: string | null
  created_at?: string | null
  decided_at?: string | null
}
