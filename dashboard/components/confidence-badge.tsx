"use client";

import { Badge } from "@/components/ui/badge";
import type { ConfidenceLevel } from "@/lib/types";

const styles: Record<ConfidenceLevel, string> = {
  none: "bg-gray-100 text-gray-500",
  low: "bg-yellow-100 text-yellow-700",
  medium: "bg-blue-100 text-blue-700",
  high: "bg-green-100 text-green-700",
};

const labels: Record<ConfidenceLevel, string> = {
  none: "No data",
  low: "Low",
  medium: "Medium",
  high: "High",
};

export function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  return (
    <Badge variant="outline" className={styles[level]}>
      {labels[level]}
    </Badge>
  );
}
