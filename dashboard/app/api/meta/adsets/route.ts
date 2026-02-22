import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";
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
    // If date range provided, fetch from Meta directly
    if (since && until) {
      const adsets = await getAdSetInsights(campaignId, { since, until });
      return NextResponse.json({ data: adsets });
    }

    // Otherwise use Supabase cache (lifetime)
    const { data: rows, error } = await getSupabase()
      .from("metrics_cache")
      .select("entity_id, name, status, campaign_id, insights")
      .eq("entity_type", "adset")
      .eq("campaign_id", campaignId);

    if (error) throw new Error(error.message);

    const adsets = (rows ?? []).map((row) => ({
      id: row.entity_id,
      name: row.name,
      status: row.status,
      campaign_id: row.campaign_id,
      insights: row.insights ? { data: [row.insights] } : { data: [] },
    }));

    return NextResponse.json({ data: adsets });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
