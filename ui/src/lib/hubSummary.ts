import type { Task, TaskStatus } from "./types"

export interface HubSummary {
  total: number
  byStatus: Record<TaskStatus, number>
}

/** What the hub knows about a change: nothing (= pending human review) or a task tally. */
export function hubSummary(
  tasks: Task[],
  project: string,
  change: string,
): HubSummary | null {
  const mine = tasks.filter(
    (t) => t.project === project && t.metadata.change === change,
  )
  if (mine.length === 0) return null
  const byStatus: Record<TaskStatus, number> = {
    pending: 0,
    "in-progress": 0,
    "in-review": 0,
    blocked: 0,
    completed: 0,
  }
  for (const t of mine) byStatus[t.status] = (byStatus[t.status] ?? 0) + 1
  return { total: mine.length, byStatus }
}
