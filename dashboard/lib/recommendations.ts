import type {
  ComputedMetrics,
  Benchmark,
  KpiResult,
  Recommendation,
  ConfidenceInterval,
} from "./types";
import { softBenchmarks, hardBenchmarks, getCpaTarget } from "./benchmarks";
import { getMetricCI } from "./confidence";

function isBenchmarkPassing(
  benchmark: Benchmark,
  ci: ConfidenceInterval,
  value: number,
  frontEndPrice: number
): { passing: boolean; confidentlyPassing: boolean; confidentlyFailing: boolean } {
  let target = benchmark.target;
  if (benchmark.dynamic && benchmark.key === "cpa") {
    target = getCpaTarget(frontEndPrice);
  }

  if (benchmark.comparison === "less_than") {
    const t = target as number;
    return {
      passing: value < t,
      confidentlyPassing: ci.upper < t,
      confidentlyFailing: ci.lower > t, // best case still exceeds target
    };
  }

  if (benchmark.comparison === "greater_than") {
    const t = target as number;
    return {
      passing: value > t,
      confidentlyPassing: ci.lower > t,
      confidentlyFailing: ci.upper < t, // best case still misses target
    };
  }

  // "between"
  const [low, high] = target as [number, number];

  if (benchmark.lowerIsBetter) {
    // e.g. CPM $40-$50: below range is good, above is bad
    return {
      passing: value <= high,
      confidentlyPassing: ci.upper <= high,
      confidentlyFailing: ci.lower > high,
    };
  }

  if (benchmark.lowerIsBetter === false) {
    // e.g. CVR 3-5%: above range is fine, below is bad
    return {
      passing: value >= low,
      confidentlyPassing: ci.lower >= low,
      confidentlyFailing: ci.upper < low,
    };
  }

  // Strict between (no preference)
  return {
    passing: value >= low && value <= high,
    confidentlyPassing: ci.lower >= low && ci.upper <= high,
    confidentlyFailing: ci.upper < low || ci.lower > high,
  };
}

export function evaluateKpis(
  metrics: ComputedMetrics,
  frontEndPrice: number
): KpiResult[] {
  const allBenchmarks = [...softBenchmarks, ...hardBenchmarks];
  return allBenchmarks
    .filter((b) => {
      if (b.videoOnly && metrics.hookRate === null) return false;
      return true;
    })
    .map((benchmark) => {
      const value = (metrics as unknown as Record<string, number>)[benchmark.key] ?? 0;
      const ci = getMetricCI(benchmark.key, metrics as unknown as Record<string, unknown> & {
        impressions: number; linkClicks: number; spend: number;
        purchases: number; addToCart: number; purchaseValue: number;
        video3sViews: number; videoP50Views: number;
      });
      const { passing, confidentlyPassing, confidentlyFailing } =
        isBenchmarkPassing(benchmark, ci, value, frontEndPrice);
      return { benchmark, value, ci, passing, confidentlyPassing, confidentlyFailing };
    });
}

export function getRecommendation(
  metrics: ComputedMetrics,
  frontEndPrice: number
): Recommendation {
  const reasoning: string[] = [];

  // Starving check
  if (metrics.spend < 10 || metrics.impressions < 500) {
    reasoning.push(
      `Insufficient data: $${metrics.spend.toFixed(2)} spend, ${metrics.impressions} impressions`
    );
    return { action: "Starving", reasoning };
  }

  const kpis = evaluateKpis(metrics, frontEndPrice);

  const softKpis = kpis.filter((k) =>
    softBenchmarks.some((sb) => sb.key === k.benchmark.key)
  );
  const hardKpis = kpis.filter((k) =>
    hardBenchmarks.some((hb) => hb.key === k.benchmark.key)
  );

  const confidentlyFailing = softKpis.filter((k) => k.confidentlyFailing);
  const confidentlyPassing = kpis.filter((k) => k.confidentlyPassing);
  const hardFailing = hardKpis.filter((k) => k.confidentlyFailing);

  // Kill: 3+ soft KPIs confidently failing
  if (confidentlyFailing.length >= 3) {
    reasoning.push(
      `${confidentlyFailing.length} soft KPIs confidently failing: ${confidentlyFailing
        .map((k) => k.benchmark.label)
        .join(", ")}`
    );
    return { action: "Kill", reasoning };
  }

  // Kill: spent >$50, zero conversions, medium+ confidence
  if (metrics.spend > 50 && metrics.purchases === 0) {
    const ctrCi = kpis.find((k) => k.benchmark.key === "ctr");
    if (ctrCi && (ctrCi.ci.confidence === "medium" || ctrCi.ci.confidence === "high")) {
      reasoning.push(
        `$${metrics.spend.toFixed(2)} spent with 0 purchases at ${ctrCi.ci.confidence} confidence`
      );
      return { action: "Kill", reasoning };
    }
  }

  // Scale: 4+ KPIs confidently passing, no hard metric failing
  if (confidentlyPassing.length >= 4 && hardFailing.length === 0) {
    reasoning.push(
      `${confidentlyPassing.length} KPIs confidently passing: ${confidentlyPassing
        .map((k) => k.benchmark.label)
        .join(", ")}`
    );
    return { action: "Scale", reasoning };
  }

  // Watch: everything else
  const passingCount = kpis.filter((k) => k.passing).length;
  const failingCount = kpis.filter((k) => !k.passing).length;
  reasoning.push(
    `${passingCount} KPIs passing, ${failingCount} failing — needs more data`
  );
  if (confidentlyFailing.length > 0) {
    reasoning.push(
      `Concern: ${confidentlyFailing.map((k) => k.benchmark.label).join(", ")} confidently failing`
    );
  }
  return { action: "Watch", reasoning };
}
