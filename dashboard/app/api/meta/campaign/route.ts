import { NextRequest, NextResponse } from "next/server";
import { getCampaignInsights } from "@/lib/meta-api";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const id = searchParams.get("id");
  const since = searchParams.get("since");
  const until = searchParams.get("until");

  if (!id) {
    return NextResponse.json({ error: "Missing id parameter" }, { status: 400 });
  }

  try {
    const dateRange = since && until ? { since, until } : undefined;
    const insights = await getCampaignInsights(id, dateRange);
    return NextResponse.json({ data: insights });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
