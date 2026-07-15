// app/page.tsx — reads from Supabase
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { getLanguageInfo, formatDate } from "@/lib/utils";

interface ReportSummary {
  id: string;
  repo_name: string;
  language: string;
  scanned_at: string;
  total_findings: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

function SeverityBar({ report }: { report: ReportSummary }) {
  const total = report.total_findings || 1;
  return (
    <div className="w-full h-1.5 rounded-full overflow-hidden flex mt-3">
      <div className="bg-red-500 transition-all" style={{ width: `${(report.critical / total) * 100}%` }} />
      <div className="bg-orange-500 transition-all" style={{ width: `${(report.high / total) * 100}%` }} />
      <div className="bg-yellow-500 transition-all" style={{ width: `${(report.medium / total) * 100}%` }} />
      <div className="bg-green-600 transition-all" style={{ width: `${(report.low / total) * 100}%` }} />
    </div>
  );
}

function ReportCard({ report }: { report: ReportSummary }) {
  const lang = getLanguageInfo(report.language);
  const hasIssues = report.critical + report.high > 0;

  return (
    <Link href={`/reports/${report.id}`}>
      <div className="bg-secondary/60 border border-secondary hover:border-accent hover:bg-secondary transition-all cursor-pointer group rounded-xl p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="font-semibold text-foreground group-hover:text-accent transition-colors text-lg leading-tight">
              {report.repo_name}
            </h3>
            <p className="text-foreground/60 text-xs mt-1">{formatDate(report.scanned_at)}</p>
          </div>
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${lang.color}`}>
            {lang.icon} {lang.label}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {report.critical > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-950 text-red-300 border border-red-800">
              🔴 {report.critical}
            </span>
          )}
          {report.high > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-orange-950 text-orange-300 border border-orange-800">
              🟠 {report.high}
            </span>
          )}
          {report.medium > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-yellow-950 text-yellow-300 border border-yellow-800">
              🟡 {report.medium}
            </span>
          )}
          {report.low > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 border border-green-300">
              🟢 {report.low}
            </span>
          )}
          {report.total_findings === 0 && (
            <span className="text-green-700 text-xs font-medium">✅ Clean scan</span>
          )}
        </div>

        {report.total_findings > 0 && <SeverityBar report={report} />}

        <div className="flex items-center justify-between mt-3 pt-3 border-t border-secondary">
          <span className="text-foreground/60 text-xs">
            {report.total_findings} finding{report.total_findings !== 1 ? "s" : ""}
          </span>
          <span className={`text-xs font-medium ${hasIssues ? "text-orange-400" : "text-green-700"}`}>
            {hasIssues ? "⚠️ Action needed" : "✅ Looks good"}
          </span>
        </div>
      </div>
    </Link>
  );
}

export default function HomePage() {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchReports() {
      const { data, error } = await supabase
        .from("reports")
        .select("id, repo_name, language, scanned_at, total_findings, critical, high, medium, low")
        .order("scanned_at", { ascending: false });

      if (!error && data) setReports(data);
      setLoading(false);
    }
    fetchReports();
  }, []);

  // Aggregate stats
  const totalFindings = reports.reduce((s, r) => s + r.total_findings, 0);
  const totalCritical = reports.reduce((s, r) => s + r.critical, 0);
  const totalHigh = reports.reduce((s, r) => s + r.high, 0);

  // Group by repo name
  const byRepo = new Map<string, ReportSummary[]>();
  for (const r of reports) {
    if (!byRepo.has(r.repo_name)) byRepo.set(r.repo_name, []);
    byRepo.get(r.repo_name)!.push(r);
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground">Code Review Reports</h1>
        <p className="text-foreground/60 mt-2">AI-powered analysis across all your projects</p>
      </div>

      {/* Stats */}
      {reports.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: "Total Scans", value: reports.length, icon: "📊", color: "text-accent" },
            { label: "Total Findings", value: totalFindings, icon: "🔍", color: "text-foreground" },
            { label: "Critical", value: totalCritical, icon: "🔴", color: "text-red-400" },
            { label: "High Priority", value: totalHigh, icon: "🟠", color: "text-orange-400" },
          ].map((s) => (
            <div key={s.label} className="bg-secondary/60 border border-secondary rounded-xl p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-foreground/60 text-sm">{s.label}</p>
                  <p className={`text-3xl font-bold mt-1 ${s.color}`}>{s.value}</p>
                </div>
                <span className="text-3xl">{s.icon}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Reports */}
      {loading ? (
        <div className="text-center py-24 text-foreground/60">
          <div className="text-4xl mb-4 animate-pulse">🔍</div>
          <p>Loading reports...</p>
        </div>
      ) : reports.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-secondary rounded-2xl">
          <div className="text-5xl mb-4">📭</div>
          <h2 className="text-xl font-semibold text-foreground/80 mb-2">No reports yet</h2>
          <p className="text-foreground/50 mb-6 max-w-md mx-auto">
            Run a scan to generate your first report.
          </p>
          <div className="bg-secondary rounded-xl p-4 inline-block text-left text-sm text-foreground/80 font-mono">
            <p className="text-foreground/50 mb-1"># Scan a project:</p>
            <p>python ts_agent.py C:/projects/next-store</p>
            <p className="mt-1">python java_agent.py C:/projects/petclinic</p>
          </div>
        </div>
      ) : (
        Array.from(byRepo.entries()).map(([repoName, repoReports]) => (
          <div key={repoName} className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <h2 className="text-lg font-semibold text-foreground">{repoName}</h2>
              <span className="text-xs text-foreground/50 bg-secondary px-2 py-0.5 rounded-full">
                {repoReports.length} scan{repoReports.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {repoReports.map((r) => <ReportCard key={r.id} report={r} />)}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
