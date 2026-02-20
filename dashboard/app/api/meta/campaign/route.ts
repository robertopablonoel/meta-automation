import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const id = searchParams.get("id");

  if (!id) {
    return NextResponse.json({ error: "Missing id parameter" }, { status: 400 });
  }

  try {
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
