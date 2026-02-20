"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { DateRange } from "@/lib/types";

interface Props {
  value: DateRange;
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
  return d.toISOString().split("T")[0];
}

function getRange(days: number): DateRange {
  const now = new Date();
  if (days === 0) {
    const today = formatDate(now);
    return { since: today, until: today };
  }
  if (days === -1) {
    // Lifetime = last 365 days
    const since = new Date(now);
    since.setDate(since.getDate() - 365);
    return { since: formatDate(since), until: formatDate(now) };
  }
  const since = new Date(now);
  since.setDate(since.getDate() - days);
  return { since: formatDate(since), until: formatDate(now) };
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
          value={value.since}
          onChange={(e) => {
            setActive("");
            onChange({ ...value, since: e.target.value });
          }}
          className="text-xs border rounded px-2 py-1"
        />
        <span className="text-xs text-muted-foreground">to</span>
        <input
          type="date"
          value={value.until}
          onChange={(e) => {
            setActive("");
            onChange({ ...value, until: e.target.value });
          }}
          className="text-xs border rounded px-2 py-1"
        />
      </div>
    </div>
  );
}
