export type TaskStatus =
  "pending" | "in-progress" | "in-review" | "completed" | "blocked"

export interface StatusNote {
  at: string
  status: string
  note: string
}

export interface AgentMetrics {
  reads?: number
  graft?: number
  edits?: number
  turns?: number
  in_tok?: number
  out_tok?: number
  wall_s?: number
  model?: string | null
}

export interface RunMetrics {
  worker?: AgentMetrics
  reviewer?: AgentMetrics
  fix?: AgentMetrics[]
}

export interface TimelineEntry {
  at: string
  from: string | null
  to: string
}

export interface RunLogEntry {
  metrics?: RunMetrics
  landed?: string | null
  outcome?: string
  at?: string
  agent?: string
  model?: string
  tier?: string
  commitRange?: string
  gates?: string
  verdict?: string
  findings?: unknown
  fixCycles?: number
  summary?: string
  [key: string]: unknown
}

export interface TaskMetadata {
  change?: string
  specRef?: string
  priority?: "P0" | "P1" | "P2"
  type?: string
  tier?: "haiku" | "sonnet" | "opus"
  blockedBy?: string[]
  blocks?: string[]
  statusNotes?: StatusNote[]
  runLog?: RunLogEntry[]
  timeline?: TimelineEntry[]
  notes?: string
  [key: string]: unknown
}

export interface Task {
  id: string
  title: string
  status: TaskStatus
  project: string | null
  metadata: TaskMetadata
  created_at: string
  updated_at: string
}

export interface Health {
  status: string
  task_count: number
}

export interface SpecFile {
  name: string
  size: number
  mtime: number // epoch seconds
}

/** One openspec/changes/<change>/ directory on disk (from GET /specs). */
export interface SpecChange {
  project: string
  change: string
  files: SpecFile[]
  updated: number // epoch seconds, newest file
}

/** One row of GET /metrics: a project/change benchmark group. */
export interface MetricsGroup {
  project: string
  change: string
  tasks: number
  byStatus: Partial<Record<TaskStatus, number>>
  runs: number
  landed: number
  passFirst: number
  reviewed: number
  fixCycles: number
  blockedRuns: number
  graftRuns: number
  metricRuns: number
  byTier: Record<
    string,
    { runs: number; passFirst: number; reviewed: number; fixCycles: number }
  >
  median: {
    reads: number | null
    graftCalls: number | null
    inTok: number | null
    outTok: number | null
    wallS: number | null
    reviewerInTok: number | null
    leadS: number | null
    reviewToLandS: number | null
  }
}

/** One row of GET /metrics/runs: a subagent run measured from its transcript. */
export interface AgentRun {
  role: string
  task: string | null
  wf: string | null
  change: string | null
  reads: number
  graft: number
  edits: number
  tools: number
  turns: number
  in_tok: number
  out_tok: number
  model: string | null
  start: string | null
  end: string | null
  wall_s: number | null
}
