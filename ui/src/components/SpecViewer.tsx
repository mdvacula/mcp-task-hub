import { useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { ExternalLink, FileText } from "lucide-react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  CHANGE_FILES,
  changeDir,
  headings,
  parseSpecRefs,
  resolveAnchor,
  specUrl,
  type Resolved,
} from "@/lib/spec"

interface Props {
  project: string
  specRef: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

type Load =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; text: string }

const HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"] as const
const LOADING: Load = { state: "loading" }

export function SpecViewer({ project, specRef, open, onOpenChange }: Props) {
  // The parent keys this component by task, so `path` starts at the task's
  // own file and only the sibling buttons move it.
  const refs = useMemo(() => parseSpecRefs(specRef), [specRef])
  const [path, setPath] = useState(refs[0]?.path ?? specRef)
  // Fetch results are remembered per file; "loading" is derived, not stored.
  const [fetched, setFetched] = useState<{ key: string; load: Load } | null>(
    null,
  )
  const body = useRef<HTMLDivElement>(null)

  const key = `${project}/${path}`
  const load: Load = fetched?.key === key ? fetched.load : LOADING

  useEffect(() => {
    if (!open) return
    let cancelled = false
    fetch(specUrl(project, path))
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
        return r.text()
      })
      .then(
        (text) =>
          !cancelled && setFetched({ key, load: { state: "ready", text } }),
      )
      .catch(
        (e) =>
          !cancelled &&
          setFetched({
            key,
            load: {
              state: "error",
              message: e instanceof Error ? e.message : String(e),
            },
          }),
      )
    return () => {
      cancelled = true
    }
  }, [open, project, path, key])

  const hs = useMemo(
    () => (load.state === "ready" ? headings(load.text) : []),
    [load],
  )
  const ids = useMemo(() => new Map(hs.map((h) => [h.line, h.id])), [hs])

  // The sections this task cites in the file currently shown, resolved
  // against its real headings (planner-written anchors are approximate).
  const targets = useMemo<{ anchor: string; hit: Resolved | null }[]>(
    () =>
      refs
        .filter((r) => r.path === path && r.anchor)
        .map((r) => ({ anchor: r.anchor, hit: resolveAnchor(r.anchor, hs) })),
    [refs, path, hs],
  )

  // Headings carry GitHub-style ids so the specRef fragment resolves; the id
  // comes from the source line, so no render-time counters are needed.
  const components = useMemo<Components>(() => {
    const out: Components = {}
    for (const tag of HEADINGS) {
      out[tag] = ({ node, children, ...props }) => {
        const line = node?.position?.start.line
        const Tag = tag
        return (
          <Tag id={line ? ids.get(line) : undefined} {...props}>
            {children}
          </Tag>
        )
      }
    }
    out.a = ({ node: _n, href, children, ...props }) => (
      <a href={href} target="_blank" rel="noreferrer" {...props}>
        {children}
      </a>
    )
    return out
  }, [ids])

  const hits = useMemo(
    () => targets.filter((t) => t.hit).map((t) => t.hit!),
    [targets],
  )
  const misses = targets.filter((t) => !t.hit).map((t) => t.anchor)

  // Scroll to and highlight the cited sections once the markdown is in.
  useEffect(() => {
    if (load.state !== "ready" || !body.current) return
    const root = body.current
    root
      .querySelectorAll(".spec-target")
      .forEach((el) => el.classList.remove("spec-target"))
    if (!hits.length) {
      root.scrollTop = 0
      return
    }
    let first: HTMLElement | null = null
    for (const { heading } of hits) {
      const el = root.querySelector<HTMLElement>(`#${CSS.escape(heading.id)}`)
      if (!el) continue
      first ??= el
      let node: Element | null = el
      while (node) {
        node.classList.add("spec-target")
        node = node.nextElementSibling
        const t = node?.tagName.toLowerCase() ?? ""
        if (/^h[1-6]$/.test(t) && Number(t[1]) <= heading.level) break
      }
    }
    first?.scrollIntoView({ block: "start" })
  }, [load, hits])

  const dir = changeDir(path)
  const fileName = path.split("/").pop() ?? path
  // Top-level sections for the jump menu (long tasks.md files on a phone).
  const sections = useMemo(() => hs.filter((h) => h.level <= 2 && h.id), [hs])
  function jumpTo(id: string) {
    body.current
      ?.querySelector<HTMLElement>(`#${CSS.escape(id)}`)
      ?.scrollIntoView({ block: "start" })
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* The sheet base forces w-3/4 on the right side, which on a phone leaves a
          sliver of page and a cramped header — take the full width there. */}
      <SheetContent className="flex w-full flex-col gap-0 p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-3xl">
        <SheetHeader className="gap-1 border-b px-4 py-3 sm:px-6">
          <SheetTitle className="flex items-center gap-2 pr-8 text-base">
            <FileText
              className="size-4 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <span className="truncate">{fileName}</span>
            {dir && (
              <span className="truncate text-sm font-normal text-muted-foreground">
                · {dir.split("/").pop()}
              </span>
            )}
          </SheetTitle>
          <SheetDescription className="hidden font-mono text-xs break-all sm:block">
            {project}/{path}
            {targets.map((t) => (
              <span key={t.anchor} className="text-foreground">
                {" "}
                #{t.anchor}
              </span>
            ))}
          </SheetDescription>
          <div className="-mx-1 flex items-center gap-1 overflow-x-auto px-1 pt-1 [scrollbar-width:none]">
            {dir &&
              CHANGE_FILES.map((f) => {
                const p = `${dir}/${f}`
                return (
                  <Button
                    key={f}
                    size="sm"
                    variant={p === path ? "secondary" : "ghost"}
                    className="h-8 shrink-0 px-2.5 text-xs"
                    onClick={() => setPath(p)}
                  >
                    {f.replace(".md", "")}
                  </Button>
                )
              })}
            {sections.length > 1 && (
              <Select onValueChange={jumpTo}>
                <SelectTrigger
                  className="h-8 w-40 shrink-0 text-xs sm:w-56"
                  aria-label="Jump to section"
                >
                  <SelectValue placeholder="Jump to section…" />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  {sections.map((h) => (
                    <SelectItem key={h.id} value={h.id} className="text-xs">
                      {h.text}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <a
              href={specUrl(project, path)}
              target="_blank"
              rel="noreferrer"
              className="ml-auto inline-flex shrink-0 items-center gap-1 px-1 text-xs text-muted-foreground hover:text-foreground"
            >
              raw <ExternalLink className="size-3" aria-hidden />
            </a>
          </div>
          <div className="flex flex-wrap items-center gap-1 text-xs">
            {load.state === "ready" && hits.length > 0 && (
              <span className="text-xs text-muted-foreground">
                · {hits.length === 1 ? "section" : `${hits.length} sections`}{" "}
                highlighted
                {hits.some((h) => !h.exact) && (
                  <>
                    {" "}
                    (matched to{" "}
                    {hits
                      .filter((h) => !h.exact)
                      .map((h) => `“${h.heading.text}”`)
                      .join(", ")}
                    )
                  </>
                )}
              </span>
            )}
            {load.state === "ready" && misses.length > 0 && (
              <span className="text-xs text-amber-700 dark:text-amber-400">
                · no heading matches #{misses.join(", #")}
              </span>
            )}
          </div>
        </SheetHeader>
        <div
          ref={body}
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6"
        >
          {load.state === "loading" && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          {load.state === "error" && (
            <p className="text-sm text-red-700 dark:text-red-300">
              Could not load {path}: {load.message}
              {load.message.startsWith("404") && (
                <span className="block text-muted-foreground">
                  The file must exist under the project's openspec/ tree on the
                  box (and the hub must have the repos dir mounted).
                </span>
              )}
            </p>
          )}
          {load.state === "ready" && (
            <article className="spec-md">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={components}
              >
                {load.text}
              </ReactMarkdown>
            </article>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
