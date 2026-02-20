"use client";

import { CampaignSelector } from "@/components/campaign-selector";
import { DateRangePicker } from "@/components/date-range-picker";
import { ThemeToggle } from "@/components/theme-toggle";
import { useState, createContext, useContext } from "react";
import type { DateRange } from "@/lib/types";

interface DateRangeContextValue {
  dateRange: DateRange | undefined;
  setDateRange: (range: DateRange | undefined) => void;
}

export const DateRangeContext = createContext<DateRangeContextValue>({
  dateRange: undefined,
  setDateRange: () => {},
});

export function useDateRange() {
  return useContext(DateRangeContext);
}

export default function CampaignLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Default to Lifetime: 36 months back through today
  const [dateRange, setDateRange] = useState<DateRange | undefined>(() => {
    const now = new Date();
    const since = new Date(now);
    since.setMonth(since.getMonth() - 36);
    const fmt = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { since: fmt(since), until: fmt(now) };
  });

  return (
    <DateRangeContext.Provider value={{ dateRange, setDateRange }}>
      <div className="min-h-screen">
        <header className="border-b bg-background/95 backdrop-blur-sm sticky top-0 z-10 shadow-sm">
          <div className="container mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h1 className="text-lg font-semibold tracking-tight">Meta Ads</h1>
              <CampaignSelector />
            </div>
            <div className="flex items-center gap-2">
              <DateRangePicker
                value={dateRange}
                onChange={setDateRange}
              />
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="container mx-auto px-4 py-8">{children}</main>
      </div>
    </DateRangeContext.Provider>
  );
}
