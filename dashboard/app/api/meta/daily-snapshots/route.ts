import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const campaignId = searchParams.get("campaignId");
  const days = parseInt(searchParams.get("days") || "30", 10);

  if (!campaignId) {
    return NextResponse.json({ error: "Missing campaignId parameter" }, { status: 400 });
  }

  try {
    const { data, error } = await getSupabase()
      .from("daily_snapshots")
      .select("date, insights")
      .eq("campaign_id", campaignId)
      .eq("entity_type", "campaign")
      .order("date", { ascending: true })
      .limit(days);

    if (error) throw new Error(error.message);

    return NextResponse.json({ data: data ?? [] });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
