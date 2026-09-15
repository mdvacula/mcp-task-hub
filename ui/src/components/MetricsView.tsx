import { useMemo, useState } from "react"

import { Card } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { MetricsGroup } from "@/lib/types"

const ALL = "__all__"

const fmtK = (n: number | null) =>
  n === null
    ? "—"
    : n >= 1000
      ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}k`
      : `${Math.round(n)}`
const fmtDur = (s: number | null) => {
  if (s === null) return "—"
  if (s < 90) return `${Math.round(s)}s`
  if (s < 5400) return `${Math.round(s / 60)}m`
  return `${(s / 3600).toFixed(1)}h`
}
const pct = (n: number, d: number) =>
  d ? `${Math.round((100 * n) / d)}%` : "—"

interface Props {
  groups: MetricsGroup[]
  error: string | null
}

/**
 * Benchmarks per change, from what the drain records on each task: run-log
 * entries (verdict, fix cycles, landed, per-agent metrics) and the status
 * timeline. Medians are per worker run; compare rows over time or across
 * settings (tier, graft) rather than single tasks.
 */
export function MetricsView({ groups, error }: Props) {
  const [project, setProject] = useState(ALL)
  const projects = useMemo(
    () => [...new Set(groups.map((g) => g.project))].sort(),
    [groups],
  )
  const rows = useMemo(
    () =>
      groups.filter(
        (g) => g.runs > 0 && (project === ALL || g.project === project),
      ),
    [groups, project],
  )

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={project} onValueChange={setProject}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Project" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All projects</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="ml-auto text-sm text-muted-foreground tabular-nums">
          {rows.length} changes with runs
        </div>
      </div>
      {error && (
        <p className="mb-3 text-sm text-red-700 dark:text-red-300">{error}</p>
      )}
      <Card className="py-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Change</TableHead>
                <TableHead
                  className="text-right"
                  title="tasks with at least one run / total tasks"
                >
                  Tasks
                </TableHead>
                <TableHead
                  className="text-right"
                  title="runLog entries (a task can have several: fix cycles, reruns)"
                >
                  Runs
                </TableHead>
                <TableHead
                  className="text-right"
                  title="runs whose lane was rebased + pushed to main"
                >
                  Landed
                </TableHead>
                <TableHead
                  className="text-right"
                  title="reviewed runs that passed with zero fix cycles"
                >
                  Pass 1st
                </TableHead>
                <TableHead className="text-right" title="total fix cycles">
                  Fixes
                </TableHead>
                <TableHead
                  className="text-right"
                  title="worker runs that made ≥1 graft call / runs with metrics"
                >
                  Graft
                </TableHead>
                <TableHead
                  className="text-right"
                  title="median read-type tool calls per worker run"
                >
                  Reads
                </TableHead>
                <TableHead
                  className="text-right"
                  title="median input tokens per worker run (all turns, cache included)"
                >
                  In tok
                </TableHead>
                <TableHead
                  className="text-right"
                  title="median wall time per worker run"
                >
                  Worker
                </TableHead>
                <TableHead
                  className="text-right"
                  title="median input tokens per reviewer run"
                >
                  Rev tok
                </TableHead>
                <TableHead
                  className="text-right"
                  title="median claim → completed (from the status timeline)"
                >
                  Lead
                </TableHead>
                <TableHead
                  className="text-right"
                  title="median in-review → completed"
                >
                  Review→land
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={13}
                    className="py-10 text-center text-muted-foreground"
                  >
                    No run-log data yet. Drains record verdicts, fix cycles,
                    landed ranges and per-agent metrics here.
                  </TableCell>
                </TableRow>
              )}
              {rows.map((g) => (
                <TableRow key={`${g.project}/${g.change}`}>
                  <TableCell className="max-w-72">
                    <div className="truncate font-medium">{g.change}</div>
                    <div className="truncate font-mono text-xs text-muted-foreground">
                      {g.project}
                      {Object.keys(g.byTier).length > 0 && (
                        <>
                          {" "}
                          ·{" "}
                          {Object.entries(g.byTier)
                            .map(([t, v]) => `${t} ${v.runs}`)
                            .join(" · ")}
                        </>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {g.tasks}
                    <div className="text-xs text-muted-foreground">
                      {g.byStatus.completed ?? 0} done
                      {(g.byStatus["in-review"] ?? 0) > 0 &&
                        ` · ${g.byStatus["in-review"]} rev`}
                      {(g.byStatus.blocked ?? 0) > 0 &&
                        ` · ${g.byStatus.blocked} blk`}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {g.runs}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {g.landed}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {pct(g.passFirst, g.reviewed)}
                    <div className="text-xs text-muted-foreground">
                      {g.passFirst}/{g.reviewed}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {g.fixCycles}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {g.metricRuns ? `${g.graftRuns}/${g.metricRuns}` : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtK(g.median.reads)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtK(g.median.inTok)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtDur(g.median.wallS)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtK(g.median.reviewerInTok)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtDur(g.median.leadS)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtDur(g.median.reviewToLandS)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
      <p className="mt-3 text-xs text-muted-foreground">
        Per-agent metrics are measured from the subagent transcripts at landing
        time (reads = Read/Grep/Glob + read-only Bash; in tok = every input
        token over the run, cache included). Rows without metrics predate that
        capture.
      </p>
    </>
  )
}
