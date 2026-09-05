import { useMemo, useState } from "react"
import { Eye, FileText } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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
import { hubSummary, type HubSummary } from "@/lib/hubSummary"
import { CHANGE_FILES } from "@/lib/spec"
import { relativeTime } from "@/lib/useTasks"
import type { SpecChange, Task } from "@/lib/types"

const ALL = "__all__"

function HubBadge({ summary }: { summary: HubSummary | null }) {
  if (!summary)
    return (
      <Badge
        variant="outline"
        className="gap-1 border-amber-300 bg-amber-100 font-normal text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"
      >
        <Eye className="size-3" aria-hidden />
        Pending review
      </Badge>
    )
  const { total, byStatus } = summary
  if (byStatus.completed === total)
    return (
      <Badge
        variant="outline"
        className="border-emerald-300 bg-emerald-100 font-normal text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
      >
        Done · {total} tasks
      </Badge>
    )
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-xs tabular-nums">
      <Badge variant="outline" className="font-normal">
        {byStatus.completed}/{total} done
      </Badge>
      {byStatus["in-progress"] > 0 && (
        <span className="text-sky-700 dark:text-sky-300">
          {byStatus["in-progress"]} running
        </span>
      )}
      {byStatus.blocked > 0 && (
        <span className="text-red-700 dark:text-red-300">
          {byStatus.blocked} blocked
        </span>
      )}
    </span>
  )
}

interface Props {
  specs: SpecChange[]
  tasks: Task[]
  error: string | null
  onOpen: (project: string, path: string) => void
}

export function SpecsView({ specs, tasks, error, onOpen }: Props) {
  const [project, setProject] = useState(ALL)
  const [search, setSearch] = useState("")
  const [pendingOnly, setPendingOnly] = useState(false)

  const projects = useMemo(
    () => [...new Set(specs.map((s) => s.project))].sort(),
    [specs],
  )

  const rows = useMemo(
    () =>
      specs.map((s) => ({ ...s, hub: hubSummary(tasks, s.project, s.change) })),
    [specs, tasks],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (project !== ALL && r.project !== project) return false
      if (pendingOnly && r.hub !== null) return false
      if (q && !`${r.project} ${r.change}`.toLowerCase().includes(q))
        return false
      return true
    })
  }, [rows, project, pendingOnly, search])

  const pendingCount = rows.filter(
    (r) => r.hub === null && (project === ALL || r.project === project),
  ).length

  function openDefault(r: SpecChange) {
    const names = new Set(r.files.map((f) => f.name))
    const first = CHANGE_FILES.find((f) => names.has(f)) ?? r.files[0].name
    onOpen(r.project, `openspec/changes/${r.change}/${first}`)
  }

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
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search change…"
          className="w-56"
        />
        <Button
          variant={pendingOnly ? "secondary" : "outline"}
          size="sm"
          onClick={() => setPendingOnly((v) => !v)}
          aria-pressed={pendingOnly}
          className="gap-1"
        >
          <Eye className="size-3.5" aria-hidden />
          Pending review
          <span className="tabular-nums text-muted-foreground">
            {pendingCount}
          </span>
        </Button>
        <div className="ml-auto text-sm text-muted-foreground tabular-nums">
          {filtered.length} shown
        </div>
      </div>

      {error && (
        <p className="mb-3 text-sm text-red-700 dark:text-red-300">
          {error} — is the repos dir mounted into the hub (HUB_REPOS_DIR)?
        </p>
      )}

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Change</TableHead>
              <TableHead className="hidden md:table-cell">Project</TableHead>
              <TableHead className="hidden sm:table-cell">Artifacts</TableHead>
              <TableHead>Hub</TableHead>
              <TableHead className="text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-10 text-center text-muted-foreground"
                >
                  {specs.length === 0
                    ? "No openspec/changes/ found under the mounted repos."
                    : "No changes match."}
                </TableCell>
              </TableRow>
            )}
            {filtered.map((r) => {
              const names = new Set(r.files.map((f) => f.name))
              const extra = r.files.filter(
                (f) => !(CHANGE_FILES as readonly string[]).includes(f.name),
              ).length
              return (
                <TableRow
                  key={`${r.project}/${r.change}`}
                  onClick={() => openDefault(r)}
                  className="cursor-pointer"
                >
                  <TableCell className="max-w-72">
                    <div className="flex items-center gap-1.5 font-medium">
                      <FileText
                        className="size-3.5 shrink-0 text-muted-foreground"
                        aria-hidden
                      />
                      <span className="truncate">{r.change}</span>
                    </div>
                    <div className="truncate font-mono text-xs text-muted-foreground md:hidden">
                      {r.project}
                    </div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    {r.project}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <div className="flex flex-wrap gap-1">
                      {CHANGE_FILES.map((f) => (
                        <button
                          key={f}
                          type="button"
                          disabled={!names.has(f)}
                          onClick={(e) => {
                            e.stopPropagation()
                            onOpen(
                              r.project,
                              `openspec/changes/${r.change}/${f}`,
                            )
                          }}
                          className={`rounded border px-1.5 py-0.5 font-mono text-[11px] ${
                            names.has(f)
                              ? "hover:bg-accent"
                              : "border-dashed text-muted-foreground/50"
                          }`}
                          title={names.has(f) ? `open ${f}` : `${f} missing`}
                        >
                          {f.replace(".md", "")}
                        </button>
                      ))}
                      {extra > 0 && (
                        <span className="self-center text-xs text-muted-foreground">
                          +{extra} more
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <HubBadge summary={r.hub} />
                  </TableCell>
                  <TableCell className="text-right text-sm text-muted-foreground tabular-nums">
                    {relativeTime(new Date(r.updated * 1000).toISOString())}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Card>
    </>
  )
}
