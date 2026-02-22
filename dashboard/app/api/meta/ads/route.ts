import { NextRequest, NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";
import { getAdInsights, getSingleAdInsights } from "@/lib/meta-api";

interface MetricsCacheRow {
  entity_id: string;
  name: string;
  status: string;
  parent_id: string;
  insights: Record<string, unknown> | null;
  extra_fields: { creative?: { id: string }; adset_id?: string } | null;
}

function rowToAd(row: MetricsCacheRow) {
  return {
    id: row.entity_id,
    name: row.name,
    status: row.status,
    adset_id: row.extra_fields?.adset_id ?? row.parent_id,
    creative: row.extra_fields?.creative ?? null,
    insights: row.insights ? { data: [row.insights] } : { data: [] },
  };
}

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
    // If date range provided, fetch from Meta directly
    if (since && until) {
      if (adId) {
        const ad = await getSingleAdInsights(adId, { since, until });
        return NextResponse.json({ data: ad });
      }
      const ads = await getAdInsights(adsetId!, { since, until });
      return NextResponse.json({ data: ads });
    }

    // Otherwise use Supabase cache (lifetime)
    if (adId) {
      const { data: row, error } = await getSupabase()
        .from("metrics_cache")
        .select("entity_id, name, status, parent_id, insights, extra_fields")
        .eq("entity_type", "ad")
        .eq("entity_id", adId)
        .single();

      if (error) throw new Error(error.message);

      return NextResponse.json({ data: rowToAd(row as MetricsCacheRow) });
    }

    const { data: rows, error } = await getSupabase()
      .from("metrics_cache")
      .select("entity_id, name, status, parent_id, insights, extra_fields")
      .eq("entity_type", "ad")
      .eq("parent_id", adsetId!);

    if (error) throw new Error(error.message);

    const ads = (rows as MetricsCacheRow[] ?? []).map(rowToAd);
    return NextResponse.json({ data: ads });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
