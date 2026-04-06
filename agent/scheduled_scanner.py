"""
Scheduled Scanner — runs in GitHub Actions
Checks Supabase settings before scanning.
If weekly_scan_enabled=false, exits early (scan is "paused").

The individual scan agents (ts_agent, js_agent, etc.) already save
to Supabase via reporter.py — this script just orchestrates them.

Environment variables needed:
  ANTHROPIC_API_KEY
  SUPABASE_URL
  SUPABASE_KEY
  FORCE_SCAN=true/false   (override the enabled flag)
  OVERRIDE_REPOS=repo1,repo2  (override configured repos)
  SCAN_MODE=scheduled|manual
"""

import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FORCE_SCAN = os.environ.get("FORCE_SCAN", "false").lower() == "true"
OVERRIDE_REPOS = os.environ.get("OVERRIDE_REPOS", "").strip()
SCAN_MODE = os.environ.get("SCAN_MODE", "scheduled")


# ─── Supabase helpers ─────────────────────────────────────────────────────────

def supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def get_settings() -> dict | None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/settings",
            headers=supabase_headers(),
            params={"id": "eq.1", "select": "*"},
        )
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
        return None


async def update_scan_timestamps() -> None:
    now = datetime.now(timezone.utc)
    days_until_monday = (7 - now.weekday()) % 7 or 7
    next_monday = (now + timedelta(days=days_until_monday)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/settings",
            headers=supabase_headers(),
            params={"id": "eq.1"},
            json={
                "last_scan_at": now.isoformat(),
                "next_scan_at": next_monday.isoformat(),
                "updated_at": now.isoformat(),
            },
        )
    print(f"  ✅ Next scan: {next_monday.strftime('%Y-%m-%d %H:%M UTC')}")


# ─── Repo config ──────────────────────────────────────────────────────────────

REPO_CONFIG = {
    "DailyPulse": (
        "/tmp/repos/DailyPulse",
        "kotlin",
        "https://github.com/Dicky59/daily-pulse",
    ),
    "next-store": (
        "/tmp/repos/next-store",
        "typescript",
        "https://github.com/Dicky59/next-store",
    ),
    "next-dicky": (
        "/tmp/repos/next-dicky",
        "javascript",
        "https://github.com/Dicky59/next-dicky",
    ),
    "spring-petclinic": (
        "/tmp/repos/spring-petclinic",
        "java",
        "https://github.com/spring-projects/spring-petclinic",
    ),
    "coding-agent": (
        "/tmp/repos/coding-agent",
        "python",
        "https://github.com/Dicky59/ai-coding-agent",
    ),
}


# ─── Git clone ────────────────────────────────────────────────────────────────

async def clone_repo(name: str, url: str, path: str) -> bool:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if Path(path).exists():
        print(f"  📁 Already cloned: {name}")
        return True
    print(f"  📥 Cloning {name}...")
    result = subprocess.run(
        ["git", "clone", "--depth=1", url, path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ❌ Clone failed: {result.stderr[:200]}")
        return False
    print(f"  ✅ Cloned: {name}")
    return True


# ─── Scan functions ───────────────────────────────────────────────────────────
# Each agent's scan_repo() already calls reporter.py which saves to Supabase.
# We just call the agent — no duplicate saving needed here.

async def scan_kotlin_repo(repo_path: str, repo_name: str) -> bool:
    print(f"\n  🤖 Scanning Kotlin: {repo_name}")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from bug_agent import scan_repo as kotlin_scan
        report = await kotlin_scan(repo_path)
        print(f"  ✅ Kotlin: {report.total_findings} findings")
        return True
    except Exception as e:
        print(f"  ❌ Kotlin failed: {e}")
        return False


async def scan_typescript_repo(repo_path: str, repo_name: str) -> bool:
    print(f"\n  📘 Scanning TypeScript: {repo_name}")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from ts_agent import scan_repo as ts_scan
        report = await ts_scan(repo_path)
        print(f"  ✅ TypeScript: {report.total_findings} findings")
        return True
    except Exception as e:
        print(f"  ❌ TypeScript failed: {e}")
        return False


async def scan_javascript_repo(repo_path: str, repo_name: str) -> bool:
    print(f"\n  💛 Scanning JavaScript: {repo_name}")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from js_agent import scan_repo as js_scan
        report = await js_scan(repo_path)
        print(f"  ✅ JavaScript: {report.total_findings} findings")
        return True
    except Exception as e:
        print(f"  ❌ JavaScript failed: {e}")
        return False


async def scan_java_repo(repo_path: str, repo_name: str) -> bool:
    print(f"\n  ☕ Scanning Java: {repo_name}")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from java_agent import scan_repo as java_scan
        report = await java_scan(repo_path)
        print(f"  ✅ Java: {report.total_findings} findings")
        return True
    except Exception as e:
        print(f"  ❌ Java failed: {e}")
        return False


async def scan_python_repo(repo_path: str, repo_name: str) -> bool:
    print(f"\n  🐍 Scanning Python: {repo_name}")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from py_agent import scan_repo as py_scan
        report = await py_scan(f"{repo_path}/agent")
        print(f"  ✅ Python: {report.total_findings} findings")
        return True
    except Exception as e:
        print(f"  ❌ Python failed: {e}")
        return False


SCAN_FUNCTIONS = {
    "kotlin":     scan_kotlin_repo,
    "typescript": scan_typescript_repo,
    "javascript": scan_javascript_repo,
    "java":       scan_java_repo,
    "python":     scan_python_repo,
}


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{'═' * 60}")
    print(f"  🤖 AI CODING AGENT — SCHEDULED SCAN")
    print(f"  Mode: {SCAN_MODE}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'═' * 60}")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ SUPABASE_URL and SUPABASE_KEY required")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY required")
        sys.exit(1)

    # Check settings
    print("\n📋 Checking Supabase settings...")
    settings = await get_settings()
    if not settings:
        print("❌ Could not fetch settings")
        sys.exit(1)

    weekly_enabled = settings.get("weekly_scan_enabled", True)
    configured_repos = settings.get("scan_repos", list(REPO_CONFIG.keys()))

    print(f"  Weekly scan enabled: {weekly_enabled}")
    print(f"  Configured repos:    {configured_repos}")

    # Check if enabled
    if not weekly_enabled and not FORCE_SCAN:
        print("\n⏸️  Weekly scan is DISABLED in dashboard settings.")
        print("   Toggle it on in ⚙️ Settings or use force=true.")
        sys.exit(0)

    if FORCE_SCAN:
        print("  ⚡ Force scan — ignoring enabled flag")

    # Which repos to scan
    if OVERRIDE_REPOS:
        repos_to_scan = [r.strip() for r in OVERRIDE_REPOS.split(",") if r.strip()]
        print(f"\n  Override repos: {repos_to_scan}")
    else:
        repos_to_scan = [r for r in configured_repos if r in REPO_CONFIG]
        print(f"\n  Repos to scan: {repos_to_scan}")

    if not repos_to_scan:
        print("⚠️  No repos to scan!")
        sys.exit(0)

    # Clone and scan each repo
    results = []
    start_time = time.time()

    for repo_name in repos_to_scan:
        if repo_name not in REPO_CONFIG:
            print(f"\n  ⚠️  Unknown repo: {repo_name} — skipping")
            continue

        repo_path, language, clone_url = REPO_CONFIG[repo_name]

        cloned = await clone_repo(repo_name, clone_url, repo_path)
        if not cloned:
            results.append({"repo": repo_name, "status": "clone_failed"})
            continue

        scan_fn = SCAN_FUNCTIONS.get(language)
        if not scan_fn:
            print(f"  ⚠️  No scanner for: {language}")
            continue

        success = await scan_fn(repo_path, repo_name)
        results.append({
            "repo": repo_name,
            "status": "success" if success else "error",
            "language": language,
        })

        await asyncio.sleep(5)  # avoid rate limiting between scans

    # Update timestamps
    print(f"\n  📅 Updating timestamps...")
    await update_scan_timestamps()

    # Summary
    elapsed = round(time.time() - start_time, 1)
    print(f"\n{'═' * 60}")
    print(f"  ✅ COMPLETE ({elapsed}s)")
    print(f"{'═' * 60}")
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {icon} {r['repo']} [{r.get('language', '?')}]: {r['status']}")

    failed = [r for r in results if r["status"] != "success"]
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
