export type TaskStatus = "pending" | "in-progress" | "completed" | "blocked"

export interface StatusNote {
  at: string
  status: string
  note: string
}

export interface RunLogEntry {
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
