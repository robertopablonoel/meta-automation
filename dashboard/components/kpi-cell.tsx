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

  // Value color based on pass/fail
  let valueColor = "text-foreground";
  if (kpi.confidentlyPassing) valueColor = "text-green-600";
  else if (kpi.confidentlyFailing) valueColor = "text-red-600";
  else if (kpi.passing) valueColor = "text-green-500/80";
  else valueColor = "text-red-500/80";

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
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{benchmark.label}</span>
        <PerformanceBadge label={perf.label} color={perf.color} />
      </div>
      <div className={`text-lg font-semibold ${valueColor}`}>{formatted}</div>
      {ci.confidence !== "none" && (
        <div className="text-xs text-muted-foreground">
          CI: {ciLower} - {ciUpper}
        </div>
      )}
      <div className="text-xs text-muted-foreground">Target: {target}</div>
      {/* Benchmark bar */}
      <BenchmarkBar kpi={kpi} />
    </div>
  );
}

function BenchmarkBar({ kpi }: { kpi: KpiResult }) {
  const { benchmark, value, ci } = kpi;

  // Determine bar range based on benchmark type
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
    ? "bg-green-200"
    : kpi.confidentlyFailing
    ? "bg-red-200"
    : "bg-gray-200";

  return (
    <div className={`relative h-2 rounded-full ${bgColor} overflow-hidden`}>
      {/* CI range */}
      {ci.confidence !== "none" && (
        <div
          className="absolute h-full bg-blue-300/50 rounded-full"
          style={{
            left: `${ciLowerPos * 100}%`,
            width: `${(ciUpperPos - ciLowerPos) * 100}%`,
          }}
        />
      )}
      {/* Target line(s) */}
      {Array.isArray(targetPos) ? (
        <>
          <div
            className="absolute h-full w-px bg-gray-500"
            style={{ left: `${targetPos[0] * 100}%` }}
          />
          <div
            className="absolute h-full w-px bg-gray-500"
            style={{ left: `${targetPos[1] * 100}%` }}
          />
        </>
      ) : (
        <div
          className="absolute h-full w-px bg-gray-500"
          style={{ left: `${(targetPos as number) * 100}%` }}
        />
      )}
      {/* Value dot */}
      <div
        className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-foreground"
        style={{ left: `calc(${valuePos * 100}% - 4px)` }}
      />
    </div>
  );
}
