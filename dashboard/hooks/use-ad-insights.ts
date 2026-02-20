import useSWR from "swr";
import type { DateRange } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useAdInsights(
  adsetId: string | null,
  dateRange?: DateRange
) {
  const key = adsetId
    ? `/api/meta/ads?adset_id=${adsetId}${
        dateRange ? `&since=${dateRange.since}&until=${dateRange.until}` : ""
      }`
    : null;

  const { data, error, isLoading } = useSWR(key, fetcher, {
    refreshInterval: 60_000,
  });

  return {
    ads: data?.data ?? [],
    isLoading,
    error,
  };
}

export function useSingleAdInsights(
  adId: string | null,
  dateRange?: DateRange
) {
  const key = adId
    ? `/api/meta/ads?ad_id=${adId}${
        dateRange ? `&since=${dateRange.since}&until=${dateRange.until}` : ""
      }`
    : null;

  const { data, error, isLoading } = useSWR(key, fetcher, {
    refreshInterval: 60_000,
  });

  return {
    ad: data?.data ?? null,
    isLoading,
    error,
  };
}
