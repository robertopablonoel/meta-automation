"use client";

import type { Recommendation } from "@/lib/types";

const bannerStyles: Record<string, { bg: string; border: string; icon: string }> = {
  Kill: {
    bg: "bg-red-50 dark:bg-red-950/30",
    border: "border-red-200 dark:border-red-800",
    icon: "text-red-600 dark:text-red-400",
  },
  Watch: {
    bg: "bg-yellow-50 dark:bg-yellow-950/30",
    border: "border-yellow-200 dark:border-yellow-800",
    icon: "text-yellow-600 dark:text-yellow-400",
  },
  Scale: {
    bg: "bg-green-50 dark:bg-green-950/30",
    border: "border-green-200 dark:border-green-800",
    icon: "text-green-600 dark:text-green-400",
  },
  Starving: {
    bg: "bg-gray-50 dark:bg-gray-900/50",
    border: "border-gray-200 dark:border-gray-700",
    icon: "text-gray-500 dark:text-gray-400",
  },
};

function getActionLabel(action: string, entityLabel: string): string {
  switch (action) {
    case "Kill": return `Kill — Turn off this ${entityLabel}`;
    case "Watch": return `Watch — Needs more data`;
    case "Scale": return `Scale — Increase budget`;
    case "Starving": return `Starving — Not enough spend`;
    default: return action;
  }
}

export function RecommendationBanner({
  recommendation,
  entityLabel = "ad",
}: {
  recommendation: Recommendation;
  entityLabel?: string;
}) {
  const style = bannerStyles[recommendation.action] || bannerStyles.Watch;

  return (
    <div className={`rounded-lg border ${style.bg} ${style.border} p-4`}>
      <div className="flex items-start gap-3">
        <div className={`text-2xl font-bold ${style.icon}`}>
          {recommendation.action === "Kill" && "!!"}
          {recommendation.action === "Watch" && "?"}
          {recommendation.action === "Scale" && "++"}
          {recommendation.action === "Starving" && "..."}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className={`text-sm font-semibold ${style.icon}`}>
            {getActionLabel(recommendation.action, entityLabel)}
          </h3>
          <ul className="mt-1.5 space-y-0.5">
            {recommendation.reasoning.map((r, i) => (
              <li key={i} className="text-xs text-muted-foreground">{r}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
