"""
Multi-Agent Orchestrator — Phase 5 (v3) — Multi-Language
Automatically detects languages and runs the right scanners.

Supported languages:
- Kotlin/Android  → server.py
- Java/Spring     → server_java.py
- TypeScript/React → server_typescript.py
- JavaScript/JSX  → server_javascript.py

Usage:
    python multi_agent.py <repo_path> [--output report.md]
    python multi_agent.py C:/Users/dicky/projects/FoodApp
    python multi_agent.py C:/Users/dicky/projects/next-store
    python multi_agent.py C:/Users/dicky/projects/my-fullstack-app
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


# ─── Language detection ───────────────────────────────────────────────────────

LANGUAGE_EXTENSIONS = {
    "kotlin":     {".kt", ".kts"},
    "java":       {".java"},
    "typescript": {".ts", ".tsx"},
    "javascript": {".js", ".jsx", ".mjs"},
}

IGNORE_DIRS = {
    ".git", "node_modules", ".next", "dist", "build",
    ".gradle", ".idea", "target", "__pycache__",
    "generated", ".turbo", "coverage", ".cache",
}

LANGUAGE_LABELS = {
    "kotlin":     "🤖 Kotlin/Android",
    "java":       "☕ Java/Spring",
    "typescript": "📘 TypeScript/React",
    "javascript": "💛 JavaScript",
}


def detect_languages(repo_path: str) -> dict[str, list[Path]]:
    """Scan repo and return dict of language -> list of files."""
    repo = Path(repo_path)
    detected: dict[str, list[Path]] = {lang: [] for lang in LANGUAGE_EXTENSIONS}

    for path in repo.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        for lang, exts in LANGUAGE_EXTENSIONS.items():
            if ext in exts:
                # Skip generated files
                rel = str(path.relative_to(repo)).replace("\\", "/")
                if "generated" not in rel and ".d.ts" not in rel:
                    detected[lang].append(path)

    # Filter out languages with 0 files
    return {k: v for k, v in detected.items() if v}


def get_mcp_servers(detected_languages: dict, repo_root: Path) -> dict:
    """Build MCP server config for detected languages."""
    server_map = {
        "kotlin":     "server.py",
        "java":       "server_java.py",
        "typescript": "server_typescript.py",
        "javascript": "server_javascript.py",
    }
    servers = {}
    for lang in detected_languages:
        server_file = repo_root / "mcp-server" / server_map[lang]
        if server_file.exists():
            servers[f"{lang}-analyzer"] = {
                "command": "python",
                "args": [str(server_file)],
                "transport": "stdio",
            }
    return servers


# ─── Shared state ─────────────────────────────────────────────────────────────

@dataclass
class PipelineState:
    repo_path: str
    detected_languages: dict[str, list[Path]] = field(default_factory=dict)
    repo_summary: dict = field(default_factory=dict)
    architecture: str = ""
    frameworks: list[str] = field(default_factory=list)
    # Findings per language
    findings_by_language: dict[str, list[dict]] = field(default_factory=dict)
    security_findings: list[dict] = field(default_factory=dict)
    files_scanned_by_language: dict[str, int] = field(default_factory=dict)
    final_report: str = ""
    reports_by_language: dict[str, str] = field(default_factory=dict)
    agent_logs: list[str] = field(default_factory=list)


# ─── MCP helpers ─────────────────────────────────────────────────────────────

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
    if isinstance(content, dict):
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


# ─── Language-specific tool configs ──────────────────────────────────────────

LANGUAGE_TOOL_SETS = {
    "kotlin": [
        "analyze_kotlin_bugs",
        "analyze_kotlin_security",
        "analyze_kotlin_performance",
        "analyze_kotlin_patterns",
    ],
    "java": [
        "analyze_java_bugs",
        "analyze_spring_patterns",
        "analyze_spring_security",
        "analyze_spring_performance",
        "analyze_jpa_issues",
    ],
    "typescript": [
        "analyze_ts_bugs",
        "analyze_react_hooks",
        "analyze_react_patterns",
        "analyze_nextjs_patterns",
        "analyze_ts_security",
    ],
    "javascript": [
        "analyze_js_bugs",
        "analyze_js_security",
        "analyze_js_patterns",
        "analyze_nextjs_js",
        "analyze_react_js",
    ],
}

LIST_TOOLS = {
    "kotlin":     ("list_files", {"languages": ["kotlin"], "max_files": 500}),
    "java":       ("list_java_files", {"file_type": "all", "include_tests": False}),
    "typescript": ("list_ts_files", {"file_type": "all", "include_tests": False}),
    "javascript": ("list_js_files", {"file_type": "all", "include_tests": False}),
}


# ─── Agent 1: RepoAnalyzer ────────────────────────────────────────────────────

REPO_ANALYZER_SYSTEM = """You are an expert software architect.
Analyze this repository and provide a concise architectural assessment covering:
1. Architecture pattern (MVVM/MVI/MVP/Clean/MVC/Layered)
2. Key frameworks and their usage
3. Code organization quality
4. Detected languages and their roles
5. Potential architectural issues
Be concise and specific. Format as structured markdown."""


async def run_repo_analyzer(state: PipelineState, tools: list) -> PipelineState:
    print("\n" + "═" * 60)
    print("  🔍 AGENT 1: RepoAnalyzer")
    print("═" * 60)

    # Detect languages
    print("  🔎 Detecting languages...")
    state.detected_languages = detect_languages(state.repo_path)

    print(f"  Found languages:")
    for lang, files in state.detected_languages.items():
        print(f"    {LANGUAGE_LABELS[lang]}: {len(files)} files")

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
    structure_text = extract_text(structure_result)

    # Read key files
    key_files_content = ""
    all_files_result = await call_tool(tools, "list_files", {
        "repo_path": state.repo_path,
        "max_files": 200,
    })
    all_files = all_files_result.get("files", [])

    key_patterns = ["ViewModel", "Repository", "Database", "Application",
                    "MainActivity", "Controller", "Service", "page", "route",
                    "layout", "middleware", "index"]
    key_files = [
        f for f in all_files
        if any(p.lower() in f["path"].lower() for p in key_patterns)
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
    lang_summary = "\n".join(
        f"  - {LANGUAGE_LABELS[lang]}: {len(files)} files"
        for lang, files in state.detected_languages.items()
    )

    prompt = f"""Analyze this repository:

REPO: {state.repo_path}
DETECTED FRAMEWORKS: {state.frameworks}
LANGUAGE BREAKDOWN:
{lang_summary}

DIRECTORY STRUCTURE:
{structure_text[:2000]}

KEY FILES:
{key_files_content[:2000]}

Provide architectural assessment."""

    state.architecture = ask_claude(REPO_ANALYZER_SYSTEM, prompt)
    state.agent_logs.append(
        f"RepoAnalyzer: detected {list(state.detected_languages.keys())}"
    )

    print("  ✅ RepoAnalyzer complete")
    print(f"\n{state.architecture[:400]}...")
    return state


# ─── Agent 2: Multi-Language BugDetector ─────────────────────────────────────

async def run_bug_detector(state: PipelineState, all_tools: list) -> PipelineState:
    print("\n" + "═" * 60)
    print("  🐛 AGENT 2: BugDetector (Multi-Language)")
    print("═" * 60)

    for lang, lang_files in state.detected_languages.items():
        label = LANGUAGE_LABELS[lang]
        print(f"\n  {label} — scanning {len(lang_files)} files...")

        # Get the list tool for this language
        list_tool_name, list_tool_extra = LIST_TOOLS[lang]
        list_args = {"repo_path": state.repo_path, **list_tool_extra}

        files_result = await call_tool(all_tools, list_tool_name, list_args)
        files = files_result.get("files", [])

        if not files:
            print(f"    ⚠️  No files returned by {list_tool_name}")
            continue

        analysis_tools = LANGUAGE_TOOL_SETS[lang]
        lang_findings = []

        for i, file_info in enumerate(files):
            file_path = str(Path(state.repo_path) / file_info["path"])
            file_name = Path(file_path).name
            print(f"    [{i+1}/{len(files)}] 🔍 {file_name}")

            for tool_name in analysis_tools:
                result = await call_tool(all_tools, tool_name, {
                    "file_path": file_path,
                    "repo_path": state.repo_path,
                })
                findings = result.get("findings", [])
                if findings:
                    print(f"      ⚡ {tool_name}: {len(findings)}")
                for f in findings:
                    f["file"] = file_info["path"]
                    f["language"] = lang
                    lang_findings.append(f)

        state.findings_by_language[lang] = lang_findings
        state.files_scanned_by_language[lang] = len(files)
        total = len(lang_findings)
        state.agent_logs.append(
            f"BugDetector [{lang}]: {total} findings in {len(files)} files"
        )
        print(f"\n  ✅ {label}: {total} findings")

    total_all = sum(len(v) for v in state.findings_by_language.values())
    print(f"\n  ✅ BugDetector complete — {total_all} total findings across all languages")
    return state


# ─── Agent 3: SecurityAuditor ─────────────────────────────────────────────────

SECURITY_SYSTEM = """You are an expert security auditor covering multiple languages and frameworks.
Analyze security vulnerabilities across the entire codebase.

Focus on:
- Hardcoded secrets, API keys, passwords
- Authentication and authorization gaps
- Injection vulnerabilities (SQL, command, XSS)
- Insecure cryptography (weak algorithms, Math.random for security)
- Insecure data storage
- Missing input validation
- CORS misconfiguration
- Exposed sensitive data

Respond in JSON:
{
  "findings": [
    {
      "file": "path/to/file",
      "area": "class or function",
      "severity": "critical|high|medium|low",
      "title": "short title",
      "description": "detailed description",
      "remediation": "specific fix"
    }
  ],
  "overall_security_score": "A|B|C|D|F",
  "summary": "2-3 sentence assessment"
}"""


async def run_security_auditor(state: PipelineState, all_tools: list) -> PipelineState:
    print("\n" + "═" * 60)
    print("  🔒 AGENT 3: SecurityAuditor")
    print("═" * 60)

    # Run security tools for each detected language
    mcp_security: list[dict] = []
    security_tool_map = {
        "kotlin":     "analyze_kotlin_security",
        "java":       "analyze_spring_security",
        "typescript": "analyze_ts_security",
        "javascript": "analyze_js_security",
    }

    for lang, lang_files in state.detected_languages.items():
        tool_name = security_tool_map.get(lang)
        if not tool_name:
            continue

        list_tool_name, list_tool_extra = LIST_TOOLS[lang]
        files_result = await call_tool(
            all_tools, list_tool_name,
            {"repo_path": state.repo_path, **list_tool_extra}
        )
        files = files_result.get("files", [])

        print(f"  🔍 {LANGUAGE_LABELS[lang]}: scanning {len(files)} files...")
        for file_info in files:
            file_path = str(Path(state.repo_path) / file_info["path"])
            result = await call_tool(all_tools, tool_name, {
                "file_path": file_path,
                "repo_path": state.repo_path,
            })
            for f in result.get("findings", []):
                f["file"] = file_info["path"]
                f["language"] = lang
                mcp_security.append(f)

    print(f"  Found {len(mcp_security)} initial security findings")

    # Deep analysis with Claude on high-risk files
    print("  🤖 Deep security analysis with Claude...")
    high_risk_patterns = [
        "auth", "secret", "key", "password", "token",
        "api", "route", "config", "env", "crypto",
        "constants", "middleware",
    ]

    files_content = ""
    seen_files = set()
    for lang, lang_files in state.detected_languages.items():
        for path in lang_files:
            rel = str(path.relative_to(state.repo_path)).replace("\\", "/")
            if rel in seen_files:
                continue
            if any(p in rel.lower() for p in high_risk_patterns):
                seen_files.add(rel)
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    files_content += f"\n\n=== {rel} ===\n{text[:1500]}"
                    if len(files_content) > 5000:
                        break
                except OSError:
                    pass
        if len(files_content) > 5000:
            break

    lang_summary = ", ".join(LANGUAGE_LABELS[l] for l in state.detected_languages)
    prompt = f"""Security audit for: {state.repo_path}
Languages: {lang_summary}
Frameworks: {state.frameworks}

MCP Scanner found:
{json.dumps(mcp_security[:20], indent=2)[:2000]}

High-risk file contents:
{files_content[:3000]}

Perform thorough security audit and respond with JSON."""

    response = ask_claude(SECURITY_SYSTEM, prompt, max_tokens=3000)

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
        security_summary = response[:300]

    state.security_findings = mcp_security + claude_findings
    state.agent_logs.append(
        f"SecurityAuditor: {len(state.security_findings)} issues, score: {security_score}"
    )
    state.agent_logs.append(f"SecurityScore:{security_score}")

    print(f"  ✅ SecurityAuditor complete")
    print(f"  🔒 Security score: {security_score}")
    print(f"  📋 Total security findings: {len(state.security_findings)}")
    if security_summary:
        print(f"  💬 {security_summary[:150]}")

    return state


# ─── Agent 4: ReportWriter ────────────────────────────────────────────────────

REPORT_WRITER_SYSTEM = """You are a senior engineering lead writing an executive code review report.
Write professional markdown with:
1. Executive Summary (3-4 sentences, non-technical)
2. Repository Overview (metrics, languages, architecture)
3. Critical Issues (must fix before release)
4. High Priority Issues (fix in next sprint)
5. Medium/Low Issues (technical debt)
6. Security Assessment
7. Per-Language Analysis (one section per language found)
8. Architecture Recommendations
9. Positive Highlights
10. Action Plan (prioritized checklist)
Be specific with file names and line numbers.
Use emojis for visual scanning. Be constructive."""


async def run_report_writer(state: PipelineState) -> PipelineState:
    print("\n" + "═" * 60)
    print("  📝 AGENT 4: ReportWriter")
    print("═" * 60)
    print("  🤖 Synthesizing findings into final report...")

    security_score = "?"
    for log in state.agent_logs:
        if log.startswith("SecurityScore:"):
            security_score = log.split(":")[1]

    # Aggregate all findings
    all_findings = []
    for findings in state.findings_by_language.values():
        all_findings.extend(findings)
    all_findings.extend(state.security_findings)

    def count_sev(findings, sev):
        return sum(1 for f in findings if f.get("severity") == sev)

    critical = count_sev(all_findings, "critical")
    high = count_sev(all_findings, "high")
    medium = count_sev(all_findings, "medium")
    low = count_sev(all_findings, "low")

    # Per-language summary
    lang_summary = ""
    for lang, findings in state.findings_by_language.items():
        files = state.files_scanned_by_language.get(lang, 0)
        c = count_sev(findings, "critical")
        h = count_sev(findings, "high")
        m = count_sev(findings, "medium")
        lang_summary += (
            f"\n{LANGUAGE_LABELS[lang]}: "
            f"{files} files, {len(findings)} findings "
            f"(🔴{c} 🟠{h} 🟡{m})"
        )

    top_findings = sorted(
        all_findings,
        key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
            f.get("severity", "low"), 4
        )
    )[:25]

    prompt = f"""Write a comprehensive multi-language code review report.

REPOSITORY: {state.repo_path}
LANGUAGES DETECTED: {list(state.detected_languages.keys())}
AGENT LOGS: {json.dumps(state.agent_logs, indent=2)}

ARCHITECTURAL ASSESSMENT:
{state.architecture}

METRICS:
- Languages: {lang_summary}
- Total findings: {len(all_findings)}
- Critical: {critical} | High: {high} | Medium: {medium} | Low: {low}
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


# ─── Per-language reports ─────────────────────────────────────────────────────

async def generate_language_reports(
    state: PipelineState,
    output_dir: str,
) -> None:
    """Generate separate HTML report per language using reporter module."""
    from reporter import generate_report, ReportConfig

    print("\n  📊 Generating per-language HTML reports...")

    for lang, findings in state.findings_by_language.items():
        if not findings:
            continue

        config = ReportConfig(
            repo_path=state.repo_path,
            repo_name=f"{Path(state.repo_path).name} [{lang}]",
            language=lang,
            output_dir=output_dir,
            create_github_issues=False,
            send_slack=False,
        )

        # Generate AI summary for this language
        time.sleep(1)
        try:
            anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            by_sev = {"critical": [], "high": [], "medium": [], "low": []}
            for f in findings:
                by_sev.get(f.get("severity", "low"), []).append(f)
            summary_text = f"Language: {lang}\nFindings: {len(findings)}\n"
            for sev, items in by_sev.items():
                if items:
                    summary_text += f"{sev}: {len(items)}\n"
                    for f in items[:3]:
                        summary_text += f"  - {f.get('title', '')} in {Path(f.get('file', '')).name}\n"
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                system=f"Expert {lang} code reviewer. Summarize findings in 100 words.",
                messages=[{"role": "user", "content": summary_text}],
            )
            lang_ai_summary = resp.content[0].text
        except Exception:
            lang_ai_summary = ""

        result = await generate_report(findings, config, lang_ai_summary)
        state.reports_by_language[lang] = result.get("html_report", "")
        print(f"    ✅ {LANGUAGE_LABELS[lang]} report: {result.get('html_report', '')}")


# ─── Combined report ──────────────────────────────────────────────────────────

async def generate_combined_report(
    state: PipelineState,
    output_dir: str,
) -> str:
    """Generate one combined HTML report with all languages."""
    from reporter import generate_report, ReportConfig

    all_findings = []
    for findings in state.findings_by_language.values():
        all_findings.extend(findings)

    # Normalize security findings — Claude uses different field names
    for f in state.security_findings:
        normalized = {
            "file": f.get("file", "unknown"),
            "line": f.get("line", 0),
            "severity": f.get("severity", "medium"),
            "category": f.get("category", f.get("area", "security")),
            "title": f.get("title", "Security Issue"),
            "description": f.get("description", ""),
            "suggested_fix": f.get("suggested_fix", f.get("remediation", "")),
        }
        all_findings.append(normalized)

    repo_name = Path(state.repo_path).name
    config = ReportConfig(
        repo_path=state.repo_path,
        repo_name=f"{repo_name} [all languages]",
        language="multi",
        output_dir=output_dir,
        create_github_issues=False,
        send_slack=False,
    )

    result = await generate_report(all_findings, config, "")
    combined_path = result.get("html_report", "")
    print(f"\n  ✅ Combined report: {combined_path}")
    return combined_path


# ─── Orchestrator ─────────────────────────────────────────────────────────────

async def run_pipeline(
    repo_path: str,
    output_file: str | None = None,
) -> PipelineState:
    start_time = time.time()
    repo_root = Path(__file__).parent.parent  # coding-agent root

    print(f"\n{'═' * 60}")
    print(f"  🚀 MULTI-LANGUAGE PIPELINE STARTING")
    print(f"{'═' * 60}")
    print(f"  Repo: {repo_path}")

    # First detect languages to know which servers to start
    print("\n🔎 Pre-scan: detecting languages...")
    detected = detect_languages(repo_path)
    if not detected:
        print("❌ No supported source files found!")
        sys.exit(1)

    lang_list = [LANGUAGE_LABELS[l] for l in detected]
    print(f"  Detected: {', '.join(lang_list)}")
    print(f"  Agents: RepoAnalyzer → BugDetector → SecurityAuditor → ReportWriter")
    print(f"{'═' * 60}")

    # Connect all needed MCP servers at once
    print("\n🔧 Connecting MCP servers...")
    # Always include the base server (Kotlin) for repo reading tools
    servers = get_mcp_servers(detected, repo_root)

    # Always add base server for repo structure tools
    base_server = repo_root / "mcp-server" / "server.py"
    if "kotlin-analyzer" not in servers and base_server.exists():
        servers["base-reader"] = {
            "command": "python",
            "args": [str(base_server)],
            "transport": "stdio",
        }

    print(f"  Servers: {list(servers.keys())}")
    mcp_client = MultiServerMCPClient(servers)
    all_tools = await mcp_client.get_tools()
    print(f"  ✅ {len(all_tools)} tools loaded across all servers")

    # Initialize state
    state = PipelineState(repo_path=repo_path)

    # Run agents
    state = await run_repo_analyzer(state, all_tools)
    state = await run_bug_detector(state, all_tools)
    state = await run_security_auditor(state, all_tools)
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
        print(f"\n💾 Markdown report: {output_file}")

    # Generate HTML reports
    output_dir = str(Path(output_file).parent) if output_file else "reports"

    # Per-language reports
    await generate_language_reports(state, output_dir)

    # Combined report
    await generate_combined_report(state, output_dir)

    # Save full JSON
    json_output = output_file.replace(".md", ".json") if output_file else None
    if json_output:
        data = {
            "repo_path": state.repo_path,
            "detected_languages": list(state.detected_languages.keys()),
            "architecture": state.architecture,
            "findings_by_language": state.findings_by_language,
            "security_findings": state.security_findings,
            "files_scanned_by_language": state.files_scanned_by_language,
            "agent_logs": state.agent_logs,
        }
        Path(json_output).write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"💾 JSON data: {json_output}")

    return state


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python multi_agent.py <repo_path> [--output report.md]")
        print("Example: python multi_agent.py C:/Users/dicky/projects/FoodApp")
        print("Example: python multi_agent.py C:/Users/dicky/projects/next-store")
        sys.exit(1)

    repo = sys.argv[1]
    output = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    asyncio.run(run_pipeline(repo, output))
