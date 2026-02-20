"use client";

import { Card, CardContent } from "@/components/ui/card";
import { formatCurrency, formatNumber } from "@/lib/utils";
import type { ComputedMetrics } from "@/lib/types";

interface Props {
  metrics: ComputedMetrics;
}

type Tint = "good" | "warn" | "bad" | "neutral";

function roasTint(roas: number): Tint {
  if (roas >= 2) return "good";
  if (roas >= 1) return "warn";
  if (roas > 0) return "bad";
  return "neutral";
}

function cpaTint(cpa: number): Tint {
  if (cpa === 0) return "neutral";
  if (cpa <= 69.95) return "good";
  if (cpa <= 104.93) return "warn";
  return "bad";
}

export function CampaignSummaryCards({ metrics }: Props) {
  const cards: { title: string; value: string; sub: string; tint: Tint }[] = [
    {
      title: "Spend",
      value: formatCurrency(metrics.spend),
      sub: `${formatNumber(metrics.impressions)} impressions`,
      tint: "neutral",
    },
    {
      title: "Purchases",
      value: formatNumber(metrics.purchases),
      sub: `${formatNumber(metrics.addToCart)} add to cart`,
      tint: metrics.purchases > 0 ? "good" : "neutral",
    },
    {
      title: "ROAS",
      value: `${metrics.roas.toFixed(2)}x`,
      sub: `${formatCurrency(metrics.purchaseValue)} revenue`,
      tint: roasTint(metrics.roas),
    },
    {
      title: "CPA",
      value: metrics.cpa > 0 ? formatCurrency(metrics.cpa) : "N/A",
      sub: `CPC ${formatCurrency(metrics.cpc)}`,
      tint: cpaTint(metrics.cpa),
    },
  ];

  const tintStyles = {
    good: "bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-800",
    warn: "bg-yellow-50 border-yellow-200 dark:bg-yellow-950/30 dark:border-yellow-800",
    bad: "bg-red-50 border-red-200 dark:bg-red-950/30 dark:border-red-800",
    neutral: "",
  };

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <Card key={card.title} className={`transition-shadow hover:shadow-md ${tintStyles[card.tint]}`}>
          <CardContent className="pt-5 pb-4">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {card.title}
            </p>
            <div className="text-3xl font-bold tabular-nums mt-1">{card.value}</div>
            <p className="text-xs text-muted-foreground mt-2">{card.sub}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
