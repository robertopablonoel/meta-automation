"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RecommendationBadge } from "@/components/recommendation-badge";
import { getMetricColor } from "@/lib/benchmarks";
import { formatCurrency, formatPercent } from "@/lib/utils";
import type { WinnerAd } from "@/lib/types";

function WinnerCard({
  ad,
  campaignId,
  accent,
}: {
  ad: WinnerAd;
  campaignId: string;
  accent: "green" | "yellow";
}) {
  const borderClass =
    accent === "green"
      ? "border-green-200 dark:border-green-800"
      : "border-yellow-200 dark:border-yellow-800";
  const bgClass =
    accent === "green"
      ? "bg-green-50/50 dark:bg-green-950/30"
      : "bg-yellow-50/50 dark:bg-yellow-950/30";

  return (
    <Link href={`/${campaignId}/ads/${ad.id}`}>
      <div
        className={`rounded-lg border p-3 ${borderClass} ${bgClass} hover:shadow-md transition-shadow cursor-pointer`}
      >
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium truncate">
              {ad.conceptName || ad.name}
            </p>
            {ad.filename && (
              <p className="text-xs text-muted-foreground truncate">
                {ad.filename}
              </p>
            )}
          </div>
          <RecommendationBadge recommendation={ad.recommendation} />
        </div>

        <div className="grid grid-cols-4 gap-2 text-xs">
          <div>
            <span className="text-muted-foreground">ROAS</span>
            <p className={`font-medium ${getMetricColor("roas", ad.metrics.roas)}`}>
              {ad.metrics.roas > 0 ? ad.metrics.roas.toFixed(2) + "x" : "-"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">CPC</span>
            <p className={`font-medium ${getMetricColor("cpc", ad.metrics.cpc)}`}>
              {ad.metrics.cpc > 0 ? formatCurrency(ad.metrics.cpc) : "-"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">CTR</span>
            <p className={`font-medium ${getMetricColor("ctr", ad.metrics.ctr)}`}>
              {ad.metrics.ctr > 0 ? formatPercent(ad.metrics.ctr) : "-"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">CVR</span>
            <p className={`font-medium ${getMetricColor("cvr", ad.metrics.cvr)}`}>
              {ad.metrics.cvr > 0 ? formatPercent(ad.metrics.cvr) : "-"}
            </p>
          </div>
        </div>

        <div className="mt-2 text-[10px] text-muted-foreground">
          {ad.kpiSummary.confidentlyPassing}/{ad.kpiSummary.total} KPIs confident
          {" | "}
          {formatCurrency(ad.metrics.spend)} spent
        </div>
      </div>
    </Link>
  );
}

export function WinnersSection({
  winners,
  trending,
  campaignId,
  isLoading,
}: {
  winners: WinnerAd[];
  trending: WinnerAd[];
  campaignId: string;
  isLoading: boolean;
}) {
  if (isLoading) {
    return null;
  }

  if (winners.length === 0 && trending.length === 0) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Winners */}
      {winners.length > 0 && (
        <Card className="border-green-200 dark:border-green-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
              Winners ({winners.length})
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              High confidence KPIs are passing
            </p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3">
              {winners.map((ad) => (
                <WinnerCard
                  key={ad.id}
                  ad={ad}
                  campaignId={campaignId}
                  accent="green"
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Trending */}
      {trending.length > 0 && (
        <Card className="border-yellow-200 dark:border-yellow-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-yellow-500" />
              Trending ({trending.length})
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Promising metrics, needs more data
            </p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3">
              {trending.map((ad) => (
                <WinnerCard
                  key={ad.id}
                  ad={ad}
                  campaignId={campaignId}
                  accent="yellow"
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
