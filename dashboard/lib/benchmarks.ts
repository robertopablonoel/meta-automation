import type { Benchmark } from "./types";

export const softBenchmarks: Benchmark[] = [
  {
    key: "cpc",
    label: "CPC (Link Click)",
    target: 1.5,
    comparison: "less_than",
    format: "currency",
  },
  {
    key: "ctr",
    label: "CTR (Link Click)",
    target: 3,
    comparison: "greater_than",
    format: "percent",
  },
  {
    key: "cpm",
    label: "CPM",
    target: [40, 50],
    comparison: "between",
    format: "currency",
    lowerIsBetter: true,
  },
  {
    key: "hookRate",
    label: "Hook Rate (3s View %)",
    target: 50,
    comparison: "greater_than",
    format: "percent",
    videoOnly: true,
  },
  {
    key: "holdRate",
    label: "Hold Rate (p50 %)",
    target: 25,
    comparison: "greater_than",
    format: "percent",
    videoOnly: true,
  },
  {
    key: "frequency",
    label: "Frequency",
    target: 1.5,
    comparison: "less_than",
    format: "number",
  },
];

export const hardBenchmarks: Benchmark[] = [
  {
    key: "cvr",
    label: "CVR",
    target: [3, 5],
    comparison: "between",
    format: "percent",
    lowerIsBetter: false,
  },
  {
    key: "atcRate",
    label: "ATC Rate",
    target: 10,
    comparison: "greater_than",
    format: "percent",
  },
  {
    key: "atcToPurchase",
    label: "ATC → Purchase",
    target: 30,
    comparison: "greater_than",
    format: "percent",
  },
  {
    key: "cpa",
    label: "CPA",
    target: 0, // Dynamic: < 50% of AOV target
    comparison: "less_than",
    format: "currency",
    dynamic: true,
  },
];

export const allBenchmarks = [...softBenchmarks, ...hardBenchmarks];

// Dynamic CPA target = 50% of (2x front-end price)
export function getCpaTarget(frontEndPrice: number): number {
  return frontEndPrice * 2 * 0.5; // = frontEndPrice
}

/**
 * Returns a Tailwind text color class for a metric value relative to its benchmark.
 * Green = good, yellow = borderline, red = bad, "" = no data / no benchmark.
 */
export function getMetricColor(key: string, value: number): string {
  // No meaningful data
  if (value === 0 && ["cpc", "cpa"].includes(key)) return "";

  // ROAS: not in benchmarks but higher is better
  if (key === "roas") {
    if (value <= 0) return "";
    if (value >= 2) return "text-green-600";
    if (value >= 1) return "text-yellow-600";
    return "text-red-500";
  }

  const benchmark = allBenchmarks.find((b) => b.key === key);
  if (!benchmark) return "";

  let target = benchmark.target;
  if (benchmark.dynamic && benchmark.key === "cpa") {
    target = getCpaTarget(69.95); // default front-end price
  }

  if (benchmark.comparison === "less_than") {
    const t = target as number;
    if (value <= t) return "text-green-600";
    if (value <= t * 1.5) return "text-yellow-600";
    return "text-red-500";
  }

  if (benchmark.comparison === "greater_than") {
    const t = target as number;
    if (value >= t) return "text-green-600";
    if (value >= t * 0.5) return "text-yellow-600";
    return "text-red-500";
  }

  // "between" [lo, hi]
  const [lo, hi] = target as [number, number];
  if (value >= lo && value <= hi) return "text-green-600";
  if (benchmark.lowerIsBetter) {
    // Below range is good (e.g. CPM)
    if (value < lo) return "text-green-600";
    if (value <= hi * 1.3) return "text-yellow-600";
    return "text-red-500";
  } else {
    // Above range is good (e.g. CVR)
    if (value > hi) return "text-green-600";
    if (value >= lo * 0.5) return "text-yellow-600";
    return "text-red-500";
  }
}
