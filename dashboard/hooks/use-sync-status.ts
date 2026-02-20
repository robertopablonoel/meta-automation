import useSWR from "swr";
import { useState, useCallback, useRef } from "react";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useSyncStatus() {
  const { data, error, mutate } = useSWR("/api/sync-status", fetcher, {
    refreshInterval: 60_000,
  });

  const [isSyncing, setIsSyncing] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const triggerSync = useCallback(async () => {
    setIsSyncing(true);

    try {
      await fetch("/api/sync-status", { method: "POST" });
    } catch {
      setIsSyncing(false);
      return;
    }

    // Record the timestamp we started so we can detect a newer completed sync
    const startedAt = data?.data?.lastSyncedAt ?? null;

    // Poll every 3s until sync_log shows a newer completed entry
    pollRef.current = setInterval(async () => {
      const res = await mutate();
      const newSyncedAt = res?.data?.lastSyncedAt ?? null;

      if (newSyncedAt && newSyncedAt !== startedAt) {
        // New sync completed
        setIsSyncing(false);
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 3_000);

    // Safety timeout: stop polling after 5 minutes
    setTimeout(() => {
      setIsSyncing(false);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    }, 5 * 60_000);
  }, [data, mutate]);

  const lastSyncedAt = data?.data?.lastSyncedAt
    ? new Date(data.data.lastSyncedAt)
    : null;

  return {
    lastSyncedAt,
    counts: data?.data?.counts ?? null,
    isLoading: !data && !error,
    isSyncing,
    triggerSync,
    error,
  };
}
