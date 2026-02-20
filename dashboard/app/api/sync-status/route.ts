import { NextResponse } from "next/server";
import { getSupabase } from "@/lib/supabase";
import { spawn } from "child_process";
import path from "path";

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
    // Run metrics_sync.py as a detached child process
    const projectRoot = path.resolve(process.cwd(), "..");
    const python = path.join(projectRoot, "venv", "bin", "python");
    const script = path.join(projectRoot, "metrics_sync.py");

    const child = spawn(python, [script], {
      cwd: projectRoot,
      detached: true,
      stdio: "ignore",
    });
    child.unref();

    return NextResponse.json({ data: { started: true, pid: child.pid } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
