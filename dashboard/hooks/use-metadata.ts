import useSWR from "swr";
import type { Concept, AdDescription, CopyVariation, AdMapping } from "@/lib/types";
import { supabase } from "@/lib/supabase";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useConcepts(campaignId: string | null) {
  const { data, error, isLoading } = useSWR(
    campaignId ? `/api/metadata/concepts?campaign_id=${campaignId}` : null,
    fetcher
  );

  return {
    concepts: (data?.data ?? []) as Concept[],
    isLoading,
    error,
  };
}

export function useAdDescriptions(
  campaignId: string | null,
  filename?: string
) {
  let url = campaignId
    ? `/api/metadata/descriptions?campaign_id=${campaignId}`
    : null;
  if (url && filename) {
    url += `&filename=${encodeURIComponent(filename)}`;
  }

  const { data, error, isLoading } = useSWR(url, fetcher);

  return {
    descriptions: (data?.data ?? []) as AdDescription[],
    isLoading,
    error,
  };
}

export function useCopyVariations(
  campaignId: string | null,
  conceptName?: string,
  subGroupName?: string
) {
  let url = campaignId
    ? `/api/metadata/copy?campaign_id=${campaignId}`
    : null;
  if (url && conceptName) {
    url += `&concept_name=${encodeURIComponent(conceptName)}`;
  }
  if (url && subGroupName) {
    url += `&sub_group_name=${encodeURIComponent(subGroupName)}`;
  }

  const { data, error, isLoading } = useSWR(url, fetcher);

  return {
    variations: (data?.data ?? []) as CopyVariation[],
    isLoading,
    error,
  };
}

// Direct Supabase query for ad mappings (used in components)
export function useAdMappings(campaignId: string | null) {
  const { data, error, isLoading } = useSWR(
    campaignId ? `mappings-${campaignId}` : null,
    async () => {
      const { data, error } = await supabase
        .from("ad_mappings")
        .select("*")
        .eq("campaign_id", campaignId!);
      if (error) throw error;
      return data as AdMapping[];
    }
  );

  return {
    mappings: data ?? [],
    isLoading,
    error,
  };
}
