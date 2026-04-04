"""
Reporter — Shared reporting module for all AI Coding Agent scanners
Generates:
1. Beautiful self-contained HTML report
2. JSON report (local backup)
3. Saves to Supabase database
4. Auto-syncs to dashboard/public/reports/

Usage:
    from reporter import generate_report, ReportConfig

    config = ReportConfig(
        repo_path="C:/Users/dicky/projects/MyApp",
        repo_name="MyApp",
        language="kotlin",
        output_dir="reports",
    )
    await generate_report(findings, config, ai_summary)
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


# ─── Config ───────────────────────────────────────────────────────────────────

class ReportConfig(BaseModel):
    repo_path: str
    repo_name: str
    language: str = "kotlin"
    output_dir: str = "reports"
    github_owner: str = ""
    github_repo: str = ""
    create_github_issues: bool = False
    send_slack: bool = False
    open_html: bool = False


class Finding(BaseModel):
    file: str
    line: int
    severity: str
    category: str
    title: str
    description: str
    suggested_fix: str


# ─── Supabase ─────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def save_to_supabase(
    findings: list[Finding],
    config: ReportConfig,
    ai_summary: str,
) -> str | None:
    """Save report + findings to Supabase. Returns report ID."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("  ⚠️  Supabase not configured — skipping DB save")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # ── Insert report ──
            report_data = {
                "repo_name": config.repo_name,
                "repo_path": config.repo_path,
                "language": config.language,
                "scanned_at": datetime.now().isoformat(),
                "total_findings": len(findings),
                "critical": sum(1 for f in findings if f.severity == "critical"),
                "high": sum(1 for f in findings if f.severity == "high"),
                "medium": sum(1 for f in findings if f.severity == "medium"),
                "low": sum(1 for f in findings if f.severity == "low"),
                "ai_summary": ai_summary,
            }

            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/reports",
                headers=supabase_headers(),
                json=report_data,
            )

            if resp.status_code not in (200, 201):
                print(f"  ⚠️  Supabase report insert failed: {resp.status_code} — {resp.text[:200]}")
                return None

            report_id = resp.json()[0]["id"]
            print(f"  ✅ Report saved to Supabase: {report_id[:8]}...")

            # ── Insert findings in batches of 100 ──
            if findings:
                batch_size = 100
                total_inserted = 0

                for i in range(0, len(findings), batch_size):
                    batch = findings[i:i + batch_size]
                    findings_data = [
                        {
                            "report_id": report_id,
                            "file": f.file,
                            "line": f.line,
                            "severity": f.severity,
                            "category": f.category,
                            "title": f.title,
                            "description": f.description,
                            "suggested_fix": f.suggested_fix,
                            "language": config.language,
                        }
                        for f in batch
                    ]

                    resp = await client.post(
                        f"{SUPABASE_URL}/rest/v1/findings",
                        headers=supabase_headers(),
                        json=findings_data,
                    )

                    if resp.status_code in (200, 201):
                        total_inserted += len(batch)
                    else:
                        print(f"  ⚠️  Findings batch failed: {resp.status_code} — {resp.text[:100]}")

                print(f"  ✅ {total_inserted} findings saved to Supabase")

            return report_id

    except Exception as e:
        print(f"  ⚠️  Supabase error: {e}")
        return None


# ─── HTML Report ──────────────────────────────────────────────────────────────

def generate_html_report(
    findings: list[Finding],
    config: ReportConfig,
    ai_summary: str = "",
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    critical = sum(1 for f in findings if f.severity == "critical")
    high = sum(1 for f in findings if f.severity == "high")
    medium = sum(1 for f in findings if f.severity == "medium")
    low = sum(1 for f in findings if f.severity == "low")

    rows = ""
    for f in sorted(findings, key=lambda x: {"critical":0,"high":1,"medium":2,"low":3}.get(x.severity,4)):
        cat_icon = {"security":"🔒","bug":"🐛","performance":"⚡","pattern":"🏗️","jpa":"🗄️"}.get(f.category,"📌")
        file_name = Path(f.file).name
        rows += f"""
        <tr class="finding-row" data-severity="{f.severity}" data-category="{f.category}">
            <td><span class="badge {f.severity}">{f.severity.upper()}</span></td>
            <td>{cat_icon} {f.category}</td>
            <td class="title-cell">
                <div class="finding-title">{f.title}</div>
                <div class="finding-detail" style="display:none">
                    <p class="desc">{f.description}</p>
                    <p class="fix">✅ <strong>Fix:</strong> {f.suggested_fix}</p>
                </div>
            </td>
            <td class="file-cell"><code>{file_name}:{f.line}</code></td>
            <td><button class="expand-btn" onclick="toggleDetail(this)">▼ Details</button></td>
        </tr>"""

    ai_section = ""
    if ai_summary:
        ai_section = f"""
        <div class="ai-summary">
            <h2>🧠 AI Analysis</h2>
            <div class="ai-content">{ai_summary.replace(chr(10), '<br>')}</div>
        </div>"""

    lang_icon = {"kotlin":"🤖","java":"☕","typescript":"📘","javascript":"💛","multi":"🌐"}.get(config.language,"📄")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Code Review Report — {config.repo_name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }}
  .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-bottom: 1px solid #334155; padding: 32px 40px; }}
  .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; }}
  .repo-name {{ font-size: 28px; font-weight: 700; color: #f1f5f9; }}
  .repo-meta {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
  .scan-time {{ font-size: 12px; color: #475569; text-align: right; }}
  .lang-badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; background: #1e40af; color: #bfdbfe; font-size: 12px; font-weight: 600; margin-top: 8px; }}
  .summary-cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 24px 40px; }}
  .card {{ background: #1e293b; border-radius: 12px; padding: 20px 24px; border: 1px solid #334155; text-align: center; }}
  .card-count {{ font-size: 36px; font-weight: 700; }}
  .card-label {{ font-size: 12px; color: #94a3b8; margin-top: 4px; text-transform: uppercase; }}
  .card.critical .card-count {{ color: #ef4444; }}
  .card.high .card-count {{ color: #f97316; }}
  .card.medium .card-count {{ color: #eab308; }}
  .card.low .card-count {{ color: #22c55e; }}
  .main {{ padding: 24px 40px; }}
  .ai-summary {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px; margin-bottom: 24px; border-left: 4px solid #6366f1; }}
  .ai-summary h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #a5b4fc; }}
  .ai-content {{ font-size: 14px; line-height: 1.7; color: #cbd5e1; }}
  .controls {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }}
  .filter-btn {{ padding: 7px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #94a3b8; font-size: 13px; cursor: pointer; transition: all 0.15s; }}
  .filter-btn:hover, .filter-btn.active {{ background: #6366f1; color: #fff; border-color: #6366f1; }}
  .search-box {{ padding: 7px 14px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; font-size: 13px; outline: none; min-width: 220px; margin-left: auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ padding: 12px 16px; text-align: left; font-size: 11px; text-transform: uppercase; color: #64748b; background: #1e293b; border-bottom: 1px solid #334155; }}
  .finding-row td {{ padding: 14px 16px; border-bottom: 1px solid #1e293b; vertical-align: top; font-size: 14px; }}
  .finding-row:hover td {{ background: #1e293b; }}
  .finding-row.hidden {{ display: none; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; }}
  .badge.critical {{ background: #450a0a; color: #fca5a5; }}
  .badge.high {{ background: #431407; color: #fdba74; }}
  .badge.medium {{ background: #422006; color: #fde68a; }}
  .badge.low {{ background: #052e16; color: #86efac; }}
  .finding-title {{ font-weight: 500; color: #e2e8f0; }}
  .finding-detail {{ margin-top: 10px; padding: 12px; background: #0f172a; border-radius: 8px; }}
  .desc {{ color: #94a3b8; font-size: 13px; line-height: 1.6; margin-bottom: 8px; }}
  .fix {{ color: #86efac; font-size: 13px; }}
  .file-cell code {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7dd3fc; background: #0f172a; padding: 2px 6px; border-radius: 4px; }}
  .expand-btn {{ padding: 4px 10px; border-radius: 6px; border: 1px solid #334155; background: transparent; color: #64748b; font-size: 12px; cursor: pointer; }}
  .expand-btn.open {{ color: #6366f1; border-color: #6366f1; }}
  .table-container {{ background: #1a2234; border: 1px solid #334155; border-radius: 12px; overflow: hidden; }}
  .footer {{ text-align: center; padding: 24px; color: #475569; font-size: 12px; border-top: 1px solid #1e293b; margin-top: 40px; }}
  .export-btn {{ padding: 7px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #94a3b8; font-size: 13px; cursor: pointer; }}
  .no-findings {{ text-align: center; padding: 60px; color: #475569; font-size: 16px; }}
</style>
</head>
<body>
<div class="header">
  <div class="header-top">
    <div>
      <div class="repo-name">{lang_icon} {config.repo_name}</div>
      <div class="repo-meta">{config.repo_path}</div>
      <div class="lang-badge">{config.language.upper()}</div>
    </div>
    <div class="scan-time">🕐 Scanned: {now}<br>🤖 AI Coding Agent</div>
  </div>
</div>
<div class="summary-cards">
  <div class="card critical"><div class="card-count">{critical}</div><div class="card-label">🔴 Critical</div></div>
  <div class="card high"><div class="card-count">{high}</div><div class="card-label">🟠 High</div></div>
  <div class="card medium"><div class="card-count">{medium}</div><div class="card-label">🟡 Medium</div></div>
  <div class="card low"><div class="card-count">{low}</div><div class="card-label">🟢 Low</div></div>
</div>
<div class="main">
  {ai_section}
  <div class="controls">
    <button class="filter-btn active" onclick="filterSeverity('all', this)">All ({len(findings)})</button>
    <button class="filter-btn" onclick="filterSeverity('critical', this)">Critical ({critical})</button>
    <button class="filter-btn" onclick="filterSeverity('high', this)">High ({high})</button>
    <button class="filter-btn" onclick="filterSeverity('medium', this)">Medium ({medium})</button>
    <button class="filter-btn" onclick="filterSeverity('low', this)">Low ({low})</button>
    <button class="export-btn" onclick="exportCSV()">📥 Export CSV</button>
    <input class="search-box" type="text" placeholder="🔍 Search findings..." oninput="searchFindings(this.value)">
  </div>
  <div class="table-container">
    {"<table><thead><tr><th>Severity</th><th>Category</th><th>Finding</th><th>File</th><th></th></tr></thead><tbody>" + rows + "</tbody></table>" if findings else '<div class="no-findings">✅ No issues found!</div>'}
  </div>
</div>
<div class="footer">Generated by <strong>AI Coding Agent</strong> · {now} · {len(findings)} findings</div>
<script>
function toggleDetail(btn) {{
  const row = btn.closest('tr');
  const detail = row.querySelector('.finding-detail');
  const isOpen = detail.style.display !== 'none';
  detail.style.display = isOpen ? 'none' : 'block';
  btn.textContent = isOpen ? '▼ Details' : '▲ Hide';
  btn.classList.toggle('open', !isOpen);
}}
function filterSeverity(severity, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.finding-row').forEach(row => {{
    if (severity === 'all' || row.dataset.severity === severity) row.classList.remove('hidden');
    else row.classList.add('hidden');
  }});
}}
function searchFindings(query) {{
  const q = query.toLowerCase();
  document.querySelectorAll('.finding-row').forEach(row => {{
    row.classList.toggle('hidden', q.length > 0 && !row.textContent.toLowerCase().includes(q));
  }});
}}
function exportCSV() {{
  const rows = [['Severity','Category','Title','File','Line','Description','Fix']];
  document.querySelectorAll('.finding-row').forEach(row => {{
    const cells = row.querySelectorAll('td');
    const title = row.querySelector('.finding-title').textContent.trim();
    const file = cells[3].textContent.trim();
    const desc = row.querySelector('.desc') ? row.querySelector('.desc').textContent.trim() : '';
    const fix = row.querySelector('.fix') ? row.querySelector('.fix').textContent.trim() : '';
    rows.push([cells[0].textContent.trim(), cells[1].textContent.trim(), title, file, '', desc, fix]);
  }});
  const csv = rows.map(r => r.map(c => '"' + c.replace(/"/g,'""') + '"').join(',')).join('\\n');
  const blob = new Blob([csv], {{type: 'text/csv'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '{config.repo_name}_findings.csv';
  a.click();
}}
</script>
</body>
</html>"""
    return html


# ─── Main generate_report ─────────────────────────────────────────────────────

async def generate_report(
    findings: list[dict],
    config: ReportConfig,
    ai_summary: str = "",
) -> dict[str, Any]:
    """
    Main entry point — generates HTML, saves JSON, saves to Supabase,
    and auto-syncs to dashboard/public/reports/.
    """
    print(f"\n📊 Generating reports for {config.repo_name}...")

    # Normalize findings — handle different field names from different agents
    normalized = []
    for f in findings:
        normalized.append({
            "file": f.get("file", "unknown"),
            "line": f.get("line", 0),
            "severity": f.get("severity", "low"),
            "category": f.get("category", f.get("area", "general")),
            "title": f.get("title", "Issue"),
            "description": f.get("description", ""),
            "suggested_fix": f.get("suggested_fix", f.get("remediation", "")),
        })

    typed_findings = [Finding(**f) for f in normalized]

    # Create output directory
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Sanitize repo name for filenames — no spaces or brackets
    safe_name = re.sub(r'[^\w\-]', '_', config.repo_name).strip('_')

    # ── 1. HTML Report ──
    print("  🎨 Generating HTML report...")
    html = generate_html_report(typed_findings, config, ai_summary)
    html_path = out_dir / f"{safe_name}_{config.language}_{timestamp}.html"
    html_path.write_text(html, encoding="utf-8")
    results["html_report"] = str(html_path)
    print(f"  ✅ HTML report: {html_path}")

    # ── 2. JSON Report (local backup) ──
    json_path = out_dir / f"{safe_name}_{config.language}_{timestamp}.json"
    json_data = {
        "repo_path": config.repo_path,
        "repo_name": config.repo_name,
        "language": config.language,
        "scanned_at": datetime.now().isoformat(),
        "total_findings": len(typed_findings),
        "critical": sum(1 for f in typed_findings if f.severity == "critical"),
        "high": sum(1 for f in typed_findings if f.severity == "high"),
        "medium": sum(1 for f in typed_findings if f.severity == "medium"),
        "low": sum(1 for f in typed_findings if f.severity == "low"),
        "ai_summary": ai_summary,
        "findings": [f.model_dump() for f in typed_findings],
    }
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    results["json_report"] = str(json_path)
    print(f"  ✅ JSON report: {json_path}")

    # ── 3. Save to Supabase ──
    report_id = await save_to_supabase(typed_findings, config, ai_summary)
    if report_id:
        results["supabase_report_id"] = report_id

    # ── 4. Auto-sync to dashboard/public/reports/ ──
    dashboard_reports = Path(__file__).parent.parent / "dashboard" / "public" / "reports"
    if dashboard_reports.exists():
        dst = dashboard_reports / json_path.name
        shutil.copy2(json_path, dst)
        # Rebuild manifest
        ids = [
            f.stem for f in sorted(dashboard_reports.glob("*.json"))
            if f.name != "manifest.json"
        ]
        (dashboard_reports / "manifest.json").write_text(
            json.dumps(ids[::-1], indent=2), encoding="utf-8"
        )
        print(f"  ✅ Dashboard synced")

    print(f"\n  📦 Reports saved to: {out_dir}/")
    return results
