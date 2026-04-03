// Types shared across the dashboard

export interface Finding {
  file: string;
  line: number;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  title: string;
  description: string;
  suggested_fix: string;
  language?: string;
}

export interface Report {
  id: string;           // filename without .json
  repo_path: string;
  repo_name: string;
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

export interface ReportSummary {
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
