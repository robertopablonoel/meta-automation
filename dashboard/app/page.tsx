"use client";

import { CampaignSelector } from "@/components/campaign-selector";

export default function Home() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-6">
        <h1 className="text-3xl font-bold">Meta Ads Dashboard</h1>
        <p className="text-muted-foreground">Select a campaign to get started</p>
        <CampaignSelector />
      </div>
    </div>
  );
}
