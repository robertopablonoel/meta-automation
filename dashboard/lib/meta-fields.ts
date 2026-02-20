import type { MetaAction } from "./types";

// Custom conversion IDs for Spicy Cubes / Pineapple
const CUSTOM_PURCHASE_ID = "866343756407498"; // "Purchase | All Pineapple"
const CUSTOM_ATC_ID = "882491937726061"; // "ATC | Pineapple"

// Fields requested from Meta Insights API
export const INSIGHTS_FIELDS = [
  "impressions",
  "clicks",
  "spend",
  "cpc",
  "cpm",
  "ctr",
  "reach",
  "frequency",
  "actions",
  "action_values",
  "cost_per_action_type",
  "video_avg_time_watched_actions",
  "video_p50_watched_actions",
  "video_p75_watched_actions",
].join(",");

export const CAMPAIGN_FIELDS = "name,status,created_time";
export const ADSET_FIELDS = "name,status,campaign_id";
export const AD_FIELDS = "name,status,adset_id,creative{id}";

// Extract a numeric value from Meta's actions array
export function extractAction(
  actions: MetaAction[] | undefined,
  actionType: string
): number {
  if (!actions) return 0;
  const action = actions.find((a) => a.action_type === actionType);
  return action ? parseFloat(action.value) : 0;
}

// Common action types — use custom conversions for purchase/ATC
export const ACTION_TYPES = {
  linkClick: "link_click",
  // Custom conversion: "Purchase | All Pineapple"
  purchase: `offsite_conversion.custom.${CUSTOM_PURCHASE_ID}`,
  // Custom conversion: "ATC | Pineapple"
  addToCart: `offsite_conversion.custom.${CUSTOM_ATC_ID}`,
  // Fallback standard pixel events
  pixelPurchase: "offsite_conversion.fb_pixel_purchase",
  pixelAddToCart: "offsite_conversion.fb_pixel_add_to_cart",
  landing_page_view: "landing_page_view",
  video3sView: "video_view",
} as const;

// Extract purchase value from actions
export function extractPurchaseValue(
  actions: MetaAction[] | undefined
): number {
  return extractAction(actions, ACTION_TYPES.purchase);
}

// Parse ad name → { concept, subGroup, filename }
export function parseAdName(adName: string): {
  concept: string;
  subGroup: string;
  filename: string;
} | null {
  // Ad names follow pattern: "concept/sub_group/filename"
  // Or with prefix: "Ad - concept/sub_group/filename"
  const cleaned = adName.replace(/^Ad\s*-\s*/, "");
  const parts = cleaned.split("/");
  if (parts.length < 3) return null;
  return {
    concept: parts[0].trim(),
    subGroup: parts[1].trim(),
    filename: parts.slice(2).join("/").trim(),
  };
}
