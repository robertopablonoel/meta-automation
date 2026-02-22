"use client";

import { useParams } from "next/navigation";
import { useSingleAdInsights } from "@/hooks/use-ad-insights";
import { useCampaignInsights } from "@/hooks/use-campaign-insights";
import {
  useConcepts,
  useAdDescriptions,
  useCopyVariations,
  useAdMappings,
} from "@/hooks/use-metadata";
import { useDateRange } from "../../layout";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { KpiCell } from "@/components/kpi-cell";
import { RecommendationBanner } from "@/components/recommendation-banner";
import { AdMetadataPanel } from "@/components/ad-metadata-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { computeMetrics } from "@/lib/metrics";
import { evaluateKpis, getRecommendation } from "@/lib/recommendations";
import { softBenchmarks, hardBenchmarks } from "@/lib/benchmarks";
import { parseAdName } from "@/lib/meta-fields";

const FRONT_END_PRICE = parseFloat(process.env.NEXT_PUBLIC_FRONT_END_PRICE || "69.95");

export default function AdDetail() {
  const { campaignId, adId } = useParams<{
    campaignId: string;
    adId: string;
  }>();
  const { dateRange } = useDateRange();
  const { ad, isLoading: adLoading } = useSingleAdInsights(adId, dateRange);
  const { insights: campaignInsightsRaw } = useCampaignInsights(campaignId, dateRange);
  const { concepts } = useConcepts(campaignId);
  const { mappings } = useAdMappings(campaignId);

  const campaignSpend = campaignInsightsRaw ? computeMetrics(campaignInsightsRaw).spend : 0;

  const adName = (ad?.name as string) || "";
  const parsed = parseAdName(adName);
  const mapping = mappings.find((m) => m.ad_name === adName);

  const filename = mapping?.filename || parsed?.filename;
  const conceptName = mapping?.concept_name || parsed?.concept;
  const subGroupName = mapping?.sub_group_name || parsed?.subGroup;

  const { descriptions } = useAdDescriptions(campaignId, filename);
  const { variations } = useCopyVariations(campaignId, conceptName, subGroupName);

  const concept = concepts.find((c) => c.name === conceptName) || null;
  const description = descriptions.length > 0 ? descriptions[0] : null;

  // Compute metrics
  const insightsData = (ad?.insights as { data: Record<string, unknown>[] })?.data?.[0];
  const metrics = insightsData
    ? computeMetrics(insightsData)
    : null;
  const recommendation = metrics
    ? getRecommendation(metrics, FRONT_END_PRICE, campaignSpend)
    : null;

  const kpis = metrics ? evaluateKpis(metrics, FRONT_END_PRICE) : [];
  const softKpis = kpis.filter((k) =>
    softBenchmarks.some((sb) => sb.key === k.benchmark.key)
  );
  const hardKpis = kpis.filter((k) =>
    hardBenchmarks.some((hb) => hb.key === k.benchmark.key)
  );

  if (adLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-6 w-64 rounded" />
        <Skeleton className="h-20 rounded-lg" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-72 rounded-lg" />
          <Skeleton className="h-72 rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumbs */}
      <Breadcrumbs
        items={[
          { label: "Campaign", href: `/${campaignId}` },
          { label: "Ad" },
          { label: filename || adName },
        ]}
      />

      {/* Header */}
      <h2 className="text-2xl font-bold tracking-tight">{filename || adName}</h2>

      {/* Recommendation banner */}
      {recommendation && (
        <RecommendationBanner recommendation={recommendation} />
      )}

      {conceptName && (
        <p className="text-sm text-muted-foreground">
          Concept: <span className="font-medium">{conceptName}</span>
          {subGroupName && (
            <>
              {" "}/ Sub-group: <span className="font-medium">{subGroupName}</span>
            </>
          )}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Metrics */}
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Ad Performance</CardTitle>
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

        {/* Right: Pipeline metadata — the feedback loop */}
        <AdMetadataPanel
          description={description}
          copyVariations={variations}
          concept={concept}
          subGroupName={subGroupName}
        />
      </div>
    </div>
  );
}
