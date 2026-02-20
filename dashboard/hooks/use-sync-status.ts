import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useSyncStatus() {
  const { data, error } = useSWR("/api/sync-status", fetcher, {
    refreshInterval: 60_000,
  });

  const lastSyncedAt = data?.data?.lastSyncedAt
    ? new Date(data.data.lastSyncedAt)
    : null;

  return {
    lastSyncedAt,
    counts: data?.data?.counts ?? null,
    isLoading: !data && !error,
    error,
  };
}
