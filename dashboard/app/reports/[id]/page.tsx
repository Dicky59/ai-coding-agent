"use client";

import { useEffect, useState, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { supabase } from "@/lib/supabase";
import { getLanguageInfo, formatDate } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Finding {
  id: string;
  file: string;
  line: number;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  title: string;
  description: string;
  suggested_fix: string;
}

interface Report {
  id: string;
  repo_name: string;
  repo_path: string;
  language: string;
  scanned_at: string;
  total_findings: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  ai_summary: string;
  findings: Finding[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SEV_COLORS: Record<string, string> = {
  critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e",
};

const SEV_BG: Record<string, string> = {
  critical: "bg-red-950 text-red-300 border-red-800",
  high: "bg-orange-950 text-orange-300 border-orange-800",
  medium: "bg-yellow-950 text-yellow-300 border-yellow-800",
  low: "bg-green-950 text-green-300 border-green-800",
};

const SEV_ICONS: Record<string, string> = {
  critical: "🔴", high: "🟠", medium: "🟡", low: "🟢",
};

const CAT_ICONS: Record<string, string> = {
  security: "🔒", bug: "🐛", performance: "⚡",
  pattern: "🏗️", nextjs: "▲", hooks: "🪝",
  typescript: "📘", jpa: "🗄️",
};

// ─── Components ───────────────────────────────────────────────────────────────

function SeverityPie({ report }: { report: Report }) {
  const data = [
    { name: "Critical", value: report.critical, color: SEV_COLORS.critical },
    { name: "High",     value: report.high,     color: SEV_COLORS.high     },
    { name: "Medium",   value: report.medium,   color: SEV_COLORS.medium   },
    { name: "Low",      value: report.low,      color: SEV_COLORS.low      },
  ].filter((d) => d.value > 0);

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-medium text-slate-300 mb-4">By Severity</h3>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={50} outerRadius={75}
            dataKey="value" paddingAngle={2}>
            {data.map((e, i) => <Cell key={i} fill={e.color} />)}
          </Pie>
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }} />
          <Legend formatter={(v) => <span className="text-slate-300 text-xs">{v}</span>} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function CategoryBar({ findings }: { findings: Finding[] }) {
  const byCategory = findings.reduce((acc, f) => {
    acc[f.category] = (acc[f.category] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const data = Object.entries(byCategory)
    .sort((a, b) => b[1] - a[1])
    .map(([cat, count]) => ({ name: `${CAT_ICONS[cat] || "📌"} ${cat}`, count }));

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-medium text-slate-300 mb-4">By Category</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} layout="vertical" margin={{ left: 20 }}>
          <XAxis type="number" tick={{ fill: "#64748b", fontSize: 11 }} />
          <YAxis type="category" dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} width={110} />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }} />
          <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const [expanded, setExpanded] = useState(false);
  const fileName = finding.file.split(/[\\/]/).pop() || finding.file;

  return (
    <div className="border-b border-slate-700/50 last:border-0">
      <button onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3 hover:bg-slate-700/30 transition-colors flex items-start gap-3">
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${SEV_BG[finding.severity]} shrink-0 mt-0.5`}>
          {SEV_ICONS[finding.severity]} {finding.severity}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-slate-200 text-sm font-medium">{finding.title}</span>
            <span className="text-xs text-slate-500">{CAT_ICONS[finding.category] || "📌"} {finding.category}</span>
          </div>
          <div className="text-xs text-indigo-400 mt-0.5 font-mono">{fileName}:{finding.line}</div>
        </div>
        <span className="text-slate-500 text-xs shrink-0 mt-1">{expanded ? "▲ hide" : "▼ details"}</span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 ml-[88px]">
          <div className="bg-slate-900/50 rounded-lg p-3 space-y-2">
            <p className="text-slate-300 text-sm">{finding.description}</p>
            <div className="flex items-start gap-2">
              <span className="text-green-400 text-sm shrink-0">✅</span>
              <p className="text-green-300 text-sm">{finding.suggested_fix}</p>
            </div>
            <div className="text-xs text-slate-500 font-mono pt-1 border-t border-slate-700">
              📄 {finding.file}:{finding.line}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ReportPage() {
  const params = useParams();
  const id = params.id as string;

  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [severityFilter, setSeverityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    async function fetchReport() {
      // Fetch report metadata
      const { data: reportData, error: reportError } = await supabase
        .from("reports")
        .select("*")
        .eq("id", id)
        .single();

      if (reportError || !reportData) {
        setError("Report not found");
        setLoading(false);
        return;
      }

      // Fetch findings for this report
      const { data: findingsData, error: findingsError } = await supabase
        .from("findings")
        .select("*")
        .eq("report_id", id)
        .order("severity", { ascending: true });

      if (findingsError) {
        setError("Failed to load findings");
        setLoading(false);
        return;
      }

      setReport({ ...reportData, findings: findingsData || [] });
      setLoading(false);
    }
    fetchReport();
  }, [id]);

  const categories = useMemo(() => {
    if (!report) return [];
    return Array.from(new Set(report.findings.map((f) => f.category)));
  }, [report]);

  const filteredFindings = useMemo(() => {
    if (!report) return [];
    return report.findings.filter((f) => {
      if (severityFilter !== "all" && f.severity !== severityFilter) return false;
      if (categoryFilter !== "all" && f.category !== categoryFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return f.title.toLowerCase().includes(q) ||
          f.file.toLowerCase().includes(q) ||
          f.description.toLowerCase().includes(q);
      }
      return true;
    });
  }, [report, severityFilter, categoryFilter, searchQuery]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        <div className="text-center">
          <div className="text-3xl mb-3 animate-pulse">🔍</div>
          <p>Loading report...</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="text-center py-24">
        <div className="text-5xl mb-4">❌</div>
        <h2 className="text-xl font-semibold text-slate-300 mb-2">Report not found</h2>
        <p className="text-slate-500 mb-6">{error}</p>
        <Link href="/" className="text-indigo-400 hover:underline">← Back to dashboard</Link>
      </div>
    );
  }

  const lang = getLanguageInfo(report.language);

  return (
    <div>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-6">
        <Link href="/" className="hover:text-slate-300 transition-colors">Dashboard</Link>
        <span>→</span>
        <span className="text-slate-300">{report.repo_name}</span>
      </div>

      {/* Header */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6 mb-6">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold text-white">{report.repo_name}</h1>
              <span className={`text-xs px-2 py-1 rounded-full font-medium ${lang.color}`}>
                {lang.icon} {lang.label}
              </span>
            </div>
            <p className="text-slate-400 text-sm">{formatDate(report.scanned_at)}</p>
            {report.repo_path && (
              <p className="text-slate-500 text-xs mt-1 font-mono">{report.repo_path}</p>
            )}
          </div>
          <div className="flex gap-4">
            {(["critical", "high", "medium", "low"] as const).map((sev) => (
              <div key={sev} className="text-center">
                <div className="text-2xl font-bold" style={{ color: SEV_COLORS[sev] }}>
                  {report[sev]}
                </div>
                <div className="text-xs text-slate-500 capitalize">{sev}</div>
              </div>
            ))}
          </div>
        </div>

        {report.ai_summary && (
          <div className="mt-4 pt-4 border-t border-slate-700">
            <h3 className="text-sm font-medium text-indigo-300 mb-2">🧠 AI Analysis</h3>
            <p className="text-slate-300 text-sm leading-relaxed whitespace-pre-line">
              {report.ai_summary.substring(0, 600)}
              {report.ai_summary.length > 600 ? "..." : ""}
            </p>
          </div>
        )}
      </div>

      {/* Charts */}
      {report.total_findings > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <SeverityPie report={report} />
          <CategoryBar findings={report.findings} />
        </div>
      )}

      {/* Findings table */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700 flex flex-wrap items-center gap-3">
          <h2 className="text-slate-200 font-semibold">
            Findings
            <span className="ml-2 text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">
              {filteredFindings.length} / {report.total_findings}
            </span>
          </h2>
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-slate-700 border border-slate-600 text-slate-200 text-xs rounded-lg px-3 py-1.5 outline-none focus:border-indigo-500">
            <option value="all">All severities</option>
            <option value="critical">🔴 Critical</option>
            <option value="high">🟠 High</option>
            <option value="medium">🟡 Medium</option>
            <option value="low">🟢 Low</option>
          </select>
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}
            className="bg-slate-700 border border-slate-600 text-slate-200 text-xs rounded-lg px-3 py-1.5 outline-none focus:border-indigo-500">
            <option value="all">All categories</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>{CAT_ICONS[cat] || "📌"} {cat}</option>
            ))}
          </select>
          <input type="text" placeholder="🔍 Search findings..."
            value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-slate-700 border border-slate-600 text-slate-200 text-xs rounded-lg px-3 py-1.5 outline-none focus:border-indigo-500 ml-auto w-48" />
        </div>

        {filteredFindings.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            {report.total_findings === 0 ? "✅ No issues found — clean scan!" : "No findings match your filters"}
          </div>
        ) : (
          <div>{filteredFindings.map((f) => <FindingRow key={f.id} finding={f} />)}</div>
        )}
      </div>

      <div className="mt-6">
        <Link href="/" className="text-indigo-400 hover:text-indigo-300 transition-colors text-sm">
          ← Back to all reports
        </Link>
      </div>
    </div>
  );
}
