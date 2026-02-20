import type { ConfidenceInterval, ConfidenceLevel } from "./types";

/**
 * Wilson Score Interval for proportions (CTR, CVR, ATC rate, hook/hold rate)
 * Handles small samples gracefully — doesn't blow up at n=0.
 */
export function wilsonScoreInterval(
  successes: number,
  trials: number,
  z: number = 1.96 // 95% CI
): ConfidenceInterval {
  if (trials === 0) {
    return { lower: 0, upper: 0, center: 0, confidence: "none" };
  }

  const p = successes / trials;
  const z2 = z * z;
  const denominator = 1 + z2 / trials;

  const center = (p + z2 / (2 * trials)) / denominator;
  const margin =
    (z * Math.sqrt((p * (1 - p)) / trials + z2 / (4 * trials * trials))) /
    denominator;

  const lower = Math.max(0, center - margin);
  const upper = Math.min(1, center + margin);
  const confidence = getProportionConfidence(trials, lower, upper, center);

  return {
    lower: lower * 100,
    upper: upper * 100,
    center: center * 100,
    confidence,
  };
}

/**
 * Monetary CI for ratios (CPC, CPA, AOV)
 * Uses CLT: SE = mean / sqrt(count)
 */
export function monetaryCI(
  total: number,
  count: number,
  z: number = 1.96
): ConfidenceInterval {
  if (count === 0) {
    return { lower: 0, upper: 0, center: 0, confidence: "none" };
  }

  const mean = total / count;
  const se = mean / Math.sqrt(count);
  const lower = Math.max(0, mean - z * se);
  const upper = mean + z * se;
  const confidence = getMonetaryConfidence(count);

  return { lower, upper, center: mean, confidence };
}

function getProportionConfidence(
  trials: number,
  lower: number,
  upper: number,
  center: number
): ConfidenceLevel {
  if (trials < 100) return "none";
  if (center === 0) return "none";
  const relativeWidth = (upper - lower) / center;
  if (relativeWidth > 1.0) return "low";
  if (relativeWidth > 0.5) return "medium";
  return "high";
}

function getMonetaryConfidence(count: number): ConfidenceLevel {
  if (count < 10) return "none";
  if (count < 30) return "low";
  if (count < 100) return "medium";
  return "high";
}

/**
 * Get CI for a given metric key
 */
export function getMetricCI(
  key: string,
  metrics: Record<string, unknown> & {
    impressions: number;
    linkClicks: number;
    spend: number;
    purchases: number;
    addToCart: number;
    purchaseValue: number;
    video3sViews: number;
    videoP50Views: number;
  }
): ConfidenceInterval {
  switch (key) {
    case "ctr":
      return wilsonScoreInterval(metrics.linkClicks, metrics.impressions);
    case "cvr":
      return wilsonScoreInterval(metrics.purchases, metrics.linkClicks);
    case "atcRate":
      return wilsonScoreInterval(metrics.addToCart, metrics.linkClicks);
    case "atcToPurchase":
      return wilsonScoreInterval(metrics.purchases, metrics.addToCart);
    case "hookRate":
      return wilsonScoreInterval(metrics.video3sViews, metrics.impressions);
    case "holdRate":
      return wilsonScoreInterval(metrics.videoP50Views, metrics.video3sViews);
    case "cpc":
      return monetaryCI(metrics.spend, metrics.linkClicks);
    case "cpa":
      return monetaryCI(metrics.spend, metrics.purchases);
    case "aov":
      return monetaryCI(metrics.purchaseValue, metrics.purchases);
    case "cpm":
      return monetaryCI(metrics.spend * 1000, metrics.impressions);
    case "frequency":
      // Frequency is impressions/reach — use monetary-style CI
      return monetaryCI(metrics.impressions, (metrics as Record<string, number>).reach || 1);
    default:
      return { lower: 0, upper: 0, center: 0, confidence: "none" };
  }
}
