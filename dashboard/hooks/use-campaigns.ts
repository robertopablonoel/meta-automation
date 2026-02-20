import useSWR from "swr";
import type { MetaCampaign } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useCampaigns() {
  const { data, error, isLoading } = useSWR<{ data: MetaCampaign[] }>(
    "/api/campaigns",
    fetcher,
    { revalidateOnFocus: false }
  );

  return {
    campaigns: data?.data ?? [],
    isLoading,
    error,
  };
}
