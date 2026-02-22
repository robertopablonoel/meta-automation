#!/usr/bin/env node
/**
 * Quick CLI to pull campaign & ad set performance from Meta API.
 * Usage:
 *   node scripts/report.mjs                      # all active campaigns, lifetime
 *   node scripts/report.mjs --days 7             # last 7 days
 *   node scripts/report.mjs --campaign 12345     # specific campaign
 *   node scripts/report.mjs --ads                # include ad-level breakdown
 */

import { config } from "dotenv";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, "../.env") });
config({ path: resolve(__dirname, "../.env.local") });

const TOKEN = process.env.META_ACCESS_TOKEN;
const ACCOUNT_ID = process.env.META_AD_ACCOUNT_ID;
const BASE = "https://graph.facebook.com/v21.0";

const INSIGHTS_FIELDS = [
  "impressions", "clicks", "spend", "cpc", "cpm", "ctr",
  "reach", "frequency", "actions", "action_values",
].join(",");

const CUSTOM_PURCHASE = "offsite_conversion.custom.866343756407498";
const CUSTOM_ATC = "offsite_conversion.custom.882491937726061";
const PIXEL_PURCHASE = "offsite_conversion.fb_pixel_purchase";

// Parse args
const args = process.argv.slice(2);
let days = null;
let campaignFilter = null;
let showAds = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--days" && args[i + 1]) days = parseInt(args[i + 1]);
  if (args[i] === "--campaign" && args[i + 1]) campaignFilter = args[i + 1];
  if (args[i] === "--ads") showAds = true;
}

function timeRangeParam() {
  if (!days) return "&date_preset=maximum";
  const until = new Date();
  const since = new Date();
  since.setDate(since.getDate() - days);
  const fmt = (d) => d.toISOString().split("T")[0];
  return `&time_range=${JSON.stringify({ since: fmt(since), until: fmt(until) })}`;
}

async function metaFetch(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Meta API ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

async function metaFetchAll(url) {
  const results = [];
  let next = url;
  while (next) {
    const data = await metaFetch(next);
    results.push(...(data.data || []));
    next = data.paging?.next || null;
  }
  return results;
}

function extractAction(actions, type) {
  if (!actions) return 0;
  const a = actions.find((x) => x.action_type === type);
  return a ? parseFloat(a.value) : 0;
}

function extractValue(actionValues, type) {
  if (!actionValues) return 0;
  const a = actionValues.find((x) => x.action_type === type);
  return a ? parseFloat(a.value) : 0;
}

function fmt$(n) { return `$${n.toFixed(2)}`; }
function fmtPct(n) { return `${parseFloat(n).toFixed(2)}%`; }
function fmtX(n) { return `${n.toFixed(2)}x`; }

function printMetrics(ins, indent = "") {
  const spend = parseFloat(ins.spend || 0);
  const impr = parseInt(ins.impressions || 0);
  const clicks = parseInt(ins.clicks || 0);
  const freq = ins.frequency || "N/A";
  const cpc = ins.cpc || "N/A";
  const ctr = ins.ctr || "0";

  const actions = ins.actions || [];
  const actionValues = ins.action_values || [];
  const linkClicks = extractAction(actions, "link_click");
  const customP = extractAction(actions, CUSTOM_PURCHASE);
  const customATC = extractAction(actions, CUSTOM_ATC);
  const pixelP = extractAction(actions, PIXEL_PURCHASE);
  const customRev = extractValue(actionValues, CUSTOM_PURCHASE);
  const pixelRev = extractValue(actionValues, PIXEL_PURCHASE);

  const customROAS = spend > 0 && customRev > 0 ? customRev / spend : 0;
  const pixelROAS = spend > 0 && pixelRev > 0 ? pixelRev / spend : 0;
  const customCPA = customP > 0 ? spend / customP : null;

  console.log(`${indent}Spend: ${fmt$(spend)} | Impr: ${impr.toLocaleString()} | LCs: ${linkClicks} | Freq: ${freq}`);
  console.log(`${indent}CPC: $${cpc} | CTR: ${fmtPct(ctr)}`);
  console.log(`${indent}Custom: ${customP}p (${fmt$(customRev)}) ${customATC}atc | Pixel: ${pixelP}p (${fmt$(pixelRev)})`);
  if (customROAS > 0) {
    console.log(`${indent}ROAS (custom): ${fmtX(customROAS)}${customCPA ? ` | CPA: ${fmt$(customCPA)}` : ""}`);
  }
  if (pixelROAS > 0 && pixelP !== customP) {
    console.log(`${indent}ROAS (pixel): ${fmtX(pixelROAS)}`);
  }

  return { spend, customP, customRev, pixelP, pixelRev, linkClicks, impr };
}

async function main() {
  const dateLabel = days ? `Last ${days} days` : "Lifetime";
  console.log(`\n📊 Meta Ads Report — ${dateLabel}`);
  console.log("═".repeat(60));

  // Get campaigns
  let campaigns = await metaFetchAll(
    `${BASE}/act_${ACCOUNT_ID}/campaigns?fields=id,name,status&limit=100&access_token=${TOKEN}`
  );

  if (campaignFilter) {
    campaigns = campaigns.filter((c) => c.id === campaignFilter);
  } else {
    campaigns = campaigns.filter((c) => c.status === "ACTIVE");
  }

  for (const campaign of campaigns) {
    // Campaign insights
    const cInsights = await metaFetch(
      `${BASE}/${campaign.id}/insights?fields=${INSIGHTS_FIELDS}${timeRangeParam()}&access_token=${TOKEN}`
    );
    const cData = cInsights.data?.[0];

    console.log(`\n🎯 ${campaign.name} [${campaign.status}]`);
    console.log("-".repeat(60));
    if (cData) {
      printMetrics(cData, "  ");
    } else {
      console.log("  No data");
    }

    // Gender breakdown
    const genderInsights = await metaFetch(
      `${BASE}/${campaign.id}/insights?fields=spend,impressions,actions,action_values&breakdowns=gender${timeRangeParam()}&access_token=${TOKEN}`
    );
    if (genderInsights.data?.length) {
      console.log("\n  Gender Split:");
      for (const g of genderInsights.data) {
        const spend = parseFloat(g.spend || 0);
        const customP = extractAction(g.actions, CUSTOM_PURCHASE);
        console.log(`    ${g.gender}: ${fmt$(spend)} spent, ${customP} custom purchases`);
      }
    }

    // Ad sets
    const timeRange = days
      ? JSON.stringify({ since: new Date(Date.now() - days * 86400000).toISOString().split("T")[0], until: new Date().toISOString().split("T")[0] })
      : null;
    const adsetUrl = timeRange
      ? `${BASE}/${campaign.id}/adsets?fields=name,status,insights.fields(${INSIGHTS_FIELDS}).time_range(${timeRange})&limit=100&access_token=${TOKEN}`
      : `${BASE}/${campaign.id}/adsets?fields=name,status,insights.fields(${INSIGHTS_FIELDS}).date_preset(maximum)&limit=100&access_token=${TOKEN}`;

    const adsets = await metaFetchAll(adsetUrl);

    // Sort by spend desc
    adsets.sort((a, b) => {
      const sa = parseFloat(a.insights?.data?.[0]?.spend || 0);
      const sb = parseFloat(b.insights?.data?.[0]?.spend || 0);
      return sb - sa;
    });

    console.log(`\n  Ad Sets (${adsets.length}):`);
    let totals = { spend: 0, customP: 0, customRev: 0, pixelP: 0 };

    for (const adset of adsets) {
      const ins = adset.insights?.data?.[0];
      const flag = ins ? "" : " (no data)";
      console.log(`\n  📦 ${adset.name} [${adset.status}]${flag}`);
      if (ins) {
        const m = printMetrics(ins, "    ");
        totals.spend += m.spend;
        totals.customP += m.customP;
        totals.customRev += m.customRev;
        totals.pixelP += m.pixelP;
      }

      // Ad-level breakdown
      if (showAds && ins) {
        const adUrl = timeRange
          ? `${BASE}/${adset.id}/ads?fields=name,status,insights.fields(${INSIGHTS_FIELDS}).time_range(${timeRange})&limit=200&access_token=${TOKEN}`
          : `${BASE}/${adset.id}/ads?fields=name,status,insights.fields(${INSIGHTS_FIELDS}).date_preset(maximum)&limit=200&access_token=${TOKEN}`;
        const ads = await metaFetchAll(adUrl);
        if (ads.length > 0) {
          for (const ad of ads) {
            const adIns = ad.insights?.data?.[0];
            if (!adIns) continue;
            console.log(`      🔹 ${ad.name}`);
            printMetrics(adIns, "        ");
          }
        }
      }
    }

    console.log(`\n  ${"═".repeat(50)}`);
    console.log(`  TOTALS: ${fmt$(totals.spend)} spent | ${totals.customP} custom purchases | ${fmt$(totals.customRev)} rev`);
    if (totals.spend > 0 && totals.customRev > 0) {
      console.log(`  Campaign ROAS (custom): ${fmtX(totals.customRev / totals.spend)}`);
    }
  }

  console.log("\n");
}

main().catch(console.error);
