import { useEffect, useRef, useState } from "react"
import type { Health, Task } from "./types"

const POLL_MS = 5000

interface HubState {
  tasks: Task[]
  health: Health | null
  error: string | null
  lastFetched: Date | null
}

export function useTasks(): HubState {
  const [state, setState] = useState<HubState>({
    tasks: [],
    health: null,
    error: null,
    lastFetched: null,
  })
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const [tasksRes, healthRes] = await Promise.all([
          fetch("/tasks"),
          fetch("/health"),
        ])
        if (!tasksRes.ok) throw new Error(`GET /tasks → ${tasksRes.status}`)
        const tasks = (await tasksRes.json()) as Task[]
        const health = healthRes.ok ? ((await healthRes.json()) as Health) : null
        if (!cancelled)
          setState({ tasks, health, error: null, lastFetched: new Date() })
      } catch (e) {
        if (!cancelled)
          setState((s) => ({ ...s, error: e instanceof Error ? e.message : String(e) }))
      } finally {
        if (!cancelled) timer.current = window.setTimeout(poll, POLL_MS)
      }
    }

    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer.current)
    }
  }, [])

  return state
}

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const s = Math.round((Date.now() - then) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function isStaleClaim(task: Task): boolean {
  if (task.status !== "in-progress") return false
  const updated = new Date(task.updated_at).getTime()
  return !Number.isNaN(updated) && Date.now() - updated > 2 * 3600 * 1000
}
