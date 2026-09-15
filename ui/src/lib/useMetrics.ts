import { useEffect, useState } from "react"
import type { MetricsGroup } from "./types"

const POLL_MS = 20000

export function useMetrics(enabled: boolean): {
  groups: MetricsGroup[]
  error: string | null
} {
  const [groups, setGroups] = useState<MetricsGroup[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    let timer: number | undefined

    async function poll() {
      try {
        const res = await fetch("/metrics")
        if (!res.ok) throw new Error(`GET /metrics → ${res.status}`)
        const data = (await res.json()) as MetricsGroup[]
        if (!cancelled) {
          setGroups(data)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, POLL_MS)
      }
    }
    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [enabled])

  return { groups, error }
}
