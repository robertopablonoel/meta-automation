"use client";

import { PerformanceBadge, getPerformanceLevel } from "./confidence-badge";
import { formatMetric } from "@/lib/utils";
import type { KpiResult } from "@/lib/types";

export function KpiCell({ kpi }: { kpi: KpiResult }) {
  const { benchmark, value, ci } = kpi;
  const formatted = formatMetric(value, benchmark.format);
  const ciLower = formatMetric(ci.lower, benchmark.format);
  const ciUpper = formatMetric(ci.upper, benchmark.format);

  const perf = getPerformanceLevel(value, benchmark, ci);

  // Value color — works in both light and dark
  let valueColor = "text-foreground";
  if (kpi.confidentlyPassing) valueColor = "text-green-600 dark:text-green-400";
  else if (kpi.confidentlyFailing) valueColor = "text-red-600 dark:text-red-400";
  else if (kpi.passing) valueColor = "text-green-600/70 dark:text-green-400/70";
  else valueColor = "text-red-600/70 dark:text-red-400/70";

  // Background wash — very subtle in dark mode
  let bgWash = "bg-muted/30";
  if (perf.color === "good") bgWash = "bg-green-50 dark:bg-green-950/40";
  else if (perf.color === "bad") bgWash = "bg-red-50 dark:bg-red-950/40";

  // Target display
  const target = Array.isArray(benchmark.target)
    ? `${formatMetric(benchmark.target[0], benchmark.format)} - ${formatMetric(
        benchmark.target[1],
        benchmark.format
      )}`
    : `${benchmark.comparison === "less_than" ? "<" : ">="} ${formatMetric(
        benchmark.target,
        benchmark.format
      )}`;

  return (
    <div className={`rounded-lg p-3 space-y-1.5 ${bgWash} transition-colors`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{benchmark.label}</span>
        <PerformanceBadge label={perf.label} color={perf.color} />
      </div>
      <div className={`text-2xl font-bold tabular-nums ${valueColor}`}>{formatted}</div>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>Target: {target}</span>
        {ci.confidence !== "none" && (
          <span>CI: {ciLower} - {ciUpper}</span>
        )}
      </div>
      <BenchmarkBar kpi={kpi} />
    </div>
  );
}

function BenchmarkBar({ kpi }: { kpi: KpiResult }) {
  const { benchmark, value, ci } = kpi;

  let barMax: number;
  let targetPos: number | [number, number];

  if (Array.isArray(benchmark.target)) {
    barMax = benchmark.target[1] * 2;
    targetPos = [benchmark.target[0] / barMax, benchmark.target[1] / barMax];
  } else {
    barMax = benchmark.target * 3;
    targetPos = benchmark.target / barMax;
  }

  const valuePos = Math.min(1, Math.max(0, value / barMax));
  const ciLowerPos = Math.min(1, Math.max(0, ci.lower / barMax));
  const ciUpperPos = Math.min(1, Math.max(0, ci.upper / barMax));

  const bgColor = kpi.confidentlyPassing
    ? "bg-green-200 dark:bg-green-900/50"
    : kpi.confidentlyFailing
    ? "bg-red-200 dark:bg-red-900/50"
    : "bg-gray-200 dark:bg-gray-700";

  return (
    <div className={`relative h-2.5 rounded-full ${bgColor} overflow-hidden`}>
      {ci.confidence !== "none" && (
        <div
          className="absolute h-full bg-blue-300/50 dark:bg-blue-500/30 rounded-full"
          style={{
            left: `${ciLowerPos * 100}%`,
            width: `${(ciUpperPos - ciLowerPos) * 100}%`,
          }}
        />
      )}
      {Array.isArray(targetPos) ? (
        <>
          <div
            className="absolute h-full w-0.5 bg-gray-500/70 dark:bg-gray-400/70"
            style={{ left: `${targetPos[0] * 100}%` }}
          />
          <div
            className="absolute h-full w-0.5 bg-gray-500/70 dark:bg-gray-400/70"
            style={{ left: `${targetPos[1] * 100}%` }}
          />
        </>
      ) : (
        <div
          className="absolute h-full w-0.5 bg-gray-500/70 dark:bg-gray-400/70"
          style={{ left: `${(targetPos as number) * 100}%` }}
        />
      )}
      <div
        className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-foreground shadow-sm"
        style={{ left: `calc(${valuePos * 100}% - 5px)` }}
      />
    </div>
  );
}
