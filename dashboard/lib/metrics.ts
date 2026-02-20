import type { ComputedMetrics } from "./types";
import { extractAction, ACTION_TYPES } from "./meta-fields";

export function computeMetrics(
  raw: Record<string, unknown>
): ComputedMetrics {
  const impressions = toNum(raw.impressions);
  const clicks = toNum(raw.clicks);
  const spend = toNum(raw.spend);
  const reach = toNum(raw.reach);
  const frequency = toNum(raw.frequency);

  const actions = raw.actions as
    | { action_type: string; value: string }[]
    | undefined;
  const actionValues = raw.action_values as
    | { action_type: string; value: string }[]
    | undefined;

  const linkClicks = extractAction(actions, ACTION_TYPES.linkClick);

  // Custom conversion events only — no fallback to standard pixel
  const purchases = extractAction(actions, ACTION_TYPES.purchase);
  const addToCart = extractAction(actions, ACTION_TYPES.addToCart);

  // Revenue: custom conversion only
  const purchaseValue = extractCustomRevenue(actionValues);

  const video3sViews = extractAction(actions, ACTION_TYPES.video3sView);
  const videoP50 = extractVideoMetric(raw.video_p50_watched_actions);

  const cpc = linkClicks > 0 ? spend / linkClicks : 0;
  const ctr = impressions > 0 ? (linkClicks / impressions) * 100 : 0;
  const cpm = impressions > 0 ? (spend / impressions) * 1000 : 0;
  const hookRate =
    video3sViews > 0 && impressions > 0
      ? (video3sViews / impressions) * 100
      : null;
  const holdRate =
    videoP50 > 0 && video3sViews > 0
      ? (videoP50 / video3sViews) * 100
      : null;
  const cvr = linkClicks > 0 ? (purchases / linkClicks) * 100 : 0;
  const atcRate = linkClicks > 0 ? (addToCart / linkClicks) * 100 : 0;
  const atcToPurchase =
    addToCart > 0 ? (purchases / addToCart) * 100 : 0;
  const aov = purchases > 0 ? purchaseValue / purchases : 0;
  const cpa = purchases > 0 ? spend / purchases : 0;
  const roas = spend > 0 ? purchaseValue / spend : 0;

  return {
    impressions,
    clicks,
    linkClicks,
    spend,
    reach,
    frequency,
    cpc,
    ctr,
    cpm,
    hookRate,
    holdRate,
    addToCart,
    purchases,
    purchaseValue,
    cvr,
    atcRate,
    atcToPurchase,
    aov,
    cpa,
    roas,
    video3sViews,
    videoP50Views: videoP50,
  };
}

function toNum(val: unknown): number {
  if (typeof val === "number") return val;
  if (typeof val === "string") return parseFloat(val) || 0;
  return 0;
}

function extractVideoMetric(
  actions: unknown
): number {
  if (!Array.isArray(actions)) return 0;
  const action = actions.find(
    (a: Record<string, string>) => a.action_type === "video_view"
  );
  return action ? parseFloat(action.value) : 0;
}

function extractCustomRevenue(
  actionValues: { action_type: string; value: string }[] | undefined
): number {
  if (!actionValues) return 0;
  const custom = actionValues.find(
    (a) => a.action_type === ACTION_TYPES.purchase
  );
  return custom ? parseFloat(custom.value) : 0;
}
