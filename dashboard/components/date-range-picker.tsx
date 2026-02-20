"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { DateRange } from "@/lib/types";

interface Props {
  value: DateRange | undefined;
  onChange: (range: DateRange) => void;
}

const presets = [
  { label: "Today", days: 0 },
  { label: "7d", days: 7 },
  { label: "14d", days: 14 },
  { label: "30d", days: 30 },
  { label: "Lifetime", days: -1 },
];

function formatDate(d: Date): string {
  // Use local date to avoid timezone issues
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getRange(days: number): DateRange {
  const now = new Date();
  const today = formatDate(now);
  if (days === 0) {
    return { since: today, until: today };
  }
  if (days === -1) {
    // Lifetime: go back 36 months (Meta's max is 37), include today
    const since = new Date(now);
    since.setMonth(since.getMonth() - 36);
    return { since: formatDate(since), until: today };
  }
  const since = new Date(now);
  since.setDate(since.getDate() - days);
  return { since: formatDate(since), until: today };
}

export function DateRangePicker({ value, onChange }: Props) {
  const [active, setActive] = useState("Lifetime");

  return (
    <div className="flex items-center gap-1">
      {presets.map((preset) => (
        <Button
          key={preset.label}
          variant={active === preset.label ? "default" : "outline"}
          size="sm"
          onClick={() => {
            setActive(preset.label);
            onChange(getRange(preset.days));
          }}
        >
          {preset.label}
        </Button>
      ))}
      <div className="flex items-center gap-1 ml-2">
        <input
          type="date"
          value={value?.since ?? ""}
          onChange={(e) => {
            setActive("");
            onChange({ since: e.target.value, until: value?.until ?? formatDate(new Date()) });
          }}
          className="text-xs border rounded px-2 py-1"
        />
        <span className="text-xs text-muted-foreground">to</span>
        <input
          type="date"
          value={value?.until ?? ""}
          onChange={(e) => {
            setActive("");
            onChange({ since: value?.since ?? "2020-01-01", until: e.target.value });
          }}
          className="text-xs border rounded px-2 py-1"
        />
      </div>
    </div>
  );
}
