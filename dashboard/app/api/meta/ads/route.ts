import { NextRequest, NextResponse } from "next/server";
import { getAdInsights, getSingleAdInsights } from "@/lib/meta-api";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const adsetId = searchParams.get("adset_id");
  const adId = searchParams.get("ad_id");
  const since = searchParams.get("since");
  const until = searchParams.get("until");

  if (!adsetId && !adId) {
    return NextResponse.json(
      { error: "Missing adset_id or ad_id parameter" },
      { status: 400 }
    );
  }

  try {
    const dateRange = since && until ? { since, until } : undefined;

    if (adId) {
      const ad = await getSingleAdInsights(adId, dateRange);
      return NextResponse.json({ data: ad });
    }

    const ads = await getAdInsights(adsetId!, dateRange);
    return NextResponse.json({ data: ads });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
