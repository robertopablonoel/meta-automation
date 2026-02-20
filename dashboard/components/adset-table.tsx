"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RecommendationBadge } from "./recommendation-badge";
import { formatCurrency, formatPercent, formatNumber } from "@/lib/utils";
import { getMetricColor } from "@/lib/benchmarks";
import type { AdSetRow } from "@/lib/types";

function extractStageNumbers(text: string): string {
  const match = text.match(/Stage\s+([\d][\d\s,\-]*[\d]?)/i);
  if (match) return match[1].trim();
  const numMatch = text.match(/^[\d][\d\s,\-]*/);
  if (numMatch) return numMatch[0].trim();
  return text.slice(0, 10);
}

const stripeClass: Record<string, string> = {
  Kill: "row-stripe-kill",
  Watch: "row-stripe-watch",
  Scale: "row-stripe-scale",
  Starving: "row-stripe-starving",
};

type SortKey = "name" | "spend" | "impressions" | "cpm" | "ctr" | "hookRate" | "holdRate" | "cpc" | "cvr" | "cpa" | "roas" | "recommendation";

interface Props {
  adsets: AdSetRow[];
  campaignId: string;
}

export function AdSetTable({ adsets, campaignId }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("spend");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    return [...adsets].sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      switch (sortKey) {
        case "name":
          aVal = a.name;
          bVal = b.name;
          break;
        case "recommendation":
          const order = { Kill: 0, Starving: 1, Watch: 2, Scale: 3 };
          aVal = order[a.recommendation.action];
          bVal = order[b.recommendation.action];
          break;
        default:
          aVal = (a.metrics as unknown as Record<string, number | null>)[sortKey] ?? 0;
          bVal = (b.metrics as unknown as Record<string, number | null>)[sortKey] ?? 0;
      }

      if (aVal < bVal) return sortAsc ? -1 : 1;
      if (aVal > bVal) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [adsets, sortKey, sortAsc]);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const SortHeader = ({ label, sKey }: { label: string; sKey: SortKey }) => (
    <TableHead
      className="cursor-pointer hover:text-foreground select-none text-xs whitespace-nowrap"
      onClick={() => handleSort(sKey)}
    >
      {label} {sortKey === sKey ? (sortAsc ? "↑" : "↓") : ""}
    </TableHead>
  );

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40">
            <SortHeader label="Ad Set" sKey="name" />
            <TableHead className="text-xs">Stage</TableHead>
            <SortHeader label="Action" sKey="recommendation" />
            <SortHeader label="Spend" sKey="spend" />
            <SortHeader label="CPC" sKey="cpc" />
            <SortHeader label="Impr." sKey="impressions" />
            <SortHeader label="CPM" sKey="cpm" />
            <SortHeader label="CTR" sKey="ctr" />
            <SortHeader label="Hook" sKey="hookRate" />
            <SortHeader label="Hold" sKey="holdRate" />
            <SortHeader label="CVR" sKey="cvr" />
            <SortHeader label="CPA" sKey="cpa" />
            <SortHeader label="ROAS" sKey="roas" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((adset, i) => (
            <TableRow
              key={adset.id}
              className={`${stripeClass[adset.recommendation.action] || ""} ${
                i % 2 === 0 ? "" : "bg-muted/20"
              } hover:bg-muted/40 transition-colors`}
            >
              <TableCell className="max-w-[250px]">
                <Link
                  href={`/${campaignId}/adsets/${adset.id}`}
                  className="hover:underline font-medium text-sm block truncate"
                >
                  {adset.conceptDisplayName || adset.name}
                </Link>
                {adset.conceptDisplayName && (
                  <div className="text-[11px] text-muted-foreground truncate">{adset.name}</div>
                )}
              </TableCell>
              <TableCell>
                {adset.awarenessStage ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-xs font-medium cursor-help underline decoration-dotted decoration-muted-foreground">
                        {extractStageNumbers(adset.awarenessStage)}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-sm text-xs">
                      {adset.awarenessStage}
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  <span className="text-xs text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell>
                {adset.adActions && adset.adActions.kill > 0 ? (
                  <div className="flex items-center gap-1.5">
                    <RecommendationBadge recommendation={adset.recommendation} />
                    <span className="text-[11px] text-red-600 dark:text-red-400 whitespace-nowrap">
                      {adset.adActions.kill} ad{adset.adActions.kill > 1 ? "s" : ""} to kill
                    </span>
                  </div>
                ) : (
                  <RecommendationBadge recommendation={adset.recommendation} />
                )}
              </TableCell>
              <TableCell className="tabular-nums text-sm">{formatCurrency(adset.metrics.spend)}</TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${getMetricColor("cpc", adset.metrics.cpc)}`}>{formatCurrency(adset.metrics.cpc)}</TableCell>
              <TableCell className="tabular-nums text-sm">{formatNumber(adset.metrics.impressions)}</TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${getMetricColor("cpm", adset.metrics.cpm)}`}>{formatCurrency(adset.metrics.cpm)}</TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${getMetricColor("ctr", adset.metrics.ctr)}`}>{formatPercent(adset.metrics.ctr)}</TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${adset.metrics.hookRate != null ? getMetricColor("hookRate", adset.metrics.hookRate) : ""}`}>
                {adset.metrics.hookRate != null ? formatPercent(adset.metrics.hookRate) : "-"}
              </TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${adset.metrics.holdRate != null ? getMetricColor("holdRate", adset.metrics.holdRate) : ""}`}>
                {adset.metrics.holdRate != null ? formatPercent(adset.metrics.holdRate) : "-"}
              </TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${getMetricColor("cvr", adset.metrics.cvr)}`}>{formatPercent(adset.metrics.cvr)}</TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${adset.metrics.cpa > 0 ? getMetricColor("cpa", adset.metrics.cpa) : ""}`}>
                {adset.metrics.cpa > 0 ? formatCurrency(adset.metrics.cpa) : "-"}
              </TableCell>
              <TableCell className={`tabular-nums text-sm font-medium ${adset.metrics.roas > 0 ? getMetricColor("roas", adset.metrics.roas) : ""}`}>
                {adset.metrics.roas > 0
                  ? `${adset.metrics.roas.toFixed(2)}x`
                  : "-"}
              </TableCell>
            </TableRow>
          ))}
          {sorted.length === 0 && (
            <TableRow>
              <TableCell colSpan={13} className="text-center text-muted-foreground py-12">
                <div className="space-y-2">
                  <p className="text-sm font-medium">No ad sets found</p>
                  <p className="text-xs">Try selecting a different date range or campaign</p>
                </div>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
