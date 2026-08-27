import { useMemo, useState } from "react"
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Circle,
  CircleDashed,
  Moon,
  Sun,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Separator } from "@/components/ui/separator"
import { isStaleClaim, relativeTime, useTasks } from "@/lib/useTasks"
import type { Task, TaskStatus } from "@/lib/types"

const STATUSES: TaskStatus[] = ["pending", "in-progress", "blocked", "completed"]

const STATUS_META: Record<
  TaskStatus,
  { label: string; icon: typeof Circle; badgeClass: string }
> = {
  pending: {
    label: "Pending",
    icon: Circle,
    badgeClass: "border-border bg-muted text-muted-foreground",
  },
  "in-progress": {
    label: "In progress",
    icon: CircleDashed,
    badgeClass:
      "border-sky-300 bg-sky-100 text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-300",
  },
  blocked: {
    label: "Blocked",
    icon: Ban,
    badgeClass:
      "border-red-300 bg-red-100 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  },
  completed: {
    label: "Completed",
    icon: CheckCircle2,
    badgeClass:
      "border-emerald-300 bg-emerald-100 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300",
  },
}

const ALL = "__all__"

function StatusBadge({ status }: { status: TaskStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.pending
  const Icon = meta.icon
  return (
    <Badge variant="outline" className={`gap-1 font-normal ${meta.badgeClass}`}>
      <Icon className="size-3" aria-hidden />
      {meta.label}
    </Badge>
  )
}

function StatTile({
  status,
  count,
  active,
  onClick,
}: {
  status: TaskStatus
  count: number
  active: boolean
  onClick: () => void
}) {
  const meta = STATUS_META[status]
  const Icon = meta.icon
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      className={`cursor-pointer py-4 transition-colors hover:bg-accent ${
        active ? "border-ring" : ""
      }`}
    >
      <CardContent className="flex items-center justify-between px-4">
        <div>
          <div className="text-xs text-muted-foreground">{meta.label}</div>
          <div className="text-2xl font-semibold tabular-nums">{count}</div>
        </div>
        <Icon className="size-5 text-muted-foreground" aria-hidden />
      </CardContent>
    </Card>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2 text-sm">
      <div className="text-muted-foreground">{label}</div>
      <div className="min-w-0 break-words">{children}</div>
    </div>
  )
}

export default function App() {
  const { tasks, health, error, lastFetched } = useTasks()
  const [project, setProject] = useState(ALL)
  const [change, setChange] = useState(ALL)
  const [status, setStatus] = useState(ALL)
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<Task | null>(null)
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  )

  function toggleTheme() {
    document.documentElement.classList.toggle("dark")
    setDark(document.documentElement.classList.contains("dark"))
  }

  const projects = useMemo(
    () => [...new Set(tasks.map((t) => t.project ?? "—"))].sort(),
    [tasks],
  )
  const changes = useMemo(() => {
    const scoped = project === ALL ? tasks : tasks.filter((t) => (t.project ?? "—") === project)
    return [...new Set(scoped.map((t) => t.metadata.change).filter(Boolean) as string[])].sort()
  }, [tasks, project])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return tasks.filter((t) => {
      if (project !== ALL && (t.project ?? "—") !== project) return false
      if (change !== ALL && t.metadata.change !== change) return false
      if (status !== ALL && t.status !== status) return false
      if (q && !`${t.id} ${t.title}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [tasks, project, change, status, search])

  const counts = useMemo(() => {
    const scoped = tasks.filter(
      (t) =>
        (project === ALL || (t.project ?? "—") === project) &&
        (change === ALL || t.metadata.change === change),
    )
    return Object.fromEntries(
      STATUSES.map((s) => [s, scoped.filter((t) => t.status === s).length]),
    ) as Record<TaskStatus, number>
  }, [tasks, project, change])

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Task Hub</h1>
          <p className="text-sm text-muted-foreground">
            {health ? (
              <>
                hub ok · {health.task_count} tasks
                {lastFetched && <> · updated {relativeTime(lastFetched.toISOString())}</>}
              </>
            ) : (
              "connecting…"
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <Badge variant="outline" className="gap-1 border-red-300 text-red-700 dark:border-red-900 dark:text-red-300">
              <AlertTriangle className="size-3" aria-hidden />
              {error}
            </Badge>
          )}
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
        </div>
      </header>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {STATUSES.map((s) => (
          <StatTile
            key={s}
            status={s}
            count={counts[s]}
            active={status === s}
            onClick={() => setStatus(status === s ? ALL : s)}
          />
        ))}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={project} onValueChange={(v) => { setProject(v); setChange(ALL) }}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Project" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All projects</SelectItem>
            {projects.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={change} onValueChange={setChange}>
          <SelectTrigger className="w-60"><SelectValue placeholder="Change" /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All changes</SelectItem>
            {changes.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search id or title…"
          className="w-56"
        />
        <div className="ml-auto text-sm text-muted-foreground tabular-nums">
          {filtered.length} shown
        </div>
      </div>

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Task</TableHead>
              <TableHead className="hidden md:table-cell">Project</TableHead>
              <TableHead className="hidden lg:table-cell">Change</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead className="hidden sm:table-cell">Tier</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No tasks match.
                </TableCell>
              </TableRow>
            )}
            {filtered.map((t) => {
              const stale = isStaleClaim(t)
              return (
                <TableRow
                  key={t.id}
                  onClick={() => setSelected(t)}
                  className="cursor-pointer"
                >
                  <TableCell className="max-w-72">
                    <div className="truncate font-medium">{t.title}</div>
                    <div className="truncate font-mono text-xs text-muted-foreground">{t.id}</div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">{t.project ?? "—"}</TableCell>
                  <TableCell className="hidden max-w-48 truncate lg:table-cell">
                    {t.metadata.change ?? "—"}
                  </TableCell>
                  <TableCell>{t.metadata.priority ?? "—"}</TableCell>
                  <TableCell className="hidden sm:table-cell">{t.metadata.tier ?? "—"}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge status={t.status} />
                      {stale && (
                        <span
                          className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400"
                          title="in-progress for over 2h — possibly an orphaned claim"
                        >
                          <AlertTriangle className="size-3.5" aria-hidden />
                          stale
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-sm text-muted-foreground tabular-nums">
                    {relativeTime(t.updated_at)}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Card>

      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle className="pr-8">{selected.title}</SheetTitle>
                <SheetDescription className="font-mono text-xs">{selected.id}</SheetDescription>
              </SheetHeader>
              <div className="space-y-3 px-4 pb-6">
                <DetailRow label="Status"><StatusBadge status={selected.status} /></DetailRow>
                <DetailRow label="Project">{selected.project ?? "—"}</DetailRow>
                <DetailRow label="Change">{selected.metadata.change ?? "—"}</DetailRow>
                <DetailRow label="Priority">{selected.metadata.priority ?? "—"}</DetailRow>
                <DetailRow label="Type">{selected.metadata.type ?? "—"}</DetailRow>
                <DetailRow label="Tier">{selected.metadata.tier ?? "—"}</DetailRow>
                {selected.metadata.specRef && (
                  <DetailRow label="Spec ref">
                    <span className="font-mono text-xs">{selected.metadata.specRef}</span>
                  </DetailRow>
                )}
                {(selected.metadata.blockedBy?.length ?? 0) > 0 && (
                  <DetailRow label="Blocked by">
                    <span className="font-mono text-xs">
                      {selected.metadata.blockedBy!.join(", ")}
                    </span>
                  </DetailRow>
                )}
                {(selected.metadata.blocks?.length ?? 0) > 0 && (
                  <DetailRow label="Blocks">
                    <span className="font-mono text-xs">{selected.metadata.blocks!.join(", ")}</span>
                  </DetailRow>
                )}
                <DetailRow label="Created">{new Date(selected.created_at).toLocaleString()}</DetailRow>
                <DetailRow label="Updated">{new Date(selected.updated_at).toLocaleString()}</DetailRow>

                {(selected.metadata.statusNotes?.length ?? 0) > 0 && (
                  <>
                    <Separator />
                    <h3 className="text-sm font-medium">Status notes</h3>
                    <ol className="space-y-2">
                      {selected.metadata.statusNotes!.map((n, i) => (
                        <li key={i} className="rounded-md border p-2 text-sm">
                          <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{new Date(n.at).toLocaleString()}</span>
                            <span>→ {n.status}</span>
                          </div>
                          {n.note}
                        </li>
                      ))}
                    </ol>
                  </>
                )}

                {(selected.metadata.runLog?.length ?? 0) > 0 && (
                  <>
                    <Separator />
                    <h3 className="text-sm font-medium">Run log</h3>
                    <ol className="space-y-2">
                      {selected.metadata.runLog!.map((entry, i) => (
                        <li key={i} className="rounded-md border p-2">
                          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">
                            {JSON.stringify(entry, null, 2)}
                          </pre>
                        </li>
                      ))}
                    </ol>
                  </>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
