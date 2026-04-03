import Link from "next/link";
import { getAllReports } from "@/lib/reports";
import { getLanguageInfo, formatDate } from "@/lib/reports";
import type { ReportSummary } from "@/lib/types";

function SeverityBadge({ count, type }: { count: number; type: string }) {
  const styles: Record<string, string> = {
    critical: "bg-red-950 text-red-300 border border-red-800",
    high: "bg-orange-950 text-orange-300 border border-orange-800",
    medium: "bg-yellow-950 text-yellow-300 border border-yellow-800",
    low: "bg-green-950 text-green-300 border border-green-800",
  };
  const icons: Record<string, string> = {
    critical: "🔴", high: "🟠", medium: "🟡", low: "🟢",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${styles[type]}`}>
      {icons[type]} {count}
    </span>
  );
}

function ScoreBar({ report }: { report: ReportSummary }) {
  const total = report.total_findings || 1;
  const criticalPct = (report.critical / total) * 100;
  const highPct = (report.high / total) * 100;
  const mediumPct = (report.medium / total) * 100;
  const lowPct = (report.low / total) * 100;

  return (
    <div className="w-full h-1.5 rounded-full overflow-hidden flex mt-3">
      <div className="bg-red-500" style={{ width: `${criticalPct}%` }} />
      <div className="bg-orange-500" style={{ width: `${highPct}%` }} />
      <div className="bg-yellow-500" style={{ width: `${mediumPct}%` }} />
      <div className="bg-green-500" style={{ width: `${lowPct}%` }} />
    </div>
  );
}

function ReportCard({ report }: { report: ReportSummary }) {
  const lang = getLanguageInfo(report.language);
  const hasIssues = report.critical + report.high > 0;

  return (
    <Link href={`/reports/${report.id}`}>
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 hover:border-indigo-500 hover:bg-slate-800 transition-all cursor-pointer group">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="font-semibold text-white group-hover:text-indigo-300 transition-colors text-lg leading-tight">
              {report.repo_name}
            </h3>
            <p className="text-slate-400 text-xs mt-1">
              {formatDate(report.scanned_at)}
            </p>
          </div>
          <span className={`text-xs px-2 py-1 rounded-full font-medium ${lang.color}`}>
            {lang.icon} {lang.label}
          </span>
        </div>

        {/* Severity badges */}
        <div className="flex items-center gap-2 flex-wrap">
          {report.critical > 0 && <SeverityBadge count={report.critical} type="critical" />}
          {report.high > 0 && <SeverityBadge count={report.high} type="high" />}
          {report.medium > 0 && <SeverityBadge count={report.medium} type="medium" />}
          {report.low > 0 && <SeverityBadge count={report.low} type="low" />}
          {report.total_findings === 0 && (
            <span className="text-green-400 text-xs font-medium">✅ Clean scan</span>
          )}
        </div>

        {/* Score bar */}
        {report.total_findings > 0 && <ScoreBar report={report} />}

        {/* Footer */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-700">
          <span className="text-slate-400 text-xs">
            {report.total_findings} finding{report.total_findings !== 1 ? "s" : ""}
          </span>
          <span className={`text-xs font-medium ${hasIssues ? "text-orange-400" : "text-green-400"}`}>
            {hasIssues ? "⚠️ Action needed" : "✅ Looks good"}
          </span>
        </div>
      </div>
    </Link>
  );
}

function StatsCard({ label, value, icon, color }: {
  label: string; value: number; icon: string; color: string;
}) {
  return (
    <div className={`bg-slate-800/50 border rounded-xl p-5 border-slate-700`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-slate-400 text-sm">{label}</p>
          <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
        </div>
        <span className="text-3xl">{icon}</span>
      </div>
    </div>
  );
}

export default function HomePage() {
  const reports = getAllReports();

  // Aggregate stats
  const totalReports = reports.length;
  const totalFindings = reports.reduce((sum, r) => sum + r.total_findings, 0);
  const totalCritical = reports.reduce((sum, r) => sum + r.critical, 0);
  const totalHigh = reports.reduce((sum, r) => sum + r.high, 0);

  // Group by repo name (latest scan per repo)
  const byRepo = new Map<string, ReportSummary[]>();
  for (const r of reports) {
    const baseName = r.repo_name.replace(/ \[.*\]$/, "").trim();
    if (!byRepo.has(baseName)) byRepo.set(baseName, []);
    byRepo.get(baseName)!.push(r);
  }

  return (
    <div>
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Code Review Reports</h1>
        <p className="text-slate-400 mt-2">
          AI-powered analysis across all your projects
        </p>
      </div>

      {/* Stats overview */}
      {totalReports > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatsCard label="Total Scans" value={totalReports} icon="📊" color="text-indigo-400" />
          <StatsCard label="Total Findings" value={totalFindings} icon="🔍" color="text-slate-200" />
          <StatsCard label="Critical Issues" value={totalCritical} icon="🔴" color="text-red-400" />
          <StatsCard label="High Priority" value={totalHigh} icon="🟠" color="text-orange-400" />
        </div>
      )}

      {/* Reports grid */}
      {reports.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-slate-700 rounded-2xl">
          <div className="text-5xl mb-4">📭</div>
          <h2 className="text-xl font-semibold text-slate-300 mb-2">No reports yet</h2>
          <p className="text-slate-500 mb-6 max-w-md mx-auto">
            Run a scan to generate your first report. Reports are stored in{" "}
            <code className="bg-slate-800 px-1.5 py-0.5 rounded text-indigo-300 text-sm">
              agent/reports/
            </code>
          </p>
          <div className="bg-slate-800 rounded-xl p-4 inline-block text-left text-sm text-slate-300 font-mono">
            <p className="text-slate-500 mb-1"># Scan a project:</p>
            <p>python ts_agent.py C:/projects/next-store</p>
            <p className="mt-1">python java_agent.py C:/projects/petclinic</p>
          </div>
        </div>
      ) : (
        <>
          {/* Group by repo */}
          {Array.from(byRepo.entries()).map(([repoName, repoReports]) => (
            <div key={repoName} className="mb-10">
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-lg font-semibold text-slate-200">{repoName}</h2>
                <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full">
                  {repoReports.length} scan{repoReports.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {repoReports.map((report) => (
                  <ReportCard key={report.id} report={report} />
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
