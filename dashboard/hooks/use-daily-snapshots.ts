import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useDailySnapshots(campaignId: string | null, days = 30) {
  const { data, error, isLoading } = useSWR(
    campaignId
      ? `/api/meta/daily-snapshots?campaignId=${campaignId}&days=${days}`
      : null,
    fetcher,
    { refreshInterval: 300_000 } // 5 min
  );

  return {
    snapshots: (data?.data ?? []) as { date: string; insights: Record<string, unknown> }[],
    isLoading,
    error,
  };
}
