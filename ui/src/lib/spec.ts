// Helpers for the specRef viewer. A specRef is repo-relative:
//   openspec/changes/<change>/tasks.md#3-some-heading
// The server serves the file at /spec/<project>/<path>; the fragment is a
// GitHub-style heading slug that we resolve client-side.

export interface SpecRef {
  path: string
  anchor: string
}

export function parseSpecRef(ref: string): SpecRef {
  const i = ref.indexOf("#")
  if (i === -1) return { path: ref.trim(), anchor: "" }
  let anchor = ref.slice(i + 1).trim()
  try {
    anchor = decodeURIComponent(anchor)
  } catch {
    /* keep raw */
  }
  return { path: ref.slice(0, i).trim(), anchor }
}

/** A task may cite several sections: "…/tasks.md#3-foo ; …/tasks.md#4-bar". */
export function parseSpecRefs(ref: string): SpecRef[] {
  return ref
    .split(/\s*;\s*|\s*,\s+(?=openspec\/)/)
    .map((r) => r.trim())
    .filter(Boolean)
    .map(parseSpecRef)
}

export function specUrl(project: string, path: string): string {
  return `/spec/${encodeURIComponent(project)}/${path
    .split("/")
    .map(encodeURIComponent)
    .join("/")}`
}

/** GitHub's heading slug: lowercase, drop punctuation, spaces → hyphens. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\p{L}\p{N}\s_-]/gu, "")
    .replace(/\s/g, "-")
}

/** Strip the inline markdown that would otherwise leak into a slug. */
function headingText(raw: string): string {
  return raw
    .replace(/\s+#+\s*$/, "") // closing hashes
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1") // links / images → text
    .replace(/`([^`]*)`/g, "$1")
    .replace(/[*_~]+/g, "")
    .trim()
}

export interface Heading {
  line: number
  level: number
  id: string
  text: string
}

/**
 * Every heading with the id GitHub would give it (same `-1`, `-2`
 * de-duplication), keyed by source line so the renderer can look ids up from
 * the hast node position without keeping render-time state.
 */
export function headings(markdown: string): Heading[] {
  const out: Heading[] = []
  const seen = new Map<string, number>()
  let inFence = false
  markdown.split("\n").forEach((line, i) => {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence
      return
    }
    if (inFence) return
    const m = /^ {0,3}(#{1,6})\s+(.*)$/.exec(line)
    if (!m) return
    const text = headingText(m[2])
    const base = slugify(text)
    const n = seen.get(base) ?? 0
    seen.set(base, n + 1)
    out.push({ line: i + 1, level: m[1].length, id: n === 0 ? base : `${base}-${n}`, text })
  })
  return out
}

export function headingIdsByLine(markdown: string): Map<number, string> {
  return new Map(headings(markdown).map((h) => [h.line, h.id]))
}

export interface Resolved {
  heading: Heading
  exact: boolean
}

const tokens = (s: string) => new Set(s.split("-").filter(Boolean))

function overlap(a: Set<string>, b: Set<string>): number {
  let n = 0
  for (const t of a) if (b.has(t)) n++
  return n / Math.max(1, Math.min(a.size, b.size))
}

/**
 * Find the heading a specRef fragment means. Planners write these by hand, so
 * besides the exact slug we accept the bare section number (`#3`), a number
 * plus a paraphrase (`#3-archive-as-superseded` for "3. Archive-as-superseded
 * (proposal status blocks)"), and a close token overlap. Numbered matches
 * prefer the shallowest heading (the `## N.` section over its `### N.x`).
 */
export function resolveAnchor(anchor: string, hs: Heading[]): Resolved | null {
  if (!anchor) return null
  const exact = hs.find((h) => h.id === anchor)
  if (exact) return { heading: exact, exact: true }

  const want = tokens(anchor)
  const num = /^(\d+)(?:-|$)/.exec(anchor)?.[1]
  if (num) {
    const numbered = hs.filter((h) => h.id === num || h.id.startsWith(`${num}-`))
    if (numbered.length) {
      const top = Math.min(...numbered.map((h) => h.level))
      const cands = numbered.filter((h) => h.level === top)
      cands.sort((a, b) => overlap(want, tokens(b.id)) - overlap(want, tokens(a.id)))
      return { heading: cands[0], exact: false }
    }
  }

  let best: Heading | null = null
  let bestScore = 0
  for (const h of hs) {
    const score = overlap(want, tokens(h.id))
    if (score > bestScore) {
      bestScore = score
      best = h
    }
  }
  return best && bestScore >= 0.6 ? { heading: best, exact: false } : null
}

/** Sibling artifacts of an OpenSpec change dir, for quick switching. */
export const CHANGE_FILES = ["proposal.md", "design.md", "tasks.md"] as const

export function changeDir(path: string): string | null {
  const m = /^(openspec\/changes\/[^/]+)\/[^/]+\.md$/.exec(path)
  return m ? m[1] : null
}
