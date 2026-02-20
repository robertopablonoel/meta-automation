// ── Meta API types ──

export interface MetaCampaign {
  id: string;
  name: string;
  status: string;
  created_time: string;
}

export interface MetaInsights {
  impressions: number;
  clicks: number;
  spend: number;
  cpc: number;
  cpm: number;
  ctr: number;
  reach: number;
  frequency: number;
  actions?: MetaAction[];
  cost_per_action_type?: MetaAction[];
  video_avg_time_watched_actions?: MetaAction[];
  video_p50_watched_actions?: MetaAction[];
  video_p75_watched_actions?: MetaAction[];
  date_start: string;
  date_stop: string;
}

export interface MetaAction {
  action_type: string;
  value: string;
}

export interface MetaAdSet {
  id: string;
  name: string;
  status: string;
  campaign_id: string;
  insights?: { data: MetaInsights[] };
}

export interface MetaAd {
  id: string;
  name: string;
  status: string;
  adset_id: string;
  insights?: { data: MetaInsights[] };
  creative?: { id: string };
}

// ── Computed metrics ──

export interface ComputedMetrics {
  // Raw
  impressions: number;
  clicks: number;
  linkClicks: number;
  spend: number;
  reach: number;
  frequency: number;
  // Soft
  cpc: number;
  ctr: number;
  cpm: number;
  hookRate: number | null; // video only
  holdRate: number | null; // video only
  // Hard
  addToCart: number;
  purchases: number;
  purchaseValue: number;
  cvr: number;
  atcRate: number;
  atcToPurchase: number;
  aov: number;
  cpa: number;
  roas: number;
  // Video raw
  video3sViews: number;
  videoP50Views: number;
}

// ── Confidence ──

export type ConfidenceLevel = "none" | "low" | "medium" | "high";

export interface ConfidenceInterval {
  lower: number;
  upper: number;
  center: number;
  confidence: ConfidenceLevel;
}

// ── Benchmarks ──

export type ComparisonType = "less_than" | "greater_than" | "between";

export interface Benchmark {
  key: string;
  label: string;
  target: number | [number, number];
  comparison: ComparisonType;
  format: "currency" | "percent" | "number";
  videoOnly?: boolean;
  dynamic?: boolean;
}

// ── KPI evaluation ──

export interface KpiResult {
  benchmark: Benchmark;
  value: number;
  ci: ConfidenceInterval;
  passing: boolean;
  confidentlyPassing: boolean;
  confidentlyFailing: boolean;
}

// ── Recommendations ──

export type RecommendationAction = "Kill" | "Watch" | "Scale" | "Starving";

export interface Recommendation {
  action: RecommendationAction;
  reasoning: string[];
}

// ── Supabase metadata ──

export interface PipelineRun {
  id: string;
  campaign_id: string;
  campaign_name: string | null;
  created_at: string;
  config: Record<string, unknown> | null;
}

export interface Concept {
  id: string;
  campaign_id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  schwartz_sophistication: string | null;
  belief_mapping: string | null;
}

export interface AdDescription {
  id: string;
  campaign_id: string;
  filename: string;
  media_type: string;
  visual_elements: string | null;
  emotional_tone: string | null;
  implied_message: string | null;
  target_awareness_level: string | null;
  transcript_summary: string | null;
}

export interface CopyVariation {
  id: string;
  campaign_id: string;
  concept_name: string;
  sub_group_name: string | null;
  variation_number: number;
  primary_text: string | null;
  headline: string | null;
  description: string | null;
}

export interface AdMapping {
  id: string;
  campaign_id: string;
  ad_name: string;
  concept_name: string;
  sub_group_name: string;
  filename: string;
  media_type: string;
}

// ── UI Props ──

export interface DateRange {
  since: string; // YYYY-MM-DD
  until: string; // YYYY-MM-DD
}

export interface AdSetRow {
  id: string;
  name: string;
  status: string;
  metrics: ComputedMetrics;
  recommendation: Recommendation;
  conceptName?: string;
  conceptDisplayName?: string;
}

export interface AdRow {
  id: string;
  name: string;
  status: string;
  metrics: ComputedMetrics;
  recommendation: Recommendation;
  filename?: string;
  conceptName?: string;
  subGroupName?: string;
  mediaType?: string;
}
