import { NextResponse } from "next/server";
import { listCampaigns } from "@/lib/meta-api";

export async function GET() {
  try {
    const campaigns = await listCampaigns();
    return NextResponse.json({ data: campaigns });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
