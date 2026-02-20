"use client";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Recommendation } from "@/lib/types";

const styles: Record<string, string> = {
  Kill: "bg-red-100 text-red-700 border-red-200",
  Watch: "bg-yellow-100 text-yellow-700 border-yellow-200",
  Scale: "bg-green-100 text-green-700 border-green-200",
  Starving: "bg-gray-100 text-gray-500 border-gray-200",
};

export function RecommendationBadge({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className={styles[recommendation.action]}>
          {recommendation.action}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <ul className="text-xs space-y-1">
          {recommendation.reasoning.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  );
}
