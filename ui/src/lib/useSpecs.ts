import { useEffect, useState } from "react"
import type { SpecChange } from "./types"

const POLL_MS = 15000

export function useSpecs(enabled: boolean): {
  specs: SpecChange[]
  error: string | null
} {
  const [specs, setSpecs] = useState<SpecChange[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    let timer: number | undefined

    async function poll() {
      try {
        const res = await fetch("/specs")
        if (!res.ok) throw new Error(`GET /specs → ${res.status}`)
        const data = (await res.json()) as SpecChange[]
        if (!cancelled) {
          setSpecs(data)
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

  return { specs, error }
}
