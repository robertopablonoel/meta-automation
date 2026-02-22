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
  frontEndPrice: number,
  campaignSpend?: number
): Recommendation {
  const reasoning: string[] = [];
  const cpaTarget = getCpaTarget(frontEndPrice);

  // Starving: getting less than a fair share of campaign spend,
  // or barely any delivery in absolute terms
  const spendShare = campaignSpend && campaignSpend > 0
    ? metrics.spend / campaignSpend
    : null;
  const isStarving = spendShare !== null
    ? spendShare < 0.02 // <2% of campaign spend
    : metrics.spend < 3 || metrics.impressions < 100; // absolute fallback

  if (isStarving) {
    const detail = spendShare !== null
      ? `${(spendShare * 100).toFixed(1)}% of campaign spend ($${metrics.spend.toFixed(2)} / $${campaignSpend!.toFixed(2)})`
      : `$${metrics.spend.toFixed(2)} spend, ${metrics.impressions} impressions`;
    reasoning.push(`Insufficient delivery: ${detail}`);
    return { action: "Starving", reasoning };
  }

  const kpis = evaluateKpis(metrics, frontEndPrice);
  const hasPurchases = metrics.purchases > 0;
  const roas = metrics.roas;

  // ── Conversion-first logic ──
  // The #1 question: is this converting profitably?

  // Kill: spent enough to know with zero conversions
  // Tiered: more spend = lower traffic requirement
  if (!hasPurchases) {
    const spent2x = metrics.spend > cpaTarget * 2;  // ~$140
    const spent3x = metrics.spend > cpaTarget * 3;  // ~$210

    if (spent3x) {
      // 3x CPA with 0 purchases — kill regardless of traffic
      reasoning.push(
        `$${metrics.spend.toFixed(2)} spent (>${(cpaTarget * 3).toFixed(0)} 3× CPA target) with 0 purchases`
      );
      return { action: "Kill", reasoning };
    }

    if (spent2x && metrics.linkClicks >= 30) {
      // 2x CPA + decent traffic with 0 purchases
      reasoning.push(
        `$${metrics.spend.toFixed(2)} spent with 0 purchases across ${metrics.linkClicks} link clicks`
      );
      return { action: "Kill", reasoning };
    }
  }

  // Kill: low volume but CPA is proven bad (1-4 purchases at > 2x CPA target)
  if (hasPurchases && metrics.purchases < 5 && metrics.cpa > cpaTarget * 2) {
    reasoning.push(
      `${metrics.purchases} purchase${metrics.purchases > 1 ? "s" : ""} at $${metrics.cpa.toFixed(2)} CPA (>${(cpaTarget * 2).toFixed(0)} 2× target)`
    );
    return { action: "Kill", reasoning };
  }

  // Kill: has conversions but confidently unprofitable (ROAS < 0.8 with enough data)
  if (hasPurchases && metrics.purchases >= 5 && roas < 0.8) {
    reasoning.push(
      `${metrics.purchases} purchases but ROAS is ${roas.toFixed(2)}x (unprofitable)`
    );
    return { action: "Kill", reasoning };
  }

  // Scale: converting profitably with enough signal
  if (hasPurchases && roas >= 1.0) {
    // Need at least a few conversions to trust the signal
    if (metrics.purchases >= 3 && metrics.cpa <= cpaTarget * 1.5) {
      reasoning.push(
        `${metrics.purchases} purchases at ${roas.toFixed(2)}x ROAS, $${metrics.cpa.toFixed(2)} CPA`
      );

      // Flag soft KPI concerns as context, but don't block Scale
      const softFailing = kpis
        .filter((k) => softBenchmarks.some((sb) => sb.key === k.benchmark.key))
        .filter((k) => k.confidentlyFailing);
      if (softFailing.length > 0) {
        reasoning.push(
          `Note: ${softFailing.map((k) => k.benchmark.label).join(", ")} below target — may improve with optimization`
        );
      }

      return { action: "Scale", reasoning };
    }
  }

  // Watch: everything else — not enough data or mixed signals
  if (hasPurchases) {
    reasoning.push(
      `${metrics.purchases} purchases, ${roas.toFixed(2)}x ROAS, $${metrics.cpa.toFixed(2)} CPA — accumulating data`
    );
  } else {
    reasoning.push(
      `$${metrics.spend.toFixed(2)} spent, ${metrics.linkClicks} link clicks, 0 purchases — needs more data`
    );
  }

  const softFailing = kpis
    .filter((k) => softBenchmarks.some((sb) => sb.key === k.benchmark.key))
    .filter((k) => k.confidentlyFailing);
  if (softFailing.length > 0) {
    reasoning.push(
      `Concern: ${softFailing.map((k) => k.benchmark.label).join(", ")} below target`
    );
  }

  return { action: "Watch", reasoning };
}
