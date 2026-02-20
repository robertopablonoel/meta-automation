import useSWR from "swr";
import type { DateRange } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useCampaignAds(
  campaignId: string | null,
  dateRange?: DateRange
) {
  const key = campaignId
    ? `/api/meta/campaign-ads?campaign_id=${campaignId}${
        dateRange ? `&since=${dateRange.since}&until=${dateRange.until}` : ""
      }`
    : null;

  const { data, error, isLoading } = useSWR(key, fetcher, {
    refreshInterval: 60_000,
  });

  return {
    ads: (data?.data ?? []) as Record<string, unknown>[],
    isLoading,
    error,
  };
}
