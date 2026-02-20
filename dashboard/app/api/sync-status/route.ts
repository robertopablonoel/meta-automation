import { NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";
import { exec } from "child_process";

export async function GET() {
  try {
    const { data, error } = await getSupabase()
      .from("sync_log")
      .select("completed_at, campaigns_synced, adsets_synced, ads_synced")
      .eq("status", "completed")
      .order("completed_at", { ascending: false })
      .limit(1)
      .single();

    if (error) {
      return NextResponse.json({
        data: { lastSyncedAt: null, counts: null },
      });
    }

    return NextResponse.json({
      data: {
        lastSyncedAt: data.completed_at,
        counts: {
          campaigns: data.campaigns_synced,
          adsets: data.adsets_synced,
          ads: data.ads_synced,
        },
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function POST() {
  try {
    // Fire-and-forget: run metrics_sync.py in background
    const cmd = "cd .. && venv/bin/python metrics_sync.py";
    exec(cmd, (err, _stdout, stderr) => {
      if (err) console.error("metrics_sync error:", stderr);
    });

    return NextResponse.json({ data: { started: true } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
