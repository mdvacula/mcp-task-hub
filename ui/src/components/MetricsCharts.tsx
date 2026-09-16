import { useMemo } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Scatter,
  ScatterChart,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts"

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { SPEC_STAGES, type SpecRunSummary } from "@/lib/specRuns"
import type { AgentRun, MetricsGroup } from "@/lib/types"

const fmtDay = (t: number) =>
  new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" })
const fmtWhen = (t: number) =>
  new Date(t).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })

function shortTask(t: string | null) {
  if (!t) return "—"
  const m = /^(p\d+-\d+|[a-z0-9]+(?:-[a-z0-9]+){0,2})-(.*)$/.exec(t)
  return m ? m[2] : t
}

/**
 * One measure per worker run over time, split into two fixed series: runs
 * that used graft and runs that did not. A dot per run (hover for the task);
 * two series → legend. The measure is chosen by the parent so no chart ever
 * carries two y-scales.
 */
export function RunsOverTime({
  runs,
  measure,
  label,
  unit,
}: {
  runs: AgentRun[]
  measure: "reads" | "in_tok" | "out_tok" | "wall_s"
  label: string
  unit?: "k" | "M" | "min"
}) {
  const config = {
    nograft: { label: "no graft", color: "var(--viz-1)" },
    graft: { label: "used graft", color: "var(--viz-2)" },
  } satisfies ChartConfig
  const data = useMemo(() => {
    const rows = runs
      .filter((r) => r.role === "worker" && r.start && r[measure] !== null)
      .map((r) => ({
        t: new Date(r.start!).getTime(),
        y:
          unit === "min"
            ? Math.round((r[measure] as number) / 60)
            : unit === "k"
              ? Math.round((r[measure] as number) / 1000)
              : unit === "M"
                ? Math.round((r[measure] as number) / 100_000) / 10
                : (r[measure] as number),
        task: shortTask(r.task),
        graft: r.graft > 0,
      }))
    return {
      nograft: rows.filter((r) => !r.graft),
      graft: rows.filter((r) => r.graft),
    }
  }, [runs, measure, unit])
  const n = data.nograft.length + data.graft.length
  if (n === 0)
    return (
      <p className="text-sm text-muted-foreground">No worker runs in range.</p>
    )
  return (
    <ChartContainer config={config} className="h-56 w-full">
      <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={["dataMin", "dataMax"]}
          tickFormatter={fmtDay}
          tickLine={false}
          axisLine={false}
          fontSize={11}
        />
        <YAxis
          dataKey="y"
          type="number"
          tickLine={false}
          axisLine={false}
          width={52}
          fontSize={11}
          tickFormatter={(v: number) =>
            unit === "k"
              ? `${v}k`
              : unit === "M"
                ? `${v}M`
                : unit === "min"
                  ? `${v}m`
                  : `${v}`
          }
        />
        <ZAxis range={[60, 60]} />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              labelFormatter={(_l, payload) => {
                const p = payload?.[0]?.payload as
                  { task: string; t: number } | undefined
                return p ? `${p.task} · ${fmtWhen(p.t)}` : ""
              }}
              formatter={(v) => [
                `${v}${unit === "k" ? "k" : unit === "M" ? "M" : unit === "min" ? " min" : ""} ${label}`,
                "",
              ]}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Scatter
          isAnimationActive={false}
          name="nograft"
          data={data.nograft}
          fill="var(--color-nograft)"
          fillOpacity={0.85}
        />
        <Scatter
          isAnimationActive={false}
          name="graft"
          data={data.graft}
          fill="var(--color-graft)"
          fillOpacity={0.85}
        />
      </ScatterChart>
    </ChartContainer>
  )
}

/** Review pass-on-first-try rate per change: one measure, one hue. */
export function PassFirstByChange({ groups }: { groups: MetricsGroup[] }) {
  const config = {
    rate: { label: "pass first review", color: "var(--viz-1)" },
  } satisfies ChartConfig
  const data = useMemo(
    () =>
      groups
        .filter((g) => g.reviewed > 0)
        .map((g) => ({
          change: g.change,
          rate: Math.round((100 * g.passFirst) / g.reviewed),
          n: g.reviewed,
          fixes: g.fixCycles,
        }))
        .sort((a, b) => b.n - a.n)
        .slice(0, 12),
    [groups],
  )
  if (data.length === 0)
    return <p className="text-sm text-muted-foreground">No reviewed runs.</p>
  return (
    <ChartContainer
      config={config}
      className="w-full"
      style={{ height: 24 * data.length + 40 }}
    >
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 40, bottom: 4, left: 4 }}
        barCategoryGap={4}
      >
        <CartesianGrid stroke="var(--viz-grid)" horizontal={false} />
        <XAxis
          type="number"
          domain={[0, 100]}
          tickFormatter={(v: number) => `${v}%`}
          tickLine={false}
          axisLine={false}
          fontSize={11}
        />
        <YAxis
          type="category"
          dataKey="change"
          width={170}
          tickLine={false}
          axisLine={false}
          fontSize={11}
          tickFormatter={(v: string) =>
            v.length > 26 ? `${v.slice(0, 25)}…` : v
          }
        />
        <ChartTooltip
          cursor={{ fill: "var(--viz-grid)" }}
          content={
            <ChartTooltipContent
              formatter={(v, _n, item) => {
                const p = item.payload as { n: number; fixes: number }
                return [`${v}% of ${p.n} reviews · ${p.fixes} fix cycles`, ""]
              }}
            />
          }
        />
        <Bar
          isAnimationActive={false}
          dataKey="rate"
          fill="var(--color-rate)"
          radius={[0, 4, 4, 0]}
          maxBarSize={14}
        />
      </BarChart>
    </ChartContainer>
  )
}

/** Input tokens per spec run, stacked by pipeline stage (four fixed series). */
export function SpecTokensByStage({ specs }: { specs: SpecRunSummary[] }) {
  const config = Object.fromEntries(
    SPEC_STAGES.map((s) => [s.key, { label: s.label, color: s.color }]),
  ) satisfies ChartConfig
  const data = specs.map((s) => ({
    name: s.change
      ? s.change.length > 22
        ? `${s.change.slice(0, 21)}…`
        : s.change
      : fmtDay(s.start),
    when: fmtWhen(s.start),
    ...Object.fromEntries(
      SPEC_STAGES.map((st) => [
        st.key,
        Math.round(((s.byStage[st.key] ?? 0) / 1_000_000) * 10) / 10,
      ]),
    ),
  }))
  if (data.length === 0)
    return (
      <p className="text-sm text-muted-foreground">No spec runs in range.</p>
    )
  return (
    <ChartContainer config={config} className="h-64 w-full">
      <BarChart
        data={data}
        margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
        barCategoryGap={6}
      >
        <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
        <XAxis
          dataKey="name"
          tickLine={false}
          axisLine={false}
          fontSize={11}
          interval={0}
          angle={data.length > 6 ? -20 : 0}
          height={data.length > 6 ? 48 : 24}
          textAnchor={data.length > 6 ? "end" : "middle"}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={48}
          fontSize={11}
          tickFormatter={(v: number) => `${v}M`}
        />
        <ChartTooltip
          cursor={{ fill: "var(--viz-grid)" }}
          content={
            <ChartTooltipContent
              labelFormatter={(_l, p) =>
                (p?.[0]?.payload as { when: string })?.when ?? ""
              }
              formatter={(v, name) => [`${v}M tok`, ` ${String(name)}`]}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        {SPEC_STAGES.map((s, i) => (
          <Bar
            isAnimationActive={false}
            key={s.key}
            dataKey={s.key}
            stackId="a"
            fill={`var(--color-${s.key})`}
            stroke="var(--background)"
            strokeWidth={2}
            radius={i === SPEC_STAGES.length - 1 ? [4, 4, 0, 0] : 0}
            maxBarSize={36}
          />
        ))}
      </BarChart>
    </ChartContainer>
  )
}

/** The code-map explorer's read count per spec run — the cleanest graft signal. */
export function CodeMapReads({ specs }: { specs: SpecRunSummary[] }) {
  const config = {
    nograft: { label: "no graft", color: "var(--viz-1)" },
    graft: { label: "used graft", color: "var(--viz-2)" },
  } satisfies ChartConfig
  const rows = specs
    .filter((s) => s.codeMap)
    .map((s) => ({
      t: s.start,
      y: s.codeMap!.reads,
      task: s.change ?? "spec run",
      graft: s.codeMap!.graft > 0,
    }))
  if (rows.length === 0)
    return <p className="text-sm text-muted-foreground">No explorer runs.</p>
  return (
    <ChartContainer config={config} className="h-48 w-full">
      <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={["dataMin", "dataMax"]}
          tickFormatter={fmtDay}
          tickLine={false}
          axisLine={false}
          fontSize={11}
        />
        <YAxis
          dataKey="y"
          type="number"
          tickLine={false}
          axisLine={false}
          width={44}
          fontSize={11}
        />
        <ZAxis range={[60, 60]} />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              labelFormatter={(_l, p) => {
                const x = p?.[0]?.payload as
                  { task: string; t: number } | undefined
                return x ? `${x.task} · ${fmtWhen(x.t)}` : ""
              }}
              formatter={(v) => [`${v} reads`, ""]}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Scatter
          isAnimationActive={false}
          name="nograft"
          data={rows.filter((r) => !r.graft)}
          fill="var(--color-nograft)"
        />
        <Scatter
          isAnimationActive={false}
          name="graft"
          data={rows.filter((r) => r.graft)}
          fill="var(--color-graft)"
        />
      </ScatterChart>
    </ChartContainer>
  )
}
