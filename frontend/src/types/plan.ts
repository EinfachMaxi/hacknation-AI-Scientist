export type NoveltySignal = 'exact_match' | 'similar_work_exists' | 'not_found'
export type ReviewSeverity = 'warning' | 'error'

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
  agent: string
  phase: 'starting' | 'progress' | 'complete' | 'error'
  status: 'started' | 'completed' | 'failed'
  payload: Record<string, unknown>
  timestamp?: string
}

export interface AgentEvent {
  event_id: string
  run_id: string
  sequence: number
  agent: string
  phase: 'starting' | 'progress' | 'complete' | 'error'
  status: 'started' | 'completed' | 'failed'
  message?: string
  payload: Record<string, unknown>
  from_agent?: string
  to_agent?: string
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
