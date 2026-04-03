// lib/reports.ts
// Works in two modes:
// - Local dev: reads from filesystem (agent/reports/)
// - Vercel: reads from public/reports/ via manifest

import type { Report, ReportSummary } from "./types";

// ─── Server-side (local dev only) ────────────────────────────────────────────

function getReportsFromFS(): ReportSummary[] {
  // Only runs on server in local dev — not on Vercel
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require("fs");
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const path = require("path");

    const candidates = [
      path.join(process.cwd(), "..", "agent", "reports"),
      path.join(process.cwd(), "..", "reports"),
    ];

    let reportsDir = "";
    for (const dir of candidates) {
      if (fs.existsSync(dir)) {
        reportsDir = dir;
        break;
      }
    }

    if (!reportsDir) return [];

    const files = fs
      .readdirSync(reportsDir)
      .filter((f: string) => f.endsWith(".json"))
      .sort()
      .reverse();

    const summaries: ReportSummary[] = [];
    for (const file of files) {
      try {
        const content = fs.readFileSync(path.join(reportsDir, file), "utf-8");
        const data = JSON.parse(content);
        if (!data.findings || !data.repo_name) continue;
        summaries.push({
          id: file.replace(".json", ""),
          repo_name: data.repo_name || "Unknown",
          language: data.language || "unknown",
          scanned_at: data.scanned_at || "",
          total_findings: data.total_findings || 0,
          critical: data.critical || 0,
          high: data.high || 0,
          medium: data.medium || 0,
          low: data.low || 0,
        });
      } catch {
        // skip invalid
      }
    }
    return summaries;
  } catch {
    return [];
  }
}

function getReportFromFS(id: string): Report | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require("fs");
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const path = require("path");

    const candidates = [
      path.join(process.cwd(), "..", "agent", "reports"),
      path.join(process.cwd(), "..", "reports"),
    ];

    for (const dir of candidates) {
      const filePath = path.join(dir, `${id}.json`);
      if (fs.existsSync(filePath)) {
        const content = fs.readFileSync(filePath, "utf-8");
        return { ...JSON.parse(content), id };
      }
    }
    return null;
  } catch {
    return null;
  }
}

// ─── Public manifest (Vercel) ─────────────────────────────────────────────────

// Reports copied to public/reports/ by reporter.py
// Manifest lists all available report IDs
export async function getAllReportsFromPublic(): Promise<ReportSummary[]> {
  try {
    const res = await fetch("/reports/manifest.json", { cache: "no-store" });
    if (!res.ok) return [];
    const ids: string[] = await res.json();

    const summaries: ReportSummary[] = [];
    for (const id of ids) {
      try {
        const r = await fetch(`/reports/${id}.json`, { cache: "no-store" });
        if (!r.ok) continue;
        const data = await r.json();
        summaries.push({
          id,
          repo_name: data.repo_name || "Unknown",
          language: data.language || "unknown",
          scanned_at: data.scanned_at || "",
          total_findings: data.total_findings || 0,
          critical: data.critical || 0,
          high: data.high || 0,
          medium: data.medium || 0,
          low: data.low || 0,
        });
      } catch {
        // skip
      }
    }
    return summaries.reverse();
  } catch {
    return [];
  }
}

export async function getReportFromPublic(id: string): Promise<Report | null> {
  try {
    const res = await fetch(`/reports/${id}.json`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    return { ...data, id };
  } catch {
    return null;
  }
}

// ─── Exports ─────────────────────────────────────────────────────────────────

// These are used by the API route (server-side, local dev)
export function getAllReports(): ReportSummary[] {
  return getReportsFromFS();
}

export function getReport(id: string): Report | null {
  return getReportFromFS(id);
}

// ─── Utilities ────────────────────────────────────────────────────────────────

export function formatDate(isoString: string): string {
  if (!isoString) return "Unknown";
  try {
    return new Date(isoString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export function getLanguageInfo(language: string): {
  icon: string;
  label: string;
  color: string;
} {
  const map: Record<string, { icon: string; label: string; color: string }> = {
    kotlin:     { icon: "🤖", label: "Kotlin",          color: "bg-purple-900 text-purple-200" },
    java:       { icon: "☕", label: "Java",             color: "bg-orange-900 text-orange-200" },
    typescript: { icon: "📘", label: "TypeScript",       color: "bg-blue-900 text-blue-200"    },
    javascript: { icon: "💛", label: "JavaScript",       color: "bg-yellow-900 text-yellow-200"},
    multi:      { icon: "🌐", label: "Multi-language",   color: "bg-green-900 text-green-200"  },
  };
  return map[language] ?? {
    icon: "📄", label: language, color: "bg-gray-700 text-gray-200",
  };
}
