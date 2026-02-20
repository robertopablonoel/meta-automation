import useSWR from "swr";
import type { DateRange } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildUrl(campaignId: string | null, dateRange?: DateRange) {
  if (!campaignId) return null;
  let url = `/api/meta/campaign?id=${campaignId}`;
  if (dateRange) {
    url += `&since=${dateRange.since}&until=${dateRange.until}`;
  }
  return url;
}

export function useCampaignInsights(
  campaignId: string | null,
  dateRange?: DateRange
) {
  const { data, error, isLoading } = useSWR(
    buildUrl(campaignId, dateRange),
    fetcher,
    { refreshInterval: 60_000 }
  );

  return {
    insights: data?.data ?? null,
    isLoading,
    error,
  };
}
