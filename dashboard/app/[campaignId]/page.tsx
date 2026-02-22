"use client";

import { useMemo, useCallback } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useCampaignInsights } from "@/hooks/use-campaign-insights";
import { useAdSetInsights } from "@/hooks/use-adset-insights";
import { useCampaignAds } from "@/hooks/use-campaign-ads";
import { useConcepts, useAdMappings } from "@/hooks/use-metadata";
import { useDateRange } from "./layout";
import { CampaignSummaryCards } from "@/components/campaign-summary-cards";
import { AdSetTable } from "@/components/adset-table";
import { WinnersSection } from "@/components/winners-section";
import { KpiCell } from "@/components/kpi-cell";
import { TrendsTab } from "@/components/trends-tab";
import { DailyLogTab } from "@/components/daily-log-tab";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { computeMetrics } from "@/lib/metrics";
import { evaluateKpis } from "@/lib/recommendations";
import { getRecommendation } from "@/lib/recommendations";
import { softBenchmarks, hardBenchmarks } from "@/lib/benchmarks";
import { parseAdName } from "@/lib/meta-fields";
import { classifyAd } from "@/lib/winners";
import type { AdSetRow, AdActionSummary, ComputedMetrics, WinnerAd } from "@/lib/types";

const FRONT_END_PRICE = parseFloat(process.env.NEXT_PUBLIC_FRONT_END_PRICE || "69.95");

export default function CampaignOverview() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { dateRange } = useDateRange();

  const activeTab = searchParams.get("tab") || "overview";

  const handleTabChange = useCallback(
    (value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value === "overview") {
        params.delete("tab");
      } else {
        params.set("tab", value);
      }
      const qs = params.toString();
      router.replace(`/${campaignId}${qs ? `?${qs}` : ""}`, { scroll: false });
    },
    [campaignId, router, searchParams]
  );

  const { insights, isLoading: insightsLoading } = useCampaignInsights(
    campaignId,
    dateRange
  );
  const { adsets, isLoading: adsetsLoading } = useAdSetInsights(
    campaignId,
    dateRange
  );
  const { ads: allAds, isLoading: adsLoading } = useCampaignAds(
    campaignId,
    dateRange
  );
  const { concepts } = useConcepts(campaignId);
  const { mappings } = useAdMappings(campaignId);

  const isLoading = insightsLoading || adsetsLoading;

  // Campaign spend for relative Starving thresholds
  const topLevelCampaignSpend = insights ? computeMetrics(insights).spend : 0;

  // Classify all ads into winners/trending
  const { winners, trending } = useMemo(() => {
    const w: WinnerAd[] = [];
    const t: WinnerAd[] = [];

    for (const ad of allAds) {
      const insightsData = (ad.insights as { data: Record<string, unknown>[] })?.data?.[0];
      if (!insightsData) continue;

      const metrics = computeMetrics(insightsData);
      const { classification, recommendation, kpis } = classifyAd(metrics, FRONT_END_PRICE, topLevelCampaignSpend);

      if (!classification) continue;

      const adName = ad.name as string;
      const parsed = parseAdName(adName);

      const winnerAd: WinnerAd = {
        id: ad.id as string,
        name: adName,
        adsetId: ad.adset_id as string,
        metrics,
        recommendation,
        classification,
        kpiSummary: {
          passing: kpis.filter((k) => k.passing).length,
          confidentlyPassing: kpis.filter((k) => k.confidentlyPassing).length,
          total: kpis.length,
        },
        conceptName: parsed?.concept,
        filename: parsed?.filename,
      };

      if (classification === "winner") {
        w.push(winnerAd);
      } else {
        t.push(winnerAd);
      }
    }

    // Sort by ROAS descending
    w.sort((a, b) => b.metrics.roas - a.metrics.roas);
    t.sort((a, b) => b.metrics.roas - a.metrics.roas);

    return { winners: w, trending: t };
  }, [allAds, topLevelCampaignSpend]);

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange}>
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="trends">Trends</TabsTrigger>
        <TabsTrigger value="daily-log">Daily Log</TabsTrigger>
      </TabsList>

      <TabsContent value="overview">
        {isLoading ? (
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
        ) : (
          <OverviewContent
            campaignId={campaignId}
            insights={insights}
            adsets={adsets}
            allAds={allAds}
            adsLoading={adsLoading}
            concepts={concepts}
            winners={winners}
            trending={trending}
          />
        )}
      </TabsContent>

      <TabsContent value="trends">
        <TrendsTab campaignId={campaignId} />
      </TabsContent>

      <TabsContent value="daily-log">
        <DailyLogTab campaignId={campaignId} />
      </TabsContent>
    </Tabs>
  );
}

function OverviewContent({
  campaignId,
  insights,
  adsets,
  allAds,
  adsLoading,
  concepts,
  winners,
  trending,
}: {
  campaignId: string;
  insights: Record<string, unknown> | null;
  adsets: Record<string, unknown>[];
  allAds: Record<string, unknown>[];
  adsLoading: boolean;
  concepts: { name: string; display_name: string | null; schwartz_sophistication: string | null }[];
  winners: WinnerAd[];
  trending: WinnerAd[];
}) {
  const campaignMetrics = insights ? computeMetrics(insights) : null;
  const campaignSpend = campaignMetrics?.spend ?? 0;

  // Compute per-ad recommendations grouped by adset
  const adActionsByAdset = useMemo(() => {
    const map = new Map<string, AdActionSummary>();
    for (const ad of allAds) {
      const adsetId = ad.adset_id as string;
      if (!adsetId) continue;
      const insightsData = (ad.insights as { data: Record<string, unknown>[] })?.data?.[0];
      if (!insightsData) continue;
      const m = computeMetrics(insightsData);
      const rec = getRecommendation(m, FRONT_END_PRICE, campaignSpend);
      const summary = map.get(adsetId) || { kill: 0, watch: 0, scale: 0, starving: 0, total: 0 };
      summary.total++;
      const key = rec.action.toLowerCase() as keyof Omit<AdActionSummary, "total">;
      summary[key]++;
      map.set(adsetId, summary);
    }
    return map;
  }, [allAds, campaignSpend]);

  // Build ad set rows with concept metadata
  const conceptMap = new Map(concepts.map((c) => [c.name, c]));

  const adsetRows: AdSetRow[] = adsets.map((adset: Record<string, unknown>) => {
    const insightsData = (adset.insights as { data: Record<string, unknown>[] })?.data?.[0];
    const metrics: ComputedMetrics = insightsData
      ? computeMetrics(insightsData)
      : computeMetrics({} as Record<string, unknown>);
    const recommendation = getRecommendation(metrics, FRONT_END_PRICE, campaignSpend);

    // Try to match ad set name to a concept
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
      adActions: adActionsByAdset.get(adset.id as string),
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

      {/* Winners & Trending */}
      <WinnersSection
        winners={winners}
        trending={trending}
        campaignId={campaignId}
        isLoading={adsLoading}
      />

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
