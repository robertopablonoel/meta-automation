"use client";

import { useParams } from "next/navigation";
import { useCampaignInsights } from "@/hooks/use-campaign-insights";
import { useAdSetInsights } from "@/hooks/use-adset-insights";
import { useConcepts, useAdMappings } from "@/hooks/use-metadata";
import { useDateRange } from "./layout";
import { CampaignSummaryCards } from "@/components/campaign-summary-cards";
import { AdSetTable } from "@/components/adset-table";
import { KpiCell } from "@/components/kpi-cell";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { computeMetrics } from "@/lib/metrics";
import { evaluateKpis } from "@/lib/recommendations";
import { getRecommendation } from "@/lib/recommendations";
import { softBenchmarks, hardBenchmarks, getCpaTarget } from "@/lib/benchmarks";
import { parseAdName } from "@/lib/meta-fields";
import type { AdSetRow, ComputedMetrics } from "@/lib/types";

const FRONT_END_PRICE = parseFloat(process.env.NEXT_PUBLIC_FRONT_END_PRICE || "29.99");

export default function CampaignOverview() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const { dateRange } = useDateRange();
  const { insights, isLoading: insightsLoading } = useCampaignInsights(
    campaignId,
    dateRange
  );
  const { adsets, isLoading: adsetsLoading } = useAdSetInsights(
    campaignId,
    dateRange
  );
  const { concepts } = useConcepts(campaignId);
  const { mappings } = useAdMappings(campaignId);

  const isLoading = insightsLoading || adsetsLoading;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-72 rounded-lg" />
          <Skeleton className="h-72 rounded-lg" />
        </div>
        <Skeleton className="h-96 rounded-lg" />
      </div>
    );
  }

  const campaignMetrics = insights ? computeMetrics(insights) : null;

  // Build ad set rows with concept metadata
  const conceptMap = new Map(concepts.map((c) => [c.name, c]));

  const adsetRows: AdSetRow[] = adsets.map((adset: Record<string, unknown>) => {
    const insightsData = (adset.insights as { data: Record<string, unknown>[] })?.data?.[0];
    const metrics: ComputedMetrics = insightsData
      ? computeMetrics(insightsData)
      : computeMetrics({} as Record<string, unknown>);
    const recommendation = getRecommendation(metrics, FRONT_END_PRICE);

    // Try to match ad set name to a concept
    // Ad set names often contain the concept name
    const adsetName = adset.name as string;
    let conceptName: string | undefined;
    let conceptDisplayName: string | undefined;

    let awarenessStage: string | undefined;

    for (const [name, concept] of conceptMap) {
      if (adsetName.toLowerCase().includes(name.toLowerCase())) {
        conceptName = name;
        conceptDisplayName = concept.display_name || undefined;
        awarenessStage = concept.schwartz_sophistication || undefined;
        break;
      }
    }

    return {
      id: adset.id as string,
      name: adsetName,
      status: adset.status as string,
      metrics,
      recommendation,
      conceptName,
      conceptDisplayName,
      awarenessStage,
    };
  });

  // KPI evaluation at campaign level
  const kpis = campaignMetrics
    ? evaluateKpis(campaignMetrics, FRONT_END_PRICE)
    : [];

  const softKpis = kpis.filter((k) =>
    softBenchmarks.some((sb) => sb.key === k.benchmark.key)
  );
  const hardKpis = kpis.filter((k) =>
    hardBenchmarks.some((hb) => hb.key === k.benchmark.key)
  );

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      {campaignMetrics && <CampaignSummaryCards metrics={campaignMetrics} />}

      {/* KPI breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Ad Performance</CardTitle>
            <p className="text-xs text-muted-foreground">How your ads are performing at capturing attention</p>
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
            <p className="text-xs text-muted-foreground">How clicks are converting to revenue</p>
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

      {/* Ad Sets table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Ad Sets ({adsetRows.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AdSetTable adsets={adsetRows} campaignId={campaignId} />
        </CardContent>
      </Card>
    </div>
  );
}
