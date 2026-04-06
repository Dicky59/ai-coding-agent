"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Legend, BarChart, Bar, PieChart, Pie, Cell, CartesianGrid,
} from "recharts";
import { supabase } from "@/lib/supabase";
import { getLanguageInfo, formatDate } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Report {
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

interface TopFinding {
  title: string;
  category: string;
  count: number;
  fixed_count: number;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SEV_COLORS = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

const REPO_COLORS = [
  "#6366f1", "#06b6d4", "#f59e0b", "#10b981",
  "#f43f5e", "#8b5cf6", "#0ea5e9", "#84cc16",
];

const CAT_ICONS: Record<string, string> = {
  security: "🔒", bug: "🐛", performance: "⚡",
  pattern: "🏗️", nextjs: "▲", hooks: "🪝",
  typescript: "📘", jpa: "🗄️", quality: "🏗️", async: "⚡",
};

// ─── Custom Tooltip ───────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 text-sm shadow-xl">
      <p className="text-slate-300 font-medium mb-2">{label}</p>
      {payload.map((p: any, i: number) => (
        <div key={i} className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: p.color }} />
          <span className="text-slate-400">{p.name}:</span>
          <span className="text-slate-200 font-medium">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 mb-6">
      <h2 className="text-slate-200 font-semibold mb-5">{title}</h2>
      {children}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function TrendsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [topFindings, setTopFindings] = useState<TopFinding[]>([]);
  const [totalFixed, setTotalFixed] = useState(0);
  const [totalOpen, setTotalOpen] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      // Reports
      const { data: reportsData } = await supabase
        .from("reports")
        .select("*")
        .order("scanned_at", { ascending: true });

      if (reportsData) setReports(reportsData);

      // Findings with fixed status
      const { data: findingsData } = await supabase
        .from("findings")
        .select("title, category, fixed");

      if (findingsData) {
        const fixed = findingsData.filter((f) => f.fixed).length;
        const open = findingsData.filter((f) => !f.fixed).length;
        setTotalFixed(fixed);
        setTotalOpen(open);

        // Top findings
        const counts: Record<string, { count: number; category: string; fixed_count: number }> = {};
        for (const f of findingsData) {
          if (!counts[f.title]) counts[f.title] = { count: 0, category: f.category, fixed_count: 0 };
          counts[f.title].count++;
          if (f.fixed) counts[f.title].fixed_count++;
        }
        const sorted = Object.entries(counts)
          .sort((a, b) => b[1].count - a[1].count)
          .slice(0, 10)
          .map(([title, { count, category, fixed_count }]) => ({
            title, category, count, fixed_count,
          }));
        setTopFindings(sorted);
      }

      setLoading(false);
    }
    fetchData();
  }, []);

  // ── Findings over time ──
  const timelineData = useMemo(() => {
    if (!reports.length) return [];
    const repos = Array.from(new Set(reports.map((r) => r.repo_name)));
    const byDate = new Map<string, Record<string, number>>();
    for (const r of reports) {
      const day = r.scanned_at.substring(0, 10);
      if (!byDate.has(day)) byDate.set(day, {});
      byDate.get(day)![r.repo_name] = r.total_findings;
    }
    return Array.from(byDate.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([date, repoData]) => ({
        date: new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        ...repoData,
      }));
  }, [reports]);

  const uniqueRepos = useMemo(
    () => Array.from(new Set(reports.map((r) => r.repo_name))),
    [reports]
  );

  // ── Severity breakdown ──
  const severityData = useMemo(() => {
    if (!reports.length) return [];
    const byDate = new Map<string, { critical: number; high: number; medium: number; low: number }>();
    for (const r of reports) {
      const day = r.scanned_at.substring(0, 10);
      if (!byDate.has(day)) byDate.set(day, { critical: 0, high: 0, medium: 0, low: 0 });
      const entry = byDate.get(day)!;
      entry.critical += r.critical;
      entry.high += r.high;
      entry.medium += r.medium;
      entry.low += r.low;
    }
    return Array.from(byDate.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([date, sev]) => ({
        date: new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        ...sev,
      }));
  }, [reports]);

  // ── Language breakdown ──
  const languageData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of reports) {
      counts[r.language] = (counts[r.language] || 0) + r.total_findings;
    }
    return Object.entries(counts).map(([lang, count]) => ({
      name: getLanguageInfo(lang).label,
      value: count,
    }));
  }, [reports]);

  const langColors = ["#6366f1", "#f97316", "#06b6d4", "#22c55e", "#f59e0b"];

  // ── Fixed vs Open pie ──
  const fixedVsOpenData = [
    { name: "Open", value: totalOpen, color: "#f97316" },
    { name: "Fixed", value: totalFixed, color: "#22c55e" },
  ].filter((d) => d.value > 0);

  // ── Repo stats ──
  const repoStats = useMemo(() => {
    const byRepo = new Map<string, Report[]>();
    for (const r of reports) {
      if (!byRepo.has(r.repo_name)) byRepo.set(r.repo_name, []);
      byRepo.get(r.repo_name)!.push(r);
    }
    return Array.from(byRepo.entries()).map(([repo, scans]) => {
      const latest = scans[scans.length - 1];
      const first = scans[0];
      const trend = scans.length > 1 ? latest.total_findings - first.total_findings : 0;
      return {
        repo,
        latest: latest.total_findings,
        critical: latest.critical,
        high: latest.high,
        scans: scans.length,
        trend,
        language: latest.language,
      };
    }).sort((a, b) => b.latest - a.latest);
  }, [reports]);

  // ── Stats ──
  const totalScans = reports.length;
  const totalFindings = reports.reduce((s, r) => s + r.total_findings, 0);
  const avgFindings = totalScans ? Math.round(totalFindings / totalScans) : 0;
  const fixPct = (totalFixed + totalOpen) > 0
    ? Math.round((totalFixed / (totalFixed + totalOpen)) * 100)
    : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        <div className="text-center">
          <div className="text-3xl mb-3 animate-pulse">📈</div>
          <p>Loading trends...</p>
        </div>
      </div>
    );
  }

  if (!reports.length) {
    return (
      <div className="text-center py-24 border border-dashed border-slate-700 rounded-2xl">
        <div className="text-5xl mb-4">📭</div>
        <h2 className="text-xl font-semibold text-slate-300 mb-2">No data yet</h2>
        <p className="text-slate-500 mb-4">Run some scans first to see trends.</p>
        <Link href="/" className="text-indigo-400 hover:underline">← Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Trends</h1>
          <p className="text-slate-400 mt-1">Track code quality over time</p>
        </div>
        <Link href="/" className="text-indigo-400 hover:text-indigo-300 text-sm transition-colors">
          ← All Reports
        </Link>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Total Scans",    value: totalScans,    icon: "📊", color: "text-indigo-400" },
          { label: "Total Findings", value: totalFindings, icon: "🔍", color: "text-slate-200"  },
          { label: "Fixed",          value: totalFixed,    icon: "✅", color: "text-green-400"  },
          { label: "Fix Rate",       value: `${fixPct}%`,  icon: "📈", color: "text-blue-400"   },
        ].map((s) => (
          <div key={s.label} className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-slate-400 text-sm">{s.label}</p>
                <p className={`text-3xl font-bold mt-1 ${s.color}`}>{s.value}</p>
              </div>
              <span className="text-3xl">{s.icon}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Findings over time */}
      {timelineData.length > 1 && (
        <Section title="📈 Findings Over Time">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={timelineData} margin={{ left: 0, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
              <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend formatter={(v) => <span className="text-slate-300 text-xs">{v}</span>} />
              {uniqueRepos.map((repo, i) => (
                <Line
                  key={repo}
                  type="monotone"
                  dataKey={repo}
                  stroke={REPO_COLORS[i % REPO_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 4, fill: REPO_COLORS[i % REPO_COLORS.length] }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </Section>
      )}

      {/* Severity + Fixed vs Open */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">

        {/* Severity breakdown */}
        {severityData.length > 0 && (
          <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
            <h2 className="text-slate-200 font-semibold mb-4">🎯 Severity Breakdown</h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={severityData} margin={{ left: 0, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="critical" stackId="a" fill={SEV_COLORS.critical} />
                <Bar dataKey="high"     stackId="a" fill={SEV_COLORS.high}     />
                <Bar dataKey="medium"   stackId="a" fill={SEV_COLORS.medium}   />
                <Bar dataKey="low"      stackId="a" fill={SEV_COLORS.low} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Fixed vs Open */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
          <h2 className="text-slate-200 font-semibold mb-4">✅ Fixed vs Open</h2>
          {fixedVsOpenData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie
                    data={fixedVsOpenData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={70}
                    dataKey="value"
                    paddingAngle={3}
                    label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`
                    }
                    labelLine={{ stroke: "#475569" }}
                  >
                    {fixedVsOpenData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "#1e293b", border: "1px solid #334155",
                      borderRadius: 8, color: "#e2e8f0",
                    }}
                    itemStyle={{ color: "#e2e8f0" }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex justify-center gap-6 mt-2">
                <div className="text-center">
                  <p className="text-2xl font-bold text-orange-400">{totalOpen}</p>
                  <p className="text-xs text-slate-500">Open</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-green-400">{totalFixed}</p>
                  <p className="text-xs text-slate-500">Fixed</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-blue-400">{fixPct}%</p>
                  <p className="text-xs text-slate-500">Fix rate</p>
                </div>
              </div>
            </>
          ) : (
            <p className="text-slate-500 text-sm text-center py-8">No data</p>
          )}
        </div>
      </div>

      {/* Repo stats + Language pie */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">

        {/* Project summary */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
          <h2 className="text-slate-200 font-semibold mb-4">🏆 Projects</h2>
          <div className="space-y-3">
            {repoStats.map((r) => {
              const lang = getLanguageInfo(r.language);
              const trendIcon = r.trend < 0 ? "📉" : r.trend > 0 ? "📈" : "➡️";
              const trendColor = r.trend < 0 ? "text-green-400" : r.trend > 0 ? "text-red-400" : "text-slate-400";
              return (
                <div key={r.repo} className="flex items-center justify-between py-2 border-b border-slate-700/50 last:border-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-lg shrink-0">{lang.icon}</span>
                    <div className="min-w-0">
                      <p className="text-slate-200 text-sm font-medium truncate">{r.repo}</p>
                      <p className="text-slate-500 text-xs">{r.scans} scan{r.scans !== 1 ? "s" : ""}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right">
                      <p className="text-slate-200 text-sm font-medium">{r.latest}</p>
                      <p className="text-slate-500 text-xs">findings</p>
                    </div>
                    {r.scans > 1 && (
                      <span className={`text-xs ${trendColor}`}>
                        {trendIcon} {Math.abs(r.trend)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Language pie */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
          <h2 className="text-slate-200 font-semibold mb-4">🌐 Findings by Language</h2>
          {languageData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={languageData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  dataKey="value"
                  paddingAngle={2}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={{ stroke: "#475569" }}
                >
                  {languageData.map((_, i) => (
                    <Cell key={i} fill={langColors[i % langColors.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "#1e293b", border: "1px solid #334155",
                    borderRadius: 8, color: "#e2e8f0",
                  }}
                  itemStyle={{ color: "#e2e8f0" }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-slate-500 text-sm text-center py-8">No data</p>
          )}
        </div>
      </div>

      {/* Top issues with fix progress */}
      {topFindings.length > 0 && (
        <Section title="🔝 Most Common Issues">
          <div className="space-y-2">
            {topFindings.map((f, i) => {
              const fixPctItem = f.count > 0 ? Math.round((f.fixed_count / f.count) * 100) : 0;
              return (
                <div key={i} className="flex items-center gap-3 py-2 border-b border-slate-700/50 last:border-0">
                  <span className="text-slate-500 text-xs w-5 text-right shrink-0">{i + 1}</span>
                  <span className="text-base shrink-0">{CAT_ICONS[f.category] || "📌"}</span>
                  <span className="text-slate-300 text-sm flex-1 min-w-0 truncate">{f.title}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {/* Fix progress bar */}
                    <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-green-500 rounded-full transition-all"
                        style={{ width: `${fixPctItem}%` }}
                      />
                    </div>
                    <span className="text-slate-400 text-xs w-20 text-right">
                      {f.fixed_count}/{f.count} fixed
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      <p className="text-center text-slate-600 text-xs mt-4">
        {totalScans} scan{totalScans !== 1 ? "s" : ""} · {uniqueRepos.length} project{uniqueRepos.length !== 1 ? "s" : ""} · {fixPct}% fix rate
      </p>
    </div>
  );
}
