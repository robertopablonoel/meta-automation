import { config } from "./config";
import {
  INSIGHTS_FIELDS,
  CAMPAIGN_FIELDS,
  ADSET_FIELDS,
  AD_FIELDS,
} from "./meta-fields";
import type { DateRange } from "./types";

const { baseUrl, accessToken, adAccountId } = config.meta;

async function metaFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, { next: { revalidate: 0 } });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Meta API error (${res.status}): ${error}`);
  }
  return res.json();
}

interface MetaListResponse<T> {
  data: T[];
  paging?: { cursors: { after: string }; next?: string };
}

// Paginate through all results
async function metaFetchAll<T>(startUrl: string): Promise<T[]> {
  const results: T[] = [];
  let url: string | undefined = startUrl;
  while (url) {
    const response: MetaListResponse<T> = await metaFetch<MetaListResponse<T>>(url);
    results.push(...response.data);
    url = response.paging?.next;
  }
  return results;
}

export async function listCampaigns() {
  const url = `${baseUrl}/act_${adAccountId}/campaigns?fields=${CAMPAIGN_FIELDS}&limit=100&access_token=${accessToken}`;
  return metaFetchAll<{
    id: string;
    name: string;
    status: string;
    created_time: string;
  }>(url);
}

export async function getCampaignInsights(
  campaignId: string,
  dateRange?: DateRange
) {
  let url = `${baseUrl}/${campaignId}/insights?fields=${INSIGHTS_FIELDS}&access_token=${accessToken}`;
  if (dateRange) {
    url += `&time_range=${JSON.stringify({
      since: dateRange.since,
      until: dateRange.until,
    })}`;
  }
  const response = await metaFetch<{ data: Record<string, unknown>[] }>(url);
  return response.data?.[0] || null;
}

export async function getAdSetInsights(
  campaignId: string,
  dateRange?: DateRange
) {
  let url = `${baseUrl}/${campaignId}/adsets?fields=${ADSET_FIELDS},insights.fields(${INSIGHTS_FIELDS})&limit=100&access_token=${accessToken}`;
  if (dateRange) {
    const timeRange = JSON.stringify({
      since: dateRange.since,
      until: dateRange.until,
    });
    url = `${baseUrl}/${campaignId}/adsets?fields=${ADSET_FIELDS},insights.fields(${INSIGHTS_FIELDS}).time_range(${timeRange})&limit=100&access_token=${accessToken}`;
  }
  return metaFetchAll<Record<string, unknown>>(url);
}

export async function getAdInsights(adSetId: string, dateRange?: DateRange) {
  let url = `${baseUrl}/${adSetId}/ads?fields=${AD_FIELDS},insights.fields(${INSIGHTS_FIELDS})&limit=200&access_token=${accessToken}`;
  if (dateRange) {
    const timeRange = JSON.stringify({
      since: dateRange.since,
      until: dateRange.until,
    });
    url = `${baseUrl}/${adSetId}/ads?fields=${AD_FIELDS},insights.fields(${INSIGHTS_FIELDS}).time_range(${timeRange})&limit=200&access_token=${accessToken}`;
  }
  return metaFetchAll<Record<string, unknown>>(url);
}

export async function getSingleAdInsights(adId: string, dateRange?: DateRange) {
  let url = `${baseUrl}/${adId}?fields=${AD_FIELDS},insights.fields(${INSIGHTS_FIELDS})&access_token=${accessToken}`;
  if (dateRange) {
    const timeRange = JSON.stringify({
      since: dateRange.since,
      until: dateRange.until,
    });
    url = `${baseUrl}/${adId}?fields=${AD_FIELDS},insights.fields(${INSIGHTS_FIELDS}).time_range(${timeRange})&access_token=${accessToken}`;
  }
  return metaFetch<Record<string, unknown>>(url);
}

export async function getCampaignAds(campaignId: string, dateRange?: DateRange) {
  let url = `${baseUrl}/${campaignId}/ads?fields=${AD_FIELDS},insights.fields(${INSIGHTS_FIELDS})&limit=200&access_token=${accessToken}`;
  if (dateRange) {
    const timeRange = JSON.stringify({
      since: dateRange.since,
      until: dateRange.until,
    });
    url = `${baseUrl}/${campaignId}/ads?fields=${AD_FIELDS},insights.fields(${INSIGHTS_FIELDS}).time_range(${timeRange})&limit=200&access_token=${accessToken}`;
  }
  return metaFetchAll<Record<string, unknown>>(url);
}
