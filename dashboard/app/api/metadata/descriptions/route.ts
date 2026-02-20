import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const campaignId = searchParams.get("campaign_id");
  const filename = searchParams.get("filename");

  if (!campaignId) {
    return NextResponse.json(
      { error: "Missing campaign_id parameter" },
      { status: 400 }
    );
  }

  try {
    let query = supabase
      .from("ad_descriptions")
      .select("*")
      .eq("campaign_id", campaignId);

    if (filename) {
      query = query.eq("filename", filename);
    }

    const { data, error } = await query;
    if (error) throw error;
    return NextResponse.json({ data });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
