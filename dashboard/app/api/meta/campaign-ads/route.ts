import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const campaignId = searchParams.get("campaign_id");

  if (!campaignId) {
    return NextResponse.json(
      { error: "Missing campaign_id parameter" },
      { status: 400 }
    );
  }

  try {
    const { data: rows, error } = await getSupabase()
      .from("metrics_cache")
      .select("entity_id, name, status, parent_id, insights, extra_fields")
      .eq("entity_type", "ad")
      .eq("campaign_id", campaignId);

    if (error) throw new Error(error.message);

    const ads = (rows ?? []).map((row) => ({
      id: row.entity_id,
      name: row.name,
      status: row.status,
      adset_id: row.extra_fields?.adset_id ?? row.parent_id,
      creative: row.extra_fields?.creative ?? null,
      insights: row.insights ? { data: [row.insights] } : { data: [] },
    }));

    return NextResponse.json({ data: ads });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
