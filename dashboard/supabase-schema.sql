-- Meta Ads Dashboard — Supabase Schema
-- Run this in the Supabase SQL Editor to set up tables

-- Pipeline run metadata
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  campaign_id TEXT NOT NULL UNIQUE,
  campaign_name TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  config JSONB
);

-- Strategic concept categories discovered by pipeline
CREATE TABLE IF NOT EXISTS concepts (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES pipeline_runs(campaign_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  display_name TEXT,
  description TEXT,
  schwartz_sophistication TEXT,
  belief_mapping TEXT,
  UNIQUE(campaign_id, name)
);

-- Per-media descriptions from Pass 1
CREATE TABLE IF NOT EXISTS ad_descriptions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES pipeline_runs(campaign_id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  media_type TEXT NOT NULL,
  visual_elements TEXT,
  emotional_tone TEXT,
  implied_message TEXT,
  target_awareness_level TEXT,
  transcript_summary TEXT,
  UNIQUE(campaign_id, filename)
);

-- Copy variations generated per concept
CREATE TABLE IF NOT EXISTS copy_variations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES pipeline_runs(campaign_id) ON DELETE CASCADE,
  concept_name TEXT NOT NULL,
  sub_group_name TEXT,
  variation_number INT NOT NULL,
  primary_text TEXT,
  headline TEXT,
  description TEXT,
  UNIQUE(campaign_id, concept_name, sub_group_name, variation_number)
);

-- Maps Meta ad names back to pipeline entities
CREATE TABLE IF NOT EXISTS ad_mappings (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES pipeline_runs(campaign_id) ON DELETE CASCADE,
  ad_name TEXT NOT NULL,
  concept_name TEXT NOT NULL,
  sub_group_name TEXT NOT NULL,
  filename TEXT NOT NULL,
  media_type TEXT NOT NULL,
  UNIQUE(campaign_id, ad_name)
);

-- Indexes for dashboard queries
CREATE INDEX IF NOT EXISTS idx_concepts_campaign ON concepts(campaign_id);
CREATE INDEX IF NOT EXISTS idx_descriptions_campaign ON ad_descriptions(campaign_id);
CREATE INDEX IF NOT EXISTS idx_descriptions_filename ON ad_descriptions(campaign_id, filename);
CREATE INDEX IF NOT EXISTS idx_copy_campaign_concept ON copy_variations(campaign_id, concept_name);
CREATE INDEX IF NOT EXISTS idx_mappings_campaign ON ad_mappings(campaign_id);
CREATE INDEX IF NOT EXISTS idx_mappings_ad_name ON ad_mappings(campaign_id, ad_name);

-- Cached metrics from Meta API (populated by metrics_sync.py)
CREATE TABLE IF NOT EXISTS metrics_cache (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  entity_type TEXT NOT NULL,         -- 'campaign', 'adset', 'ad'
  entity_id TEXT NOT NULL,           -- Meta object ID
  parent_id TEXT,                    -- campaign_id for adsets, adset_id for ads
  campaign_id TEXT NOT NULL,         -- top-level campaign ID (for easy filtering)
  name TEXT,
  status TEXT,
  insights JSONB,                    -- raw Meta insights blob (the data[0] object)
  extra_fields JSONB,               -- non-insights fields (creative, adset_id, etc.)
  synced_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_mc_campaign ON metrics_cache(entity_type, entity_id) WHERE entity_type = 'campaign';
CREATE INDEX IF NOT EXISTS idx_mc_adsets ON metrics_cache(campaign_id, entity_type) WHERE entity_type = 'adset';
CREATE INDEX IF NOT EXISTS idx_mc_ads_by_adset ON metrics_cache(parent_id, entity_type) WHERE entity_type = 'ad';
CREATE INDEX IF NOT EXISTS idx_mc_ads_by_campaign ON metrics_cache(campaign_id, entity_type) WHERE entity_type = 'ad';

-- Daily metric snapshots (populated by metrics_sync.py with time_increment=1)
CREATE TABLE IF NOT EXISTS daily_snapshots (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  date DATE NOT NULL,
  insights JSONB,
  synced_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(entity_type, entity_id, date)
);

CREATE INDEX IF NOT EXISTS idx_ds_campaign_date
  ON daily_snapshots(campaign_id, entity_type, date)
  WHERE entity_type = 'campaign';

-- Sync run log
CREATE TABLE IF NOT EXISTS sync_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  started_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ,
  campaigns_synced INT DEFAULT 0,
  adsets_synced INT DEFAULT 0,
  ads_synced INT DEFAULT 0,
  status TEXT DEFAULT 'running',     -- 'running', 'completed', 'failed'
  error_message TEXT
);
