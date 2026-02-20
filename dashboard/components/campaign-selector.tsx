"use client";

import { useRouter, useParams } from "next/navigation";
import { useCampaigns } from "@/hooks/use-campaigns";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

export function CampaignSelector() {
  const router = useRouter();
  const params = useParams();
  const currentCampaignId = params?.campaignId as string | undefined;
  const { campaigns, isLoading } = useCampaigns();

  if (isLoading) {
    return <Skeleton className="h-9 w-64" />;
  }

  return (
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
        {campaigns.map((campaign) => (
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
  );
}
