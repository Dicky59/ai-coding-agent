"""
Multi-Agent Orchestrator — Phase 5 (v2)
Coordinates specialized agents in a pipeline:

1. RepoAnalyzer    → understands structure and architecture
2. BugDetector     → finds code bugs and anti-patterns
3. SecurityAuditor → deep security analysis
4. ReportWriter    → synthesizes everything into executive report

Usage:
    python multi_agent.py <repo_path>
    python multi_agent.py C:/Users/dicky/projects/FoodApp
    python multi_agent.py C:/Users/dicky/projects/FoodApp --output report.md
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel


# ─── Shared state passed between agents ──────────────────────────────────────

@dataclass
class PipelineState:
    repo_path: str
    repo_summary: dict = field(default_factory=dict)
    kotlin_files: list[dict] = field(default_factory=list)
    architecture: str = ""
    frameworks: list[str] = field(default_factory=list)
    bug_findings: list[dict] = field(default_factory=list)
    security_findings: list[dict] = field(default_factory=list)
    total_files_scanned: int = 0
    final_report: str = ""
    agent_logs: list[str] = field(default_factory=list)


# ─── MCP client ──────────────────────────────────────────────────────────────

def create_mcp_client() -> MultiServerMCPClient:
    server_path = Path(__file__).parent.parent / "mcp-server" / "server.py"
    return MultiServerMCPClient(
        {
            "repo-reader": {
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


def extract_text(content: any) -> str:
    """Safely extract text content from a tool result."""
    if isinstance(content, dict):
        # Try common text keys
        for key in ("text", "content", "result"):
            if key in content and isinstance(content[key], str):
                return content[key]
        return json.dumps(content)
    elif isinstance(content, str):
        return content
    return str(content)


# ─── Anthropic client ─────────────────────────────────────────────────────────

anthropic = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def ask_claude(system: str, prompt: str, max_tokens: int = 2048) -> str:
    """Single Claude call with rate limit protection."""
    time.sleep(2)
    try:
        response = anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        return f"Error: {e}"


# ─── Agent 1: RepoAnalyzer ────────────────────────────────────────────────────

REPO_ANALYZER_SYSTEM = """You are an expert Android/Kotlin architect.
Your job is to analyze a repository structure and provide a concise architectural assessment.

Focus on:
- Architecture pattern (MVVM, MVI, MVP, Clean Architecture)
- Key frameworks and libraries detected
- Code organization quality
- Potential architectural issues
- Complexity assessment

Be concise and specific. Format as structured markdown."""


async def run_repo_analyzer(state: PipelineState, tools: list) -> PipelineState:
    print("\n" + "═" * 60)
    print("  🔍 AGENT 1: RepoAnalyzer")
    print("═" * 60)

    # Get repo summary
    print("  📊 Fetching repository summary...")
    summary = await call_tool(tools, "get_repo_summary", {
        "repo_path": state.repo_path
    })
    state.repo_summary = summary
    state.frameworks = summary.get("detected_frameworks", [])

    # Get structure
    print("  🗂️  Mapping directory structure...")
    structure_result = await call_tool(tools, "get_repo_structure", {
        "repo_path": state.repo_path,
        "max_depth": 4,
    })
    # Extract the actual tree text
    structure_text = extract_text(structure_result)

    # Get Kotlin files
    print("  📂 Listing Kotlin files...")
    files_result = await call_tool(tools, "list_files", {
        "repo_path": state.repo_path,
        "languages": ["kotlin"],
        "max_files": 500,
    })
    state.kotlin_files = files_result.get("files", [])
    print(f"  Found {len(state.kotlin_files)} Kotlin files")

    # Read key files for deeper analysis
    key_files_content = ""
    key_patterns = ["ViewModel", "Repository", "Database", "Application", "MainActivity"]
    key_files = [
        f for f in state.kotlin_files
        if any(p in f["path"] for p in key_patterns)
    ][:5]

    for f in key_files:
        file_path = str(Path(state.repo_path) / f["path"])
        content = await call_tool(tools, "read_file", {
            "file_path": file_path,
            "repo_path": state.repo_path,
            "include_line_numbers": False,
        })
        text = extract_text(content)
        if text:
            key_files_content += f"\n\n--- {f['path']} ---\n{text[:1500]}"

    # Ask Claude for architectural assessment
    print("  🤖 Generating architectural assessment...")
    lang_breakdown = summary.get("language_breakdown", {})

    prompt = f"""Analyze this Android/Kotlin repository:

REPO PATH: {state.repo_path}
DETECTED FRAMEWORKS: {state.frameworks}
LANGUAGE BREAKDOWN: {json.dumps(lang_breakdown, indent=2)}
TOTAL FILES: {summary.get('total_files', 0)}
TOTAL LINES: {summary.get('total_lines', 0)}

DIRECTORY STRUCTURE:
{structure_text[:3000]}

KEY FILES ANALYZED:
{key_files_content[:3000]}

Provide a concise architectural assessment covering:
1. Architecture pattern (MVVM/MVI/MVP/Clean)
2. Key frameworks and their usage
3. Code organization quality
4. Potential architectural issues
5. Complexity assessment"""

    state.architecture = ask_claude(REPO_ANALYZER_SYSTEM, prompt)
    state.agent_logs.append(
        f"RepoAnalyzer: analyzed {len(state.kotlin_files)} Kotlin files"
    )

    print("  ✅ RepoAnalyzer complete")
    print(f"\n{state.architecture[:500]}...")

    return state


# ─── Agent 2: BugDetector ─────────────────────────────────────────────────────

async def run_bug_detector(state: PipelineState, tools: list) -> PipelineState:
    print("\n" + "═" * 60)
    print("  🐛 AGENT 2: BugDetector")
    print("═" * 60)

    all_findings = []

    for i, file_info in enumerate(state.kotlin_files):
        file_path = str(Path(state.repo_path) / file_info["path"])
        file_name = Path(file_path).name
        print(f"  [{i+1}/{len(state.kotlin_files)}] 🔍 {file_name}")

        file_findings = []
        for tool_name in [
            "analyze_kotlin_bugs",
            "analyze_kotlin_performance",
            "analyze_kotlin_patterns",
        ]:
            result = await call_tool(tools, tool_name, {
                "file_path": file_path,
                "repo_path": state.repo_path,
            })
            findings = result.get("findings", [])
            for f in findings:
                f["file"] = file_info["path"]
                file_findings.append(f)

        if file_findings:
            print(f"    ⚡ {len(file_findings)} findings")

        all_findings.extend(file_findings)

    state.bug_findings = all_findings
    state.total_files_scanned = len(state.kotlin_files)
    state.agent_logs.append(
        f"BugDetector: found {len(all_findings)} issues in "
        f"{len(state.kotlin_files)} files"
    )

    print(f"\n  ✅ BugDetector complete — {len(all_findings)} findings")
    return state


# ─── Agent 3: SecurityAuditor ─────────────────────────────────────────────────

SECURITY_SYSTEM = """You are an expert Android security auditor.
You specialize in finding security vulnerabilities in Android/Kotlin apps.

Focus areas:
- Hardcoded API keys, secrets, passwords in source code
- Insecure network communication (HTTP vs HTTPS)
- Insecure data storage (SharedPreferences for sensitive data)
- Permission misuse (requesting too many permissions)
- SQL injection in Room queries
- Insecure WebView configurations
- Exported components without proper protection
- Sensitive data in logs
- Certificate pinning absence
- Insecure random number generation

For each finding provide:
- File and approximate line area
- Severity (critical/high/medium/low)
- Specific vulnerability description
- Concrete remediation steps

Respond in JSON format:
{
  "findings": [
    {
      "file": "path/to/file.kt",
      "area": "class or function name",
      "severity": "critical|high|medium|low",
      "title": "short title",
      "description": "detailed description",
      "remediation": "specific fix steps"
    }
  ],
  "overall_security_score": "A|B|C|D|F",
  "summary": "2-3 sentence overall assessment"
}"""


async def run_security_auditor(state: PipelineState, tools: list) -> PipelineState:
    print("\n" + "═" * 60)
    print("  🔒 AGENT 3: SecurityAuditor")
    print("═" * 60)

    # Run MCP security tool on all files
    print("  🔍 Running security scan on all files...")
    mcp_security_findings = []
    for file_info in state.kotlin_files:
        file_path = str(Path(state.repo_path) / file_info["path"])
        result = await call_tool(tools, "analyze_kotlin_security", {
            "file_path": file_path,
            "repo_path": state.repo_path,
        })
        for f in result.get("findings", []):
            f["file"] = file_info["path"]
            mcp_security_findings.append(f)

    print(f"  Found {len(mcp_security_findings)} initial security findings")

    # Build list of high-risk files to read — case insensitive matching
    high_risk_patterns = [
        "constants", "api", "network", "database",
        "prefs", "auth", "permission", "webview",
        "config", "secret", "key", "token",
    ]
    high_risk_files = [
        f for f in state.kotlin_files
        if any(p.lower() in f["path"].lower() for p in high_risk_patterns)
    ]

    # Always include Constants.kt and API service files regardless of name match
    always_include = ["Constants", "ApiService", "Api.kt", "Application"]
    for f in state.kotlin_files:
        if any(p in f["path"] for p in always_include):
            if f not in high_risk_files:
                high_risk_files.append(f)

    high_risk_files = high_risk_files[:8]
    print(
        f"  📂 Reading {len(high_risk_files)} high-risk files: "
        f"{[Path(f['path']).name for f in high_risk_files]}"
    )

    # Read each high-risk file
    files_content = ""
    for f in high_risk_files:
        file_path = str(Path(state.repo_path) / f["path"])
        content = await call_tool(tools, "read_file", {
            "file_path": file_path,
            "repo_path": state.repo_path,
            "include_line_numbers": True,
        })
        text = extract_text(content)
        if text:
            files_content += f"\n\n=== {f['path']} ===\n{text[:2000]}"

    # Deep security analysis with Claude
    print("  🤖 Deep security analysis with Claude...")
    prompt = f"""Security audit for Android app at: {state.repo_path}

Detected frameworks: {state.frameworks}

MCP Scanner found these security issues:
{json.dumps(mcp_security_findings, indent=2)[:2000]}

High-risk file contents for deeper analysis:
{files_content[:4000]}

Perform a thorough security audit and respond with JSON findings."""

    response = ask_claude(SECURITY_SYSTEM, prompt, max_tokens=3000)

    # Parse Claude's security analysis
    try:
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        security_data = json.loads(text.strip())
        claude_findings = security_data.get("findings", [])
        security_score = security_data.get("overall_security_score", "?")
        security_summary = security_data.get("summary", "")
    except Exception:
        claude_findings = []
        security_score = "?"
        security_summary = response[:500]

    # Combine MCP and Claude findings
    all_security = mcp_security_findings + claude_findings
    state.security_findings = all_security
    state.agent_logs.append(
        f"SecurityAuditor: found {len(all_security)} issues, "
        f"score: {security_score}"
    )
    state.agent_logs.append(f"SecurityScore:{security_score}")

    print("  ✅ SecurityAuditor complete")
    print(f"  🔒 Security score: {security_score}")
    print(f"  📋 Total security findings: {len(all_security)}")
    if security_summary:
        print(f"  💬 {security_summary[:200]}")

    return state


# ─── Agent 4: ReportWriter ────────────────────────────────────────────────────

REPORT_WRITER_SYSTEM = """You are a senior engineering lead writing an executive code review report.
Your report will be read by both technical and non-technical stakeholders.

Structure the report as professional markdown with:
1. Executive Summary (3-4 sentences, non-technical)
2. Repository Overview (metrics, architecture)
3. Critical Issues (must fix before release)
4. High Priority Issues (fix in next sprint)
5. Medium/Low Issues (technical debt)
6. Security Assessment
7. Architecture Recommendations
8. Positive Highlights (what the code does well)
9. Action Plan (prioritized checklist)

Be specific, reference actual file names and line numbers.
Be constructive — balance criticism with praise.
Use emojis for visual scanning. Be concise but thorough."""


async def run_report_writer(state: PipelineState) -> PipelineState:
    print("\n" + "═" * 60)
    print("  📝 AGENT 4: ReportWriter")
    print("═" * 60)
    print("  🤖 Synthesizing all findings into final report...")

    # Extract security score from logs
    security_score = "?"
    for log in state.agent_logs:
        if log.startswith("SecurityScore:"):
            security_score = log.split(":")[1]

    # Count severities across all findings
    all_findings = state.bug_findings + state.security_findings

    def count_sev(findings, sev):
        return sum(1 for f in findings if f.get("severity") == sev)

    critical = count_sev(all_findings, "critical")
    high = count_sev(all_findings, "high")
    medium = count_sev(all_findings, "medium")
    low = count_sev(all_findings, "low")

    # Top findings sorted by severity
    top_findings = sorted(
        all_findings,
        key=lambda f: {
            "critical": 0, "high": 1, "medium": 2, "low": 3
        }.get(f.get("severity", "low"), 4)
    )[:20]

    prompt = f"""Write a comprehensive code review report for this Android app.

REPOSITORY: {state.repo_path}
AGENT LOGS: {json.dumps(state.agent_logs, indent=2)}

ARCHITECTURAL ASSESSMENT:
{state.architecture}

METRICS:
- Files scanned: {state.total_files_scanned} Kotlin files
- Total findings: {len(all_findings)}
- Critical: {critical}
- High: {high}
- Medium: {medium}
- Low: {low}
- Security Score: {security_score}

TOP FINDINGS:
{json.dumps(top_findings, indent=2)[:3000]}

SECURITY FINDINGS:
{json.dumps(state.security_findings[:10], indent=2)[:2000]}

Write the full executive report now."""

    state.final_report = ask_claude(
        REPORT_WRITER_SYSTEM, prompt, max_tokens=4096
    )
    state.agent_logs.append("ReportWriter: final report generated")

    print("  ✅ ReportWriter complete")
    return state


# ─── Orchestrator ─────────────────────────────────────────────────────────────

async def run_pipeline(
    repo_path: str,
    output_file: str | None = None,
) -> PipelineState:
    start_time = time.time()

    print(f"\n{'═' * 60}")
    print(f"  🚀 MULTI-AGENT PIPELINE STARTING")
    print(f"{'═' * 60}")
    print(f"  Repo: {repo_path}")
    print(
        f"  Agents: RepoAnalyzer → BugDetector → "
        f"SecurityAuditor → ReportWriter"
    )
    print(f"{'═' * 60}")

    # Initialize shared state
    state = PipelineState(repo_path=repo_path)

    # Connect MCP tools (shared across all agents)
    print("\n🔧 Connecting MCP tools...")
    mcp_client = create_mcp_client()
    tools = await mcp_client.get_tools()
    print(f"  ✅ {len(tools)} tools loaded")

    # Run agents in sequence
    state = await run_repo_analyzer(state, tools)
    state = await run_bug_detector(state, tools)
    state = await run_security_auditor(state, tools)
    state = await run_report_writer(state)

    elapsed = round(time.time() - start_time, 1)

    # Print final report
    print(f"\n{'═' * 60}")
    print(f"  ✅ PIPELINE COMPLETE ({elapsed}s)")
    print(f"{'═' * 60}")
    print(f"\n{state.final_report}")

    # Save markdown report
    if output_file:
        out_path = Path(output_file)
        out_path.write_text(state.final_report, encoding="utf-8")
        print(f"\n💾 Report saved to: {output_file}")

    # Save full JSON data alongside
    if output_file:
        json_output = output_file.replace(".md", ".json")
        data = {
            "repo_path": state.repo_path,
            "architecture": state.architecture,
            "total_files_scanned": state.total_files_scanned,
            "bug_findings": state.bug_findings,
            "security_findings": state.security_findings,
            "agent_logs": state.agent_logs,
        }
        Path(json_output).write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"💾 JSON data saved to: {json_output}")

    return state


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python multi_agent.py <repo_path> [--output report.md]")
        print(
            "Example: python multi_agent.py "
            "C:/Users/dicky/projects/FoodApp --output report.md"
        )
        sys.exit(1)

    repo = sys.argv[1]
    output = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    asyncio.run(run_pipeline(repo, output))
