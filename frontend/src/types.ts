/** WebSocket event types streamed from the backend. */

export type AgentName = 'planner' | 'search' | 'writer' | 'critic'

export type PipelineStatus = 'idle' | 'running' | 'done' | 'error'

export interface AgentStartEvent {
  type: 'agent_start'
  agent: AgentName
  message: string
}

export interface AgentDoneEvent {
  type: 'agent_done'
  agent: AgentName
  message: string
  data: Record<string, unknown>
}

export interface AgentErrorEvent {
  type: 'agent_error'
  agent: AgentName
  message: string
  error: string
}

export interface PipelineStartEvent {
  type: 'pipeline_start'
  message: string
}

export interface CompleteEvent {
  type: 'complete'
  report: string
  quality_score: number
  revision_count: number
  search_queries: string[]
  word_count: number
  source_count: number
  status: string
}

export interface ErrorEvent {
  type: 'error'
  message: string
}

export type WsEvent =
  | PipelineStartEvent
  | AgentStartEvent
  | AgentDoneEvent
  | AgentErrorEvent
  | CompleteEvent
  | ErrorEvent

export interface AgentStep {
  agent: AgentName
  status: 'waiting' | 'running' | 'done' | 'error'
  message: string
  data?: Record<string, unknown>
}

export interface ResearchResult {
  report: string
  quality_score: number
  revision_count: number
  search_queries: string[]
  word_count: number
  source_count: number
}
