"use client";

import { useMemo, useState } from "react";
import { useDailySnapshots } from "@/hooks/use-daily-snapshots";
import { computeMetrics } from "@/lib/metrics";
import { getMetricColor } from "@/lib/benchmarks";
import { formatCurrency, formatPercent, formatNumber } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DailyMetricRow } from "@/lib/types";

interface DailyLogTabProps {
  campaignId: string;
}

type SortKey =
  | "date"
  | "spend"
  | "impressions"
  | "clicks"
  | "cpc"
  | "ctr"
  | "purchases"
  | "purchaseValue"
  | "cvr"
  | "cpa"
  | "roas"
  | "frequency";

const columns: { key: SortKey; label: string }[] = [
  { key: "date", label: "Date" },
  { key: "spend", label: "Spend" },
  { key: "impressions", label: "Impr" },
  { key: "clicks", label: "Clicks" },
  { key: "frequency", label: "Freq" },
  { key: "cpc", label: "CPC" },
  { key: "ctr", label: "CTR" },
  { key: "purchases", label: "Purchases" },
  { key: "purchaseValue", label: "Revenue" },
  { key: "cvr", label: "CVR" },
  { key: "cpa", label: "CPA" },
  { key: "roas", label: "ROAS" },
];

function formatCell(key: SortKey, row: DailyMetricRow): string {
  if (key === "date") {
    const d = new Date(row.date + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  const v = row.metrics[key as keyof typeof row.metrics] as number;
  switch (key) {
    case "spend":
    case "cpc":
    case "cpa":
    case "purchaseValue":
      return formatCurrency(v);
    case "ctr":
    case "cvr":
      return formatPercent(v);
    case "roas":
      return `${v.toFixed(2)}x`;
    case "frequency":
      return v.toFixed(2);
    default:
      return formatNumber(v);
  }
}

function cellColor(key: SortKey, row: DailyMetricRow): string {
  if (key === "date" || key === "spend" || key === "impressions" || key === "clicks" || key === "purchases" || key === "purchaseValue" ) return "";
  return getMetricColor(key, row.metrics[key as keyof typeof row.metrics] as number);
}

export function DailyLogTab({ campaignId }: DailyLogTabProps) {
  const { snapshots, isLoading } = useDailySnapshots(campaignId);
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortAsc, setSortAsc] = useState(false);

  const rows: DailyMetricRow[] = useMemo(
    () =>
      snapshots.map((s) => ({
        date: s.date,
        metrics: computeMetrics(s.insights),
      })),
    [snapshots]
  );

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      let av: number, bv: number;
      if (sortKey === "date") {
        av = new Date(a.date).getTime();
        bv = new Date(b.date).getTime();
      } else {
        av = a.metrics[sortKey as keyof typeof a.metrics] as number;
        bv = b.metrics[sortKey as keyof typeof b.metrics] as number;
      }
      return sortAsc ? av - bv : bv - av;
    });
    return copy;
  }, [rows, sortKey, sortAsc]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  if (isLoading) {
    return <Skeleton className="h-96 rounded-lg" />;
  }

  if (rows.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No daily data yet. Run a sync to populate daily snapshots.
      </div>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Daily Log ({rows.length} days)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className="text-left py-2 px-3 font-medium text-muted-foreground cursor-pointer hover:text-foreground whitespace-nowrap"
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                    {sortKey === col.key && (
                      <span className="ml-1">{sortAsc ? "↑" : "↓"}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <tr key={row.date} className="border-b last:border-0 hover:bg-muted/50">
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={`py-2 px-3 tabular-nums whitespace-nowrap ${cellColor(col.key, row)}`}
                    >
                      {formatCell(col.key, row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
