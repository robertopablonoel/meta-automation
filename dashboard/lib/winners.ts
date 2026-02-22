import type { ComputedMetrics, KpiResult, Recommendation } from "./types";
import { evaluateKpis, getRecommendation } from "./recommendations";
import { softBenchmarks } from "./benchmarks";

export type AdClassification = "winner" | "trending" | null;

/**
 * Classify an ad as "winner", "trending", or null based on KPI performance.
 *
 * Winner — confidently performing well:
 *   - Recommendation is "Scale" (4+ KPIs confidently passing, no hard metric failing), OR
 *   - 3+ KPIs confidently passing AND 0 KPIs confidently failing AND spend > $20
 *
 * Trending — promising but not yet proven:
 *   - Recommendation is "Watch" AND
 *   - 3+ KPIs passing at point estimate AND
 *   - 0 hard KPIs confidently failing AND
 *   - At least 1 KPI has confidence "low" or "medium" AND
 *   - Spend > $10
 */
export function classifyAd(
  metrics: ComputedMetrics,
  frontEndPrice: number,
  campaignSpend?: number
): {
  classification: AdClassification;
  recommendation: Recommendation;
  kpis: KpiResult[];
} {
  const recommendation = getRecommendation(metrics, frontEndPrice, campaignSpend);
  const kpis = evaluateKpis(metrics, frontEndPrice);

  const confidentlyPassing = kpis.filter((k) => k.confidentlyPassing);
  const confidentlyFailing = kpis.filter((k) => k.confidentlyFailing);
  const passing = kpis.filter((k) => k.passing);

  const hardKpis = kpis.filter(
    (k) => !softBenchmarks.some((sb) => sb.key === k.benchmark.key)
  );
  const hardConfidentlyFailing = hardKpis.filter((k) => k.confidentlyFailing);

  // Winner: "Scale" recommendation
  if (recommendation.action === "Scale") {
    return { classification: "winner", recommendation, kpis };
  }

  // Winner: 3+ confidently passing, 0 confidently failing, spend > $20
  if (
    confidentlyPassing.length >= 3 &&
    confidentlyFailing.length === 0 &&
    metrics.spend > 20
  ) {
    return { classification: "winner", recommendation, kpis };
  }

  // Trending: Watch + promising point estimates + still accumulating data
  if (recommendation.action === "Watch") {
    const hasLowOrMediumConfidence = kpis.some(
      (k) => k.ci.confidence === "low" || k.ci.confidence === "medium"
    );

    if (
      passing.length >= 3 &&
      hardConfidentlyFailing.length === 0 &&
      hasLowOrMediumConfidence &&
      metrics.spend > 10
    ) {
      return { classification: "trending", recommendation, kpis };
    }
  }

  return { classification: null, recommendation, kpis };
}
