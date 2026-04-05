"""
GitHub Actions Runner — AI Code Review
Self-contained script that runs inside GitHub Actions.
No MCP/LangGraph needed — uses Anthropic API directly.

Triggered by:
- PR opened/updated → reviews changed Kotlin files
- Push to main → posts full scan summary as commit status
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from anthropic import Anthropic

# ─── Environment ─────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_OWNER = os.environ.get("REPO_OWNER", "")
REPO_NAME = os.environ.get("REPO_NAME", "")
PR_NUMBER = os.environ.get("PR_NUMBER", "")
HEAD_SHA = os.environ.get("HEAD_SHA", "")
HEAD_REF = os.environ.get("HEAD_REF", "")
SCAN_MODE = os.environ.get("SCAN_MODE", "pr")

GITHUB_API = "https://api.github.com"
anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)


def github_headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ─── Kotlin bug scanner (inline — no MCP needed) ─────────────────────────────

def scan_kotlin_file(content: str, file_path: str) -> list[dict]:
    """Run regex-based Kotlin analysis directly — no MCP server needed."""
    lines = content.splitlines()
    findings = []

    # Track multiline strings
    in_multiline = False

    checks = {
        "bugs": [
            (r"!!", "Force unwrap operator (!!)",
             "Can cause NullPointerException at runtime",
             "Use safe call (?.), elvis operator (?:), or requireNotNull()", "high"),
            (r"catch\s*\([^)]+\)\s*\{\s*\}", "Empty catch block",
             "Swallowing exceptions silently hides errors",
             "At minimum log the exception, or rethrow if unrecoverable", "medium"),
            (r"GlobalScope\.(launch|async)", "GlobalScope coroutine",
             "Not tied to lifecycle — causes memory leaks",
             "Use viewModelScope or lifecycleScope instead", "high"),
            (r"runBlocking\s*\{", "runBlocking usage",
             "Blocks the thread — causes ANR on main thread",
             "Use suspend functions or launch/async instead", "high"),
            (r"\.printStackTrace\(\)", "printStackTrace() usage",
             "Lost in production — output goes to stderr only",
             "Use proper logging framework (Timber)", "low"),
        ],
        "security": [
            (r'(?:api_?key|password|secret|token)\s*=\s*"[^"]{4,}"',
             "Hardcoded secret",
             "Credentials in source code exposed in version control",
             "Move to BuildConfig fields or Android Keystore", "critical"),
            (r'http://(?!localhost|127\.0\.0\.1)',
             "Insecure HTTP connection",
             "Plain HTTP can be intercepted",
             "Use HTTPS everywhere", "high"),
            (r'MD5|SHA1(?![\d])', "Weak cryptographic hash",
             "MD5/SHA-1 are cryptographically broken",
             "Use SHA-256 or stronger", "high"),
        ],
        "performance": [
            (r'FetchType\.EAGER', "FetchType.EAGER on relationship",
             "Always loads related entities — causes N+1 problems",
             "Use FetchType.LAZY and load explicitly when needed", "high"),
            (r'Thread\.sleep\(', "Thread.sleep() usage",
             "Blocks the thread — causes ANR on main thread",
             "Use delay() in a coroutine instead", "high"),
        ],
        "pattern": [
            (r'MutableStateFlow|MutableLiveData|MutableSharedFlow',
             "Mutable state potentially exposed publicly",
             "MVI: Mutable state should be private",
             "private val _state = MutableStateFlow(...); val state = _state.asStateFlow()", "medium"),
            (r'viewModelScope\.launch\s*\{(?![^}]*Dispatchers)',
             "viewModelScope without explicit dispatcher",
             "IO operations need Dispatchers.IO specified",
             "Use viewModelScope.launch(Dispatchers.IO) { } for IO", "medium"),
        ],
    }

    for i, line in enumerate(lines):
        # Skip multiline strings
        triple_count = line.count('"""')
        if triple_count % 2 != 0:
            in_multiline = not in_multiline
            continue
        if in_multiline:
            continue

        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue

        for category, check_list in checks.items():
            for pattern, title, desc, fix, severity in check_list:
                if re.search(pattern, line, re.IGNORECASE):
                    # Extra check for 'as' — clean string literals first
                    cleaned = re.sub(r'"[^"]*"', '""', line)
                    cleaned = re.sub(r"'[^']*'", "''", cleaned)
                    findings.append({
                        "line": i + 1,
                        "code": stripped[:100],
                        "title": title,
                        "description": desc,
                        "suggested_fix": fix,
                        "severity": severity,
                        "category": category,
                    })

    return findings


# ─── GitHub API helpers ───────────────────────────────────────────────────────

async def get_pr_files(pr_number: int) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/files",
            headers=github_headers(),
            params={"per_page": 100},
        )
        resp.raise_for_status()
        return resp.json()


async def get_file_content(file_path: str, ref: str) -> str:
    import base64
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{file_path}",
            headers=github_headers(),
            params={"ref": ref},
        )
        if resp.status_code == 404:
            return ""
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


async def get_pr_info(pr_number: int) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}",
            headers=github_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def post_review(
    pr_number: int,
    commit_sha: str,
    body: str,
    comments: list[dict],
    action: str,
) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/reviews",
            headers=github_headers(),
            json={
                "commit_id": commit_sha,
                "body": body,
                "event": action,
                "comments": comments,
            },
        )
        if resp.status_code not in (200, 201):
            print(f"  ⚠️  Review post failed: {resp.status_code} — {resp.text[:200]}")


async def post_comment(pr_number: int, body: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr_number}/comments",
            headers=github_headers(),
            json={"body": body},
        )
        if resp.status_code not in (200, 201):
            print(f"  ⚠️  Comment post failed: {resp.status_code}")


def get_first_changed_position(patch: str) -> int | None:
    if not patch:
        return None
    position = 0
    for line in patch.split("\n"):
        position += 1
        if line.startswith("+") and not line.startswith("+++"):
            return position
    return 1


# ─── AI summary ───────────────────────────────────────────────────────────────

async def generate_ai_summary(findings: list[dict], repo: str) -> str:
    if not findings:
        return ""
    await asyncio.sleep(2)
    try:
        by_sev = {"critical": [], "high": [], "medium": [], "low": []}
        for f in findings:
            by_sev.get(f.get("severity", "low"), []).append(f)

        summary_text = f"Kotlin/Android repo: {repo}\nTotal: {len(findings)}\n"
        for sev, items in by_sev.items():
            if items:
                summary_text += f"{sev.upper()} ({len(items)}):\n"
                for f in items[:5]:
                    summary_text += f"  - {f['title']} in {Path(f['file']).name}:{f['line']}\n"

        resp = anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=(
                "Expert Android/Kotlin reviewer. "
                "Summarize PR review findings in 3-4 sentences. "
                "Be specific and actionable."
            ),
            messages=[{"role": "user", "content": summary_text}],
        )
        return resp.content[0].text
    except Exception as e:
        return f"*AI summary unavailable: {e}*"


# ─── Format comments ──────────────────────────────────────────────────────────

def format_file_comment(filename: str, findings: list[dict]) -> str:
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_f = sorted(findings, key=lambda f: sev_order.get(f.get("severity", "low"), 4))

    lines = [
        f"## 🤖 AI Review — `{Path(filename).name}`",
        f"Found **{len(findings)} issue(s)**:",
        "",
    ]
    for f in sorted_f:
        sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
            f.get("severity", "low"), "⚪"
        )
        cat_icon = {"security": "🔒", "bug": "🐛", "performance": "⚡", "pattern": "🏗️"}.get(
            f.get("category", "bug"), "📌"
        )
        lines += [
            f"### {sev_icon} [{f['severity'].upper()}] {cat_icon} {f['title']} *(line {f['line']})*",
            f"{f['description']}",
            f"**Fix:** {f['suggested_fix']}",
            "",
        ]
    lines.append("*Posted by [AI Coding Agent](https://github.com/Dicky59/coding-agent)*")
    return "\n".join(lines)


def format_summary_comment(
    findings: list[dict],
    files_scanned: int,
    ai_summary: str,
    action: str,
) -> str:
    critical = sum(1 for f in findings if f.get("severity") == "critical")
    high = sum(1 for f in findings if f.get("severity") == "high")
    medium = sum(1 for f in findings if f.get("severity") == "medium")
    low = sum(1 for f in findings if f.get("severity") == "low")

    action_line = {
        "APPROVE": "✅ **No blocking issues found — PR approved!**",
        "REQUEST_CHANGES": f"❌ **Found {critical + high} critical/high issue(s) — changes requested.**",
        "COMMENT": f"💬 **Found {medium + low} minor issue(s) — review comments posted.**",
    }.get(action, "")

    lines = [
        "## 🤖 AI Code Review Report",
        "",
        action_line,
        "",
        f"Scanned **{files_scanned} Kotlin file(s)** changed in this PR.",
        "",
        "| Severity | Count |",
        "|----------|-------|",
        f"| 🔴 Critical | {critical} |",
        f"| 🟠 High | {high} |",
        f"| 🟡 Medium | {medium} |",
        f"| 🟢 Low | {low} |",
        f"| **Total** | **{len(findings)}** |",
        "",
    ]

    if ai_summary:
        lines += ["### 🧠 AI Analysis", "", ai_summary, ""]

    if not findings:
        lines += ["### ✅ No issues found!", ""]
    else:
        by_cat: dict[str, list] = {}
        for f in findings:
            by_cat.setdefault(f.get("category", "bug"), []).append(f)

        cat_labels = {
            "security": "🔒 Security",
            "bug": "🐛 Bugs",
            "performance": "⚡ Performance",
            "pattern": "🏗️ Patterns",
        }
        lines.append("### All Findings")
        lines.append("")
        for cat, label in cat_labels.items():
            items = by_cat.get(cat, [])
            if not items:
                continue
            lines.append(f"**{label}** ({len(items)})")
            for f in items:
                sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    f.get("severity", "low"), "⚪"
                )
                lines.append(
                    f"- {sev_icon} `{Path(f['file']).name}:{f['line']}` — {f['title']}"
                )
            lines.append("")

    lines += [
        "---",
        "*Generated by [AI Coding Agent](https://github.com/Dicky59/coding-agent)*",
    ]
    return "\n".join(lines)


# ─── PR review mode ───────────────────────────────────────────────────────────

async def run_pr_review() -> None:
    pr_number = int(PR_NUMBER)
    print(f"\n🔍 AI PR Review starting...")
    print(f"📋 {REPO_OWNER}/{REPO_NAME} PR #{pr_number}")

    # Get PR info
    pr_info = await get_pr_info(pr_number)
    commit_sha = pr_info["head"]["sha"]
    branch = pr_info["head"]["ref"]
    print(f"  Branch: {branch} | Commit: {commit_sha[:8]}")

    # Get changed files
    pr_files = await get_pr_files(pr_number)
    kotlin_files = [
        f for f in pr_files
        if f["filename"].endswith(".kt") and f["status"] != "removed"
    ]
    print(f"  Changed Kotlin files: {len(kotlin_files)}")

    if not kotlin_files:
        await post_comment(
            pr_number,
            "## 🤖 AI Code Review\n\nNo Kotlin files changed in this PR. ✅"
        )
        return

    # Scan each file
    all_findings = []
    file_patches: dict[str, str] = {}

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, file_info in enumerate(kotlin_files):
            filename = file_info["filename"]
            patch = file_info.get("patch", "")
            file_patches[filename] = patch

            print(f"  [{i+1}/{len(kotlin_files)}] 🔍 {Path(filename).name}")

            content = await get_file_content(filename, branch)
            if not content:
                continue

            findings = scan_kotlin_file(content, filename)
            if findings:
                print(f"    ⚡ {len(findings)} findings")

            for f in findings:
                f["file"] = filename
            all_findings.extend(findings)

    # Generate AI summary
    print("  🤖 Generating AI summary...")
    ai_summary = await generate_ai_summary(all_findings, REPO_NAME)

    # Build inline comments — one per file
    inline_comments = []
    files_with_findings: dict[str, list] = {}
    for f in all_findings:
        files_with_findings.setdefault(f["file"], []).append(f)

    for filename, findings in files_with_findings.items():
        patch = file_patches.get(filename, "")
        position = get_first_changed_position(patch)
        if position is None:
            continue
        inline_comments.append({
            "path": filename,
            "position": position,
            "body": format_file_comment(filename, findings),
        })

    # Decide action
    critical_high = sum(1 for f in all_findings if f.get("severity") in ("critical", "high"))
    if not all_findings:
        action = "APPROVE"
        review_body = "✅ No issues found in changed Kotlin files. Looks good!"
    elif critical_high == 0:
        action = "COMMENT"
        review_body = f"Found {len(all_findings)} minor issue(s). Consider addressing them."
    else:
        action = "REQUEST_CHANGES"
        review_body = f"Found {critical_high} critical/high issue(s) to address before merging."

    # Post review
    print(f"  📤 Posting review (action: {action}, inline: {len(inline_comments)})...")
    try:
        if inline_comments:
            await post_review(
                pr_number, commit_sha, review_body, inline_comments, action
            )
            print("  ✅ Inline review posted!")

        summary = format_summary_comment(
            all_findings, len(kotlin_files), ai_summary, action
        )
        await post_comment(pr_number, summary)
        print("  ✅ Summary comment posted!")
    except Exception as e:
        print(f"  ❌ Failed to post: {e}")

    print(f"\n{'═' * 50}")
    print(f"  ✅ PR REVIEW COMPLETE")
    print(f"  Files: {len(kotlin_files)} | Issues: {len(all_findings)} | Action: {action}")
    print(f"{'═' * 50}")


# ─── Full scan mode (push to main) ───────────────────────────────────────────

async def run_full_scan() -> None:
    print(f"\n🔍 Full scan on push to main...")
    print(f"📁 {REPO_OWNER}/{REPO_NAME}")

    # Find all Kotlin files in the repo
    import subprocess
    result = subprocess.run(
        ["find", ".", "-name", "*.kt",
         "-not", "-path", "*/build/*",
         "-not", "-path", "*/.gradle/*",
         "-not", "-path", "*/.git/*"],
        capture_output=True, text=True
    )

    kt_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    print(f"  Found {len(kt_files)} Kotlin files")

    all_findings = []
    for file_path in kt_files:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
            findings = scan_kotlin_file(content, file_path)
            for f in findings:
                f["file"] = file_path
            all_findings.extend(findings)
        except OSError:
            continue

    critical = sum(1 for f in all_findings if f.get("severity") == "critical")
    high = sum(1 for f in all_findings if f.get("severity") == "high")
    medium = sum(1 for f in all_findings if f.get("severity") == "medium")
    low = sum(1 for f in all_findings if f.get("severity") == "low")

    print(f"\n📊 Full Scan Results:")
    print(f"  Files: {len(kt_files)} | Total: {len(all_findings)}")
    print(f"  🔴 Critical: {critical} | 🟠 High: {high} | 🟡 Medium: {medium} | 🟢 Low: {low}")

    # Set GitHub commit status
    state = "failure" if critical + high > 0 else "success"
    desc = (
        f"Found {len(all_findings)} issues ({critical} critical, {high} high)"
        if all_findings else "No issues found ✅"
    )

    async with httpx.AsyncClient() as client:
        sha = os.environ.get("GITHUB_SHA", "")
        if sha:
            await client.post(
                f"{GITHUB_API}/repos/{REPO_OWNER}/{REPO_NAME}/statuses/{sha}",
                headers=github_headers(),
                json={
                    "state": state,
                    "description": desc[:140],
                    "context": "AI Code Review",
                },
            )
            print(f"  ✅ Commit status set: {state}")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if SCAN_MODE == "full":
        asyncio.run(run_full_scan())
    elif PR_NUMBER:
        asyncio.run(run_pr_review())
    else:
        print("❌ No PR_NUMBER set and SCAN_MODE is not 'full'. Nothing to do.")
        sys.exit(1)
