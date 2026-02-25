"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useCampaigns } from "@/hooks/use-campaigns";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

export function CampaignSelector() {
  const router = useRouter();
  const params = useParams();
  const currentCampaignId = params?.campaignId as string | undefined;
  const { campaigns, isLoading } = useCampaigns();
  const [showAll, setShowAll] = useState(false);

  if (isLoading) {
    return <Skeleton className="h-9 w-64" />;
  }

  const filtered = showAll
    ? campaigns
    : campaigns.filter((c) => c.status === "ACTIVE");

  return (
    <div className="flex items-center gap-4">
      <Select
        value={currentCampaignId ?? ""}
        onValueChange={(value) => {
          router.push(`/${value}`);
        }}
      >
        <SelectTrigger className="w-72">
          <SelectValue placeholder="Select a campaign..." />
        </SelectTrigger>
        <SelectContent>
          {filtered.map((campaign) => (
            <SelectItem key={campaign.id} value={campaign.id}>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    campaign.status === "ACTIVE"
                      ? "bg-green-500"
                      : campaign.status === "PAUSED"
                      ? "bg-yellow-500"
                      : "bg-gray-400"
                  }`}
                />
                <span className="truncate">{campaign.name}</span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="flex items-center gap-1.5">
        <Switch id="show-all-campaigns" checked={showAll} onCheckedChange={setShowAll} />
        <Label htmlFor="show-all-campaigns" className="text-xs text-muted-foreground cursor-pointer">
          Show all
        </Label>
      </div>
    </div>
  );
}
