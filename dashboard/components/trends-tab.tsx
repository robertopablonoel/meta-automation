"use client";

import { useMemo } from "react";
import { useDailySnapshots } from "@/hooks/use-daily-snapshots";
import { computeMetrics } from "@/lib/metrics";
import { TrendChart } from "@/components/trend-chart";
import { Skeleton } from "@/components/ui/skeleton";
import type { DailyMetricRow } from "@/lib/types";

interface TrendsTabProps {
  campaignId: string;
}

export function TrendsTab({ campaignId }: TrendsTabProps) {
  const { snapshots, isLoading } = useDailySnapshots(campaignId);

  const rows: DailyMetricRow[] = useMemo(
    () =>
      snapshots.map((s) => ({
        date: s.date,
        metrics: computeMetrics(s.insights),
      })),
    [snapshots]
  );

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-64 rounded-lg" />
        ))}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No daily data yet. Run a sync to populate daily snapshots.
      </div>
    );
  }

  const charts: { title: string; key: keyof DailyMetricRow["metrics"]; format: "currency" | "percent" | "multiplier" | "number" }[] = [
    { title: "Daily Spend", key: "spend", format: "currency" },
    { title: "CPC", key: "cpc", format: "currency" },
    { title: "CTR", key: "ctr", format: "percent" },
    { title: "CVR", key: "cvr", format: "percent" },
    { title: "CPA", key: "cpa", format: "currency" },
    { title: "ROAS", key: "roas", format: "multiplier" },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {charts.map((chart) => (
        <TrendChart
          key={chart.key}
          title={chart.title}
          format={chart.format}
          data={rows.map((r) => ({
            date: r.date,
            value: r.metrics[chart.key] as number,
          }))}
        />
      ))}
    </div>
  );
}
