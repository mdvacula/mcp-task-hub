import { useEffect, useState } from "react"
import type { AgentRun } from "./types"

interface Fetched {
  key: string
  runs: AgentRun[]
  error: string | null
}

/** Per-run agent metrics for one project and phase (drain | spec). Results are
 * remembered per query key; "loading" is derived, not stored. */
export function useRuns(
  project: string | null,
  phase: "drain" | "spec",
  since: string | null,
) {
  const key = project ? `${project}|${phase}|${since ?? ""}` : ""
  const [fetched, setFetched] = useState<Fetched | null>(null)

  useEffect(() => {
    if (!project) return
    let cancelled = false
    const q = new URLSearchParams({ project, phase })
    if (since) q.set("since", since)
    fetch(`/metrics/runs?${q}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`GET /metrics/runs → ${r.status}`)
        return (await r.json()) as AgentRun[]
      })
      .then((runs) => !cancelled && setFetched({ key, runs, error: null }))
      .catch(
        (e) =>
          !cancelled &&
          setFetched({
            key,
            runs: [],
            error: e instanceof Error ? e.message : String(e),
          }),
      )
    return () => {
      cancelled = true
    }
  }, [project, phase, since, key])

  const current = key && fetched?.key === key ? fetched : null
  return {
    runs: current?.runs ?? [],
    error: current?.error ?? null,
    loading: !!key && !current,
  }
}
