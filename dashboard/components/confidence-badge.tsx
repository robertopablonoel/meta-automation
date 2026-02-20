"use client";

import { Badge } from "@/components/ui/badge";
import type { Benchmark, ConfidenceInterval } from "@/lib/types";

type PerformanceLevel = "Low" | "On Target" | "High" | "No data";
type PerformanceColor = "good" | "bad" | "neutral";

function isLowerBetter(benchmark: Benchmark): boolean {
  if (benchmark.lowerIsBetter !== undefined) return benchmark.lowerIsBetter;
  return benchmark.comparison === "less_than";
}

export function getPerformanceLevel(
  value: number,
  benchmark: Benchmark,
  ci: ConfidenceInterval
): { label: PerformanceLevel; color: PerformanceColor } {
  // Only show "No data" when the value is truly zero/meaningless
  if (value === 0 && ci.confidence === "none") {
    return { label: "No data", color: "neutral" };
  }

  const lowerBetter = isLowerBetter(benchmark);

  if (benchmark.comparison === "between") {
    const [lo, hi] = benchmark.target as [number, number];
    if (value < lo) {
      return { label: "Low", color: lowerBetter ? "good" : "bad" };
    }
    if (value > hi) {
      return { label: "High", color: lowerBetter ? "bad" : "good" };
    }
    return { label: "On Target", color: "good" };
  }

  if (benchmark.comparison === "less_than") {
    const t = benchmark.target as number;
    if (value <= t) {
      return { label: "On Target", color: "good" };
    }
    return { label: "High", color: "bad" };
  }

  // greater_than
  const t = benchmark.target as number;
  if (value >= t) {
    return { label: "On Target", color: "good" };
  }
  return { label: "Low", color: "bad" };
}

const colorStyles: Record<PerformanceColor, string> = {
  good: "bg-green-100 text-green-700",
  bad: "bg-red-100 text-red-700",
  neutral: "bg-gray-100 text-gray-500",
};

interface Props {
  label: PerformanceLevel;
  color: PerformanceColor;
}

export function PerformanceBadge({ label, color }: Props) {
  return (
    <Badge variant="outline" className={colorStyles[color]}>
      {label}
    </Badge>
  );
}
