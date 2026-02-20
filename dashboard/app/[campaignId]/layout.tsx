"use client";

import { CampaignSelector } from "@/components/campaign-selector";
import { DateRangePicker } from "@/components/date-range-picker";
import { useState, createContext, useContext } from "react";
import type { DateRange } from "@/lib/types";

interface DateRangeContextValue {
  dateRange: DateRange | undefined;
  setDateRange: (range: DateRange) => void;
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
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);

  return (
    <DateRangeContext.Provider value={{ dateRange, setDateRange }}>
      <div className="min-h-screen">
        <header className="border-b bg-background sticky top-0 z-10">
          <div className="container mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h1 className="text-lg font-semibold">Meta Ads</h1>
              <CampaignSelector />
            </div>
            <DateRangePicker
              value={
                dateRange || {
                  since: new Date(Date.now() - 365 * 86400000)
                    .toISOString()
                    .split("T")[0],
                  until: new Date().toISOString().split("T")[0],
                }
              }
              onChange={setDateRange}
            />
          </div>
        </header>
        <main className="container mx-auto px-4 py-6">{children}</main>
      </div>
    </DateRangeContext.Provider>
  );
}
