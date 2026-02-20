import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const campaignId = searchParams.get("campaign_id");
  const conceptName = searchParams.get("concept_name");
  const subGroupName = searchParams.get("sub_group_name");

  if (!campaignId) {
    return NextResponse.json(
      { error: "Missing campaign_id parameter" },
      { status: 400 }
    );
  }

  try {
    let query = supabase
      .from("copy_variations")
      .select("*")
      .eq("campaign_id", campaignId);

    if (conceptName) {
      query = query.eq("concept_name", conceptName);
    }
    if (subGroupName) {
      query = query.eq("sub_group_name", subGroupName);
    }

    const { data, error } = await query.order("variation_number");
    if (error) throw error;
    return NextResponse.json({ data });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
