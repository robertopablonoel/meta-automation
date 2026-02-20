"use client";

import { useParams } from "next/navigation";
import { useAdInsights } from "@/hooks/use-ad-insights";
import { useAdSetInsights } from "@/hooks/use-adset-insights";
import { useConcepts, useAdMappings } from "@/hooks/use-metadata";
import { useDateRange } from "../../layout";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { AdTable } from "@/components/ad-table";
import { KpiCell } from "@/components/kpi-cell";
import { RecommendationBanner } from "@/components/recommendation-banner";
import { ConceptCard } from "@/components/concept-card";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { computeMetrics } from "@/lib/metrics";
import { evaluateKpis, getRecommendation } from "@/lib/recommendations";
import { softBenchmarks, hardBenchmarks } from "@/lib/benchmarks";
import { parseAdName } from "@/lib/meta-fields";
import type { AdRow, ComputedMetrics } from "@/lib/types";

const FRONT_END_PRICE = parseFloat(process.env.NEXT_PUBLIC_FRONT_END_PRICE || "69.95");

export default function AdSetDetail() {
  const { campaignId, adsetId } = useParams<{
    campaignId: string;
    adsetId: string;
  }>();
  const { dateRange } = useDateRange();
  const { ads, isLoading: adsLoading } = useAdInsights(adsetId, dateRange);
  const { adsets } = useAdSetInsights(campaignId, dateRange);
  const { concepts } = useConcepts(campaignId);
  const { mappings } = useAdMappings(campaignId);

  // Find this ad set
  const adset = adsets.find((a: Record<string, unknown>) => a.id === adsetId);
  const adsetName = (adset?.name as string) || "Ad Set";

  // Compute ad set level metrics
  const adsetInsights = (adset?.insights as { data: Record<string, unknown>[] })?.data?.[0];
  const adsetMetrics = adsetInsights
    ? computeMetrics(adsetInsights)
    : null;
  const adsetRecommendation = adsetMetrics
    ? getRecommendation(adsetMetrics, FRONT_END_PRICE)
    : null;

  // Match concept
  const conceptMap = new Map(concepts.map((c) => [c.name, c]));
  const mappingMap = new Map(mappings.map((m) => [m.ad_name, m]));
  let matchedConcept = null;
  for (const [name, concept] of conceptMap) {
    if (adsetName.toLowerCase().includes(name.toLowerCase())) {
      matchedConcept = concept;
      break;
    }
  }

  // Build ad rows
  const adRows: AdRow[] = ads.map((ad: Record<string, unknown>) => {
    const insightsData = (ad.insights as { data: Record<string, unknown>[] })?.data?.[0];
    const metrics: ComputedMetrics = insightsData
      ? computeMetrics(insightsData)
      : computeMetrics({} as Record<string, unknown>);
    const recommendation = getRecommendation(metrics, FRONT_END_PRICE);

    const adName = ad.name as string;
    const parsed = parseAdName(adName);
    // Mappings are stored without the "Ad - " prefix
    const cleanedName = adName.replace(/^Ad\s*-\s*/, "");
    const mapping = mappingMap.get(cleanedName) || mappingMap.get(adName);
    const filename = mapping?.filename || parsed?.filename;
    const mediaType =
      mapping?.media_type ||
      (filename && /\.(mp4|mov|avi|mkv)$/i.test(filename) ? "video" : "image");

    return {
      id: ad.id as string,
      name: adName,
      status: ad.status as string,
      metrics,
      recommendation,
      filename,
      conceptName: mapping?.concept_name || parsed?.concept,
      subGroupName: mapping?.sub_group_name || parsed?.subGroup,
      mediaType,
    };
  });

  // KPIs at ad set level
  const kpis = adsetMetrics
    ? evaluateKpis(adsetMetrics, FRONT_END_PRICE)
    : [];
  const softKpis = kpis.filter((k) =>
    softBenchmarks.some((sb) => sb.key === k.benchmark.key)
  );
  const hardKpis = kpis.filter((k) =>
    hardBenchmarks.some((hb) => hb.key === k.benchmark.key)
  );

  if (adsLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-6 w-64 rounded" />
        <Skeleton className="h-20 rounded-lg" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-72 rounded-lg" />
          <Skeleton className="h-72 rounded-lg" />
        </div>
        <Skeleton className="h-96 rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumbs */}
      <Breadcrumbs
        items={[
          { label: "Campaign", href: `/${campaignId}` },
          { label: adsetName },
        ]}
      />

      {/* Header */}
      <h2 className="text-2xl font-bold tracking-tight">{adsetName}</h2>

      {/* Recommendation banner */}
      {adsetRecommendation && (
        <RecommendationBanner recommendation={adsetRecommendation} entityLabel="ad set" />
      )}

      {/* Concept card */}
      {matchedConcept && <ConceptCard concept={matchedConcept} />}

      {/* KPI breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Ad Performance</CardTitle>
            <p className="text-xs text-muted-foreground">How this ad set captures attention</p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              {softKpis.map((kpi) => (
                <KpiCell key={kpi.benchmark.key} kpi={kpi} />
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Conversion Funnel</CardTitle>
            <p className="text-xs text-muted-foreground">How clicks convert to revenue</p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              {hardKpis.map((kpi) => (
                <KpiCell key={kpi.benchmark.key} kpi={kpi} />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Ads table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Ads ({adRows.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AdTable ads={adRows} campaignId={campaignId} />
        </CardContent>
      </Card>
    </div>
  );
}
