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
import { RecommendationBadge } from "./recommendation-badge";
import { formatCurrency, formatPercent, formatNumber } from "@/lib/utils";
import type { AdSetRow } from "@/lib/types";

type SortKey = "name" | "spend" | "impressions" | "ctr" | "cpc" | "cvr" | "cpa" | "roas" | "recommendation";

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
          aVal = (a.metrics as unknown as Record<string, number>)[sortKey] ?? 0;
          bVal = (b.metrics as unknown as Record<string, number>)[sortKey] ?? 0;
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
          <SortHeader label="Ad Set" sKey="name" />
          <SortHeader label="Action" sKey="recommendation" />
          <SortHeader label="Spend" sKey="spend" />
          <SortHeader label="Impressions" sKey="impressions" />
          <SortHeader label="CTR" sKey="ctr" />
          <SortHeader label="CPC" sKey="cpc" />
          <SortHeader label="CVR" sKey="cvr" />
          <SortHeader label="CPA" sKey="cpa" />
          <SortHeader label="ROAS" sKey="roas" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((adset) => (
          <TableRow key={adset.id}>
            <TableCell>
              <Link
                href={`/${campaignId}/adsets/${adset.id}`}
                className="hover:underline font-medium"
              >
                {adset.conceptDisplayName || adset.name}
              </Link>
              {adset.conceptDisplayName && (
                <div className="text-xs text-muted-foreground">{adset.name}</div>
              )}
            </TableCell>
            <TableCell>
              <RecommendationBadge recommendation={adset.recommendation} />
            </TableCell>
            <TableCell>{formatCurrency(adset.metrics.spend)}</TableCell>
            <TableCell>{formatNumber(adset.metrics.impressions)}</TableCell>
            <TableCell>{formatPercent(adset.metrics.ctr)}</TableCell>
            <TableCell>{formatCurrency(adset.metrics.cpc)}</TableCell>
            <TableCell>{formatPercent(adset.metrics.cvr)}</TableCell>
            <TableCell>
              {adset.metrics.cpa > 0 ? formatCurrency(adset.metrics.cpa) : "-"}
            </TableCell>
            <TableCell>
              {adset.metrics.roas > 0
                ? `${adset.metrics.roas.toFixed(2)}x`
                : "-"}
            </TableCell>
          </TableRow>
        ))}
        {sorted.length === 0 && (
          <TableRow>
            <TableCell colSpan={9} className="text-center text-muted-foreground py-8">
              No ad sets found
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
