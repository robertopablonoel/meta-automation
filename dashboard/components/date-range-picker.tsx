"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "lucide-react";
import type { DateRange } from "@/lib/types";

interface Props {
  value: DateRange | undefined;
  onChange: (range: DateRange | undefined) => void;
}

const presets = [
  { label: "Yesterday", days: -2 },
  { label: "Today", days: 0 },
  { label: "7d", days: 7 },
  { label: "14d", days: 14 },
  { label: "30d", days: 30 },
  { label: "Lifetime", days: -1 },
];

function formatDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getRange(days: number): DateRange | undefined {
  if (days === -1) return undefined; // Lifetime = Supabase cache
  if (days === -2) {
    // Yesterday
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const d = formatDate(yesterday);
    return { since: d, until: d };
  }
  const now = new Date();
  const today = formatDate(now);
  if (days === 0) return { since: today, until: today };
  const since = new Date(now);
  since.setDate(since.getDate() - days);
  return { since: formatDate(since), until: today };
}

export function DateRangePicker({ value, onChange }: Props) {
  const [active, setActive] = useState("Lifetime");
  const [showCustom, setShowCustom] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);

  // Close custom picker on outside click
  useEffect(() => {
    if (!showCustom) return;
    function handleClick(e: MouseEvent) {
      if (popRef.current && !popRef.current.contains(e.target as Node)) {
        setShowCustom(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showCustom]);

  return (
    <div className="flex items-center gap-1">
      {presets.map((preset) => (
        <Button
          key={preset.label}
          variant={active === preset.label ? "default" : "outline"}
          size="sm"
          onClick={() => {
            setActive(preset.label);
            setShowCustom(false);
            onChange(getRange(preset.days));
          }}
        >
          {preset.label}
        </Button>
      ))}
      <div className="relative ml-1">
        <Button
          variant={active === "custom" ? "default" : "outline"}
          size="sm"
          onClick={() => setShowCustom((v) => !v)}
          title="Custom date range"
        >
          <Calendar className="h-3.5 w-3.5" />
        </Button>
        {showCustom && (
          <div
            ref={popRef}
            className="absolute right-0 top-full mt-1 bg-popover border rounded-md shadow-lg p-3 z-20 flex items-center gap-2"
          >
            <input
              type="date"
              value={value?.since ?? ""}
              onChange={(e) => {
                setActive("custom");
                onChange({
                  since: e.target.value,
                  until: value?.until ?? formatDate(new Date()),
                });
              }}
              className="text-xs border rounded px-2 py-1 bg-background"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={value?.until ?? ""}
              onChange={(e) => {
                setActive("custom");
                onChange({
                  since: value?.since ?? "2020-01-01",
                  until: e.target.value,
                });
              }}
              className="text-xs border rounded px-2 py-1 bg-background"
            />
          </div>
        )}
      </div>
    </div>
  );
}
