import { NextRequest, NextResponse } from "next/server";
import { getAdSetInsights } from "@/lib/meta-api";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const campaignId = searchParams.get("campaign_id");
  const since = searchParams.get("since");
  const until = searchParams.get("until");

  if (!campaignId) {
    return NextResponse.json(
      { error: "Missing campaign_id parameter" },
      { status: 400 }
    );
  }

  try {
    const dateRange = since && until ? { since, until } : undefined;
    const adsets = await getAdSetInsights(campaignId, dateRange);
    return NextResponse.json({ data: adsets });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
