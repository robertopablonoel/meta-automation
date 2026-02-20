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
import { Badge } from "@/components/ui/badge";
import { RecommendationBadge } from "./recommendation-badge";
import { formatCurrency, formatPercent, formatNumber } from "@/lib/utils";
import { getMetricColor } from "@/lib/benchmarks";
import type { AdRow } from "@/lib/types";

type SortKey = "name" | "spend" | "impressions" | "cpm" | "ctr" | "cpc" | "cvr" | "cpa" | "roas";

interface Props {
  ads: AdRow[];
  campaignId: string;
}

export function AdTable({ ads, campaignId }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("spend");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    return [...ads].sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      if (sortKey === "name") {
        aVal = a.filename || a.name;
        bVal = b.filename || b.name;
      } else {
        aVal = (a.metrics as unknown as Record<string, number>)[sortKey] ?? 0;
        bVal = (b.metrics as unknown as Record<string, number>)[sortKey] ?? 0;
      }

      if (aVal < bVal) return sortAsc ? -1 : 1;
      if (aVal > bVal) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [ads, sortKey, sortAsc]);

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const SortHeader = ({ label, sKey }: { label: string; sKey: SortKey }) => (
    <TableHead
      className="cursor-pointer hover:text-foreground select-none"
      onClick={() => handleSort(sKey)}
    >
      {label} {sortKey === sKey ? (sortAsc ? "↑" : "↓") : ""}
    </TableHead>
  );

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortHeader label="Ad" sKey="name" />
          <TableHead>Action</TableHead>
          <TableHead>Type</TableHead>
          <SortHeader label="Spend" sKey="spend" />
          <SortHeader label="Impressions" sKey="impressions" />
          <SortHeader label="CPM" sKey="cpm" />
          <SortHeader label="CTR" sKey="ctr" />
          <SortHeader label="CPC" sKey="cpc" />
          <SortHeader label="CVR" sKey="cvr" />
          <SortHeader label="CPA" sKey="cpa" />
          <SortHeader label="ROAS" sKey="roas" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((ad) => (
          <TableRow key={ad.id}>
            <TableCell>
              <Link
                href={`/${campaignId}/ads/${ad.id}`}
                className="hover:underline font-medium"
              >
                {ad.filename || ad.name}
              </Link>
              {ad.conceptName && (
                <div className="text-xs text-muted-foreground">
                  {ad.conceptName} / {ad.subGroupName}
                </div>
              )}
            </TableCell>
            <TableCell>
              <RecommendationBadge recommendation={ad.recommendation} />
            </TableCell>
            <TableCell>
              {ad.mediaType && (
                <Badge variant="outline" className="text-xs">
                  {ad.mediaType}
                </Badge>
              )}
            </TableCell>
            <TableCell>{formatCurrency(ad.metrics.spend)}</TableCell>
            <TableCell>{formatNumber(ad.metrics.impressions)}</TableCell>
            <TableCell className={getMetricColor("cpm", ad.metrics.cpm)}>{formatCurrency(ad.metrics.cpm)}</TableCell>
            <TableCell className={getMetricColor("ctr", ad.metrics.ctr)}>{formatPercent(ad.metrics.ctr)}</TableCell>
            <TableCell className={getMetricColor("cpc", ad.metrics.cpc)}>{formatCurrency(ad.metrics.cpc)}</TableCell>
            <TableCell className={getMetricColor("cvr", ad.metrics.cvr)}>{formatPercent(ad.metrics.cvr)}</TableCell>
            <TableCell className={ad.metrics.cpa > 0 ? getMetricColor("cpa", ad.metrics.cpa) : ""}>
              {ad.metrics.cpa > 0 ? formatCurrency(ad.metrics.cpa) : "-"}
            </TableCell>
            <TableCell className={ad.metrics.roas > 0 ? getMetricColor("roas", ad.metrics.roas) : ""}>
              {ad.metrics.roas > 0 ? `${ad.metrics.roas.toFixed(2)}x` : "-"}
            </TableCell>
          </TableRow>
        ))}
        {sorted.length === 0 && (
          <TableRow>
            <TableCell colSpan={11} className="text-center text-muted-foreground py-8">
              No ads found
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
