import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";
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
    // If date range provided, fetch from Meta directly
    if (since && until) {
      const insights = await getCampaignInsights(id, { since, until });
      return NextResponse.json({ data: insights });
    }

    // Otherwise use Supabase cache (lifetime)
    const { data, error } = await getSupabase()
      .from("metrics_cache")
      .select("insights")
      .eq("entity_type", "campaign")
      .eq("entity_id", id)
      .single();

    if (error) throw new Error(error.message);

    return NextResponse.json({ data: data?.insights ?? null });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
