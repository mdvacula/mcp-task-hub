#!/usr/bin/env node
// Check that every specRef in the hub resolves to a heading in the file it
// names, using the same slug + fuzzy-match logic the UI's spec viewer uses.
//   node ui/scripts/check-spec-anchors.mts [--hub http://127.0.0.1:8050] [--repos ~/code]
// Prints exact / fuzzy / miss counts and lists misses (and fuzzy matches with -v).
import { readFileSync, existsSync } from "node:fs"
import { headings, parseSpecRefs, resolveAnchor } from "../src/lib/spec.ts"

const arg = (k: string, d: string) => {
  const i = process.argv.indexOf(k)
  return i === -1 ? d : process.argv[i + 1]
}
const HUB = arg("--hub", "http://127.0.0.1:8050")
const REPOS = arg("--repos", `${process.env.HOME}/code`)
const VERBOSE = process.argv.includes("-v")

interface Task { project: string | null; metadata: { specRef?: string } }
const tasks = (await (await fetch(`${HUB}/tasks`)).json()) as Task[]

let exact = 0, fuzzy = 0, miss = 0, noFile = 0
const cache = new Map<string, ReturnType<typeof headings>>()
for (const t of tasks) {
  if (!t.project || !t.metadata.specRef) continue
  for (const r of parseSpecRefs(t.metadata.specRef)) {
    const file = `${REPOS}/${t.project}/${r.path}`
    if (!existsSync(file)) { noFile++; console.log(`NOFILE ${t.project} ${r.path}`); continue }
    if (!r.anchor) continue
    let hs = cache.get(file)
    if (!hs) { hs = headings(readFileSync(file, "utf8")); cache.set(file, hs) }
    const hit = resolveAnchor(r.anchor, hs)
    if (!hit) { miss++; console.log(`MISS   ${t.project} ${r.path}#${r.anchor}`) }
    else if (hit.exact) exact++
    else { fuzzy++; if (VERBOSE) console.log(`fuzzy  #${r.anchor}  →  ${hit.heading.text}`) }
  }
}
console.log({ exact, fuzzy, miss, noFile })
process.exit(miss || noFile ? 1 : 0)
