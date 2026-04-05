"""
Python Bug Scanner
Scans Python repositories using specialized MCP tools.

Usage:
    python py_agent.py <repo_path>
    python py_agent.py C:/Users/dicky/projects/coding-agent/agent
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel


# ─── Data models ─────────────────────────────────────────────────────────────

class PyFinding(BaseModel):
    file: str
    line: int
    severity: str
    category: str
    title: str
    description: str
    suggested_fix: str


class PyReport(BaseModel):
    repo_path: str
    total_files_scanned: int
    total_findings: int
    critical: int
    high: int
    medium: int
    low: int
    findings: list[PyFinding]
    ai_summary: str = ""


# ─── MCP client ──────────────────────────────────────────────────────────────

def create_mcp_client() -> MultiServerMCPClient:
    server_path = Path(__file__).parent.parent / "mcp-server" / "server_python.py"
    return MultiServerMCPClient(
        {
            "python-analyzer": {
                "command": "python",
                "args": [str(server_path)],
                "transport": "stdio",
            }
        }
    )


async def call_tool(tools: list, name: str, args: dict) -> dict:
    tool = next((t for t in tools if t.name == name), None)
    if not tool:
        return {}
    try:
        result = await tool.ainvoke(args)
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and "text" in first:
                return json.loads(first["text"])
            elif hasattr(first, "text"):
                return json.loads(first.text)
        if isinstance(result, str):
            return json.loads(result)
        if isinstance(result, dict):
            return result
        return {}
    except Exception:
        return {}


# ─── Scanner ──────────────────────────────────────────────────────────────────

async def scan_repository(repo_path: str) -> tuple[list[PyFinding], int]:
    mcp_client = create_mcp_client()
    tools = await mcp_client.get_tools()
    print(f"✅ Tools loaded: {[t.name for t in tools]}")

    print("\n📂 Listing Python files...")
    files_result = await call_tool(tools, "list_python_files", {
        "repo_path": repo_path,
        "include_tests": False,
    })

    py_files = files_result.get("files", [])
    print(f"   Found {len(py_files)} Python files")

    if not py_files:
        print("   No Python files found!")
        return [], 0

    all_findings: list[PyFinding] = []
    analysis_tools = [
        "analyze_python_bugs",
        "analyze_python_security",
        "analyze_python_quality",
        "analyze_python_async",
    ]

    for i, file_info in enumerate(py_files):
        file_path = str(Path(repo_path) / file_info["path"])
        file_name = file_info["name"]
        file_type = file_info.get("file_type", "")
        has_async = file_info.get("has_async", False)

        async_tag = " [async]" if has_async else ""
        print(f"\n  [{i+1}/{len(py_files)}] 🐍 {file_name} ({file_type}{async_tag})")

        for tool_name in analysis_tools:
            result = await call_tool(tools, tool_name, {
                "file_path": file_path,
                "repo_path": repo_path,
            })
            findings = result.get("findings", [])
            if findings:
                print(f"    ⚡ {tool_name}: {len(findings)}")
            for f in findings:
                all_findings.append(PyFinding(
                    file=file_info["path"],
                    line=f.get("line", 0),
                    severity=f.get("severity", "low"),
                    category=f.get("category", "quality"),
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    suggested_fix=f.get("suggested_fix", ""),
                ))

    return all_findings, len(py_files)


# ─── AI Summary ───────────────────────────────────────────────────────────────

async def generate_ai_summary(findings: list[PyFinding], repo_path: str) -> str:
    if not findings:
        return "No issues found in the repository."
    try:
        llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            max_tokens=1024,
        )
        by_severity = {"critical": [], "high": [], "medium": [], "low": []}
        for f in findings:
            by_severity.get(f.severity, []).append(f)

        summary_text = f"Python repo: {repo_path}\nTotal: {len(findings)} findings\n\n"
        for sev, items in by_severity.items():
            if items:
                summary_text += f"{sev.upper()} ({len(items)}):\n"
                for f in items[:5]:
                    summary_text += (
                        f"  - [{f.category}] {f.title} "
                        f"in {Path(f.file).name}:{f.line}\n"
                    )
                if len(items) > 5:
                    summary_text += f"  ... and {len(items) - 5} more\n"
                summary_text += "\n"

        response = llm.invoke([
            SystemMessage(content=(
                "You are an expert Python developer. "
                "Given these code scan results for a Python AI agent codebase, "
                "provide a concise executive summary highlighting the most important "
                "issues and recommended priorities. Be specific about Python best "
                "practices, async patterns, and security concerns. Max 200 words."
            )),
            HumanMessage(content=summary_text),
        ])
        return response.content
    except Exception as e:
        return f"AI summary unavailable: {e}"


# ─── Report ───────────────────────────────────────────────────────────────────

def build_report(repo_path, findings, files_scanned, ai_summary) -> PyReport:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: severity_order.get(f.severity, 4))
    return PyReport(
        repo_path=repo_path,
        total_files_scanned=files_scanned,
        total_findings=len(findings),
        critical=sum(1 for f in findings if f.severity == "critical"),
        high=sum(1 for f in findings if f.severity == "high"),
        medium=sum(1 for f in findings if f.severity == "medium"),
        low=sum(1 for f in findings if f.severity == "low"),
        findings=findings,
        ai_summary=ai_summary,
    )


def print_report(report: PyReport) -> None:
    print("\n" + "═" * 60)
    print("  🐍 PYTHON BUG REPORT")
    print("═" * 60)
    print(f"  Repo:    {report.repo_path}")
    print(f"  Scanned: {report.total_files_scanned} Python files")
    print(f"  Total:   {report.total_findings} findings")
    print()
    print(f"  🔴 Critical: {report.critical}")
    print(f"  🟠 High:     {report.high}")
    print(f"  🟡 Medium:   {report.medium}")
    print(f"  🟢 Low:      {report.low}")
    print("═" * 60)

    if report.ai_summary:
        print(f"\n  📋 AI SUMMARY\n  {'─' * 50}")
        for line in report.ai_summary.split("\n"):
            print(f"  {line}")

    if not report.findings:
        print("\n  ✅ No issues found!")
        return

    categories = {
        "security": [], "bug": [], "quality": [], "async": [],
    }
    for f in report.findings:
        categories.get(f.category, []).append(f)

    category_labels = {
        "security": "🔒 SECURITY",
        "bug":      "🐛 BUGS",
        "quality":  "🏗️  CODE QUALITY",
        "async":    "⚡ ASYNC",
    }

    for cat, label in category_labels.items():
        items = categories[cat]
        if not items:
            continue
        print(f"\n  {label} ({len(items)} findings)")
        print("  " + "─" * 50)
        for f in items:
            sev_icon = {
                "critical": "🔴", "high": "🟠",
                "medium": "🟡", "low": "🟢"
            }.get(f.severity, "⚪")
            print(f"\n  {sev_icon} [{f.severity.upper()}] {f.title}")
            print(f"     📄 {Path(f.file).name}:{f.line}")
            print(f"     💬 {f.description}")
            print(f"     ✅ Fix: {f.suggested_fix}")

    print("\n" + "═" * 60)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def scan_repo(repo_path: str) -> PyReport:
    print(f"\n🐍 Python Scanner starting...")
    print(f"📁 Repo: {repo_path}")

    findings, files_scanned = await scan_repository(repo_path)
    ai_summary = await generate_ai_summary(findings, repo_path)
    report = build_report(repo_path, findings, files_scanned, ai_summary)
    print_report(report)

    from reporter import generate_report, ReportConfig
    config = ReportConfig(
        repo_path=repo_path,
        repo_name=Path(repo_path).name,
        language="python",
        output_dir="reports",
        create_github_issues=False,
        send_slack=False,
    )
    await generate_report(
        [f.model_dump() for f in report.findings],
        config,
        report.ai_summary,
    )

    return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python py_agent.py <repo_path>")
        print("Example: python py_agent.py C:/Users/dicky/projects/coding-agent/agent")
        sys.exit(1)

    repo = sys.argv[1]
    asyncio.run(scan_repo(repo))
