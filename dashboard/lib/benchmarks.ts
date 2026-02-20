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
