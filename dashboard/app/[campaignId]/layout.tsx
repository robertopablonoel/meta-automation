"use client";

import { CampaignSelector } from "@/components/campaign-selector";
import { DateRangePicker } from "@/components/date-range-picker";
import { ThemeToggle } from "@/components/theme-toggle";
import { useSyncStatus } from "@/hooks/use-sync-status";
import { formatRelativeTime } from "@/lib/utils";
import { RefreshCw } from "lucide-react";
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
  // Default to Lifetime (undefined = use Supabase cache)
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);

  const { lastSyncedAt, isSyncing, triggerSync } = useSyncStatus();

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
              <button
                onClick={triggerSync}
                disabled={isSyncing}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                title={isSyncing ? "Syncing..." : "Refresh metrics from Meta"}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? "animate-spin" : ""}`} />
                {isSyncing
                  ? "Syncing..."
                  : lastSyncedAt
                    ? `Synced ${formatRelativeTime(lastSyncedAt)}`
                    : "Sync"}
              </button>
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
