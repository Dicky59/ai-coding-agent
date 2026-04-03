import fs from "fs";
import path from "path";
import type { Report, ReportSummary } from "./types";

// Reports folder: coding-agent/agent/reports/
// Dashboard is at: coding-agent/dashboard/
// So we go up two levels to find reports/
function getReportsDir(): string {
  // In production (Vercel), reports are served differently
  // In development, read from local filesystem
  const localPath = path.join(process.cwd(), "..", "agent", "reports");
  if (fs.existsSync(localPath)) {
    return localPath;
  }
  // Fallback: check for reports/ next to dashboard/
  const siblingPath = path.join(process.cwd(), "..", "reports");
  if (fs.existsSync(siblingPath)) {
    return siblingPath;
  }
  // Last resort: public/reports inside dashboard
  return path.join(process.cwd(), "public", "reports");
}

export function getAllReports(): ReportSummary[] {
  const reportsDir = getReportsDir();

  if (!fs.existsSync(reportsDir)) {
    return [];
  }

  const files = fs
    .readdirSync(reportsDir)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .reverse(); // newest first

  const summaries: ReportSummary[] = [];

  for (const file of files) {
    try {
      const content = fs.readFileSync(path.join(reportsDir, file), "utf-8");
      const data = JSON.parse(content);

      // Skip if it doesn't look like a report
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
      // Skip invalid JSON files
    }
  }

  return summaries;
}

export function getReport(id: string): Report | null {
  const reportsDir = getReportsDir();
  const filePath = path.join(reportsDir, `${id}.json`);

  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(content);
    return { ...data, id };
  } catch {
    return null;
  }
}

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
    kotlin: { icon: "🤖", label: "Kotlin", color: "bg-purple-900 text-purple-200" },
    java: { icon: "☕", label: "Java", color: "bg-orange-900 text-orange-200" },
    typescript: { icon: "📘", label: "TypeScript", color: "bg-blue-900 text-blue-200" },
    javascript: { icon: "💛", label: "JavaScript", color: "bg-yellow-900 text-yellow-200" },
    multi: { icon: "🌐", label: "Multi-language", color: "bg-green-900 text-green-200" },
  };
  return map[language] ?? { icon: "📄", label: language, color: "bg-gray-700 text-gray-200" };
}
