import { NextResponse } from "next/server";
import { getAllReports, getReport } from "@/lib/reports";

// This route only runs in local dev (reads from filesystem)
// On Vercel, the client fetches from /reports/*.json directly
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const id = searchParams.get("id");

  if (id) {
    const report = getReport(id);
    if (!report) {
      return NextResponse.json({ error: "Report not found" }, { status: 404 });
    }
    return NextResponse.json(report);
  }

  const reports = getAllReports();
  return NextResponse.json(reports);
}
