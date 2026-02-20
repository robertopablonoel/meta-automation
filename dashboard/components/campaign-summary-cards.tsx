"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatNumber } from "@/lib/utils";
import type { ComputedMetrics } from "@/lib/types";

interface Props {
  metrics: ComputedMetrics;
}

export function CampaignSummaryCards({ metrics }: Props) {
  const cards = [
    {
      title: "Spend",
      value: formatCurrency(metrics.spend),
      sub: `${formatNumber(metrics.impressions)} impressions`,
    },
    {
      title: "Purchases",
      value: formatNumber(metrics.purchases),
      sub: `${formatNumber(metrics.addToCart)} add to cart`,
    },
    {
      title: "ROAS",
      value: `${metrics.roas.toFixed(2)}x`,
      sub: `${formatCurrency(metrics.purchaseValue)} revenue`,
    },
    {
      title: "CPA",
      value: metrics.cpa > 0 ? formatCurrency(metrics.cpa) : "N/A",
      sub: `CPC ${formatCurrency(metrics.cpc)}`,
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">
              {card.title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{card.value}</div>
            <p className="text-xs text-muted-foreground mt-1">{card.sub}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
