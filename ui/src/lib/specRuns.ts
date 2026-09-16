import type { AgentRun } from "./types"

export const fmtK = (v: number) =>
  v >= 1_000_000
    ? `${(v / 1_000_000).toFixed(1)}M`
    : v >= 1000
      ? `${Math.round(v / 1000)}k`
      : `${v}`

export const SPEC_STAGES = [
  {
    key: "explore",
    label: "explore",
    roles: ["spec:code-map", "spec:conventions", "spec:constraints"],
    color: "var(--viz-1)",
  },
  {
    key: "approach",
    label: "approaches + judge",
    roles: ["spec:approach", "spec:judge"],
    color: "var(--viz-2)",
  },
  {
    key: "draft",
    label: "draft / revise",
    roles: ["spec:draft"],
    color: "var(--viz-3)",
  },
  {
    key: "critic",
    label: "critics",
    roles: ["spec:critic"],
    color: "var(--viz-4)",
  },
] as const

export interface SpecRunSummary {
  wf: string
  start: number
  change: string | null
  agents: number
  reads: number
  graft: number
  inTok: number
  outTok: number
  wallS: number
  byStage: Record<string, number>
  codeMap?: AgentRun
}

/** Group spec-phase agent runs into one row per /hub-spec workflow run. */
export function summarizeSpecRuns(runs: AgentRun[]): SpecRunSummary[] {
  const by = new Map<string, AgentRun[]>()
  for (const r of runs) {
    const k = r.wf ?? `?${r.start?.slice(0, 13)}`
    by.set(k, [...(by.get(k) ?? []), r])
  }
  return [...by.entries()]
    .map(([wf, rs]) => {
      const starts = rs
        .map((r) => (r.start ? new Date(r.start).getTime() : 0))
        .filter(Boolean)
      const ends = rs
        .map((r) => (r.end ? new Date(r.end).getTime() : 0))
        .filter(Boolean)
      const byStage: Record<string, number> = {}
      for (const s of SPEC_STAGES)
        byStage[s.key] = rs
          .filter((r) => (s.roles as readonly string[]).includes(r.role))
          .reduce((a, r) => a + r.in_tok, 0)
      return {
        wf,
        start: Math.min(...starts),
        change: rs.map((r) => r.change).find(Boolean) ?? null,
        agents: rs.length,
        reads: rs.reduce((a, r) => a + r.reads, 0),
        graft: rs.reduce((a, r) => a + r.graft, 0),
        inTok: rs.reduce((a, r) => a + r.in_tok, 0),
        outTok: rs.reduce((a, r) => a + r.out_tok, 0),
        wallS:
          starts.length && ends.length
            ? Math.round((Math.max(...ends) - Math.min(...starts)) / 1000)
            : 0,
        byStage,
        codeMap: rs.find((r) => r.role === "spec:code-map"),
      }
    })
    .sort((a, b) => a.start - b.start)
}
