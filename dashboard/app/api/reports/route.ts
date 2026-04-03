import { NextResponse } from "next/server";
import { getAllReports, getReport } from "@/lib/reports";

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
