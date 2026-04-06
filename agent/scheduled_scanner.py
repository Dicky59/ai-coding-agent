"""
Scheduled Scanner — runs in GitHub Actions
Checks Supabase settings before scanning.
If weekly_scan_enabled=false, exits early (scan is "paused").

Supports:
- Weekly scheduled scans of configured repos
- Manual trigger of configured repos
- Custom repo URL scan (REPO_URL env var)

Environment variables needed:
  ANTHROPIC_API_KEY
  SUPABASE_URL
  SUPABASE_KEY
  FORCE_SCAN=true/false
  OVERRIDE_REPOS=repo1,repo2
  SCAN_MODE=scheduled|manual
  REPO_URL=https://github.com/user/repo   (custom repo scan)
  REPO_LANGUAGE=auto|kotlin|java|typescript|javascript|python
"""

import asyncio
import os
import re
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
REPO_URL = os.environ.get("REPO_URL", "").strip()
REPO_LANGUAGE = os.environ.get("REPO_LANGUAGE", "auto").strip().lower()


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


# ─── Language detection ───────────────────────────────────────────────────────

def detect_language(repo_path: str) -> str:
    """Auto-detect the primary language of a repository."""
    path = Path(repo_path)

    # Priority rules — check for definitive files first
    if (path / "AndroidManifest.xml").exists():
        return "kotlin"
    if list(path.rglob("*.kt")):
        return "kotlin"
    if (path / "pom.xml").exists():
        return "java"
    if (path / "tsconfig.json").exists():
        return "typescript"

    # Count files per language
    py_files = [f for f in path.rglob("*.py")
                if not any(p in str(f) for p in ["__pycache__", ".venv", "venv"])]
    js_files = [f for f in path.rglob("*.js")
                if "node_modules" not in str(f)]
    java_files = list(path.rglob("*.java"))

    if len(java_files) > 5:
        return "java"
    if len(py_files) > 5:
        return "python"
    if len(js_files) > 5:
        return "javascript"

    return "typescript"  # default for web projects


def extract_repo_name_from_url(url: str) -> str:
    """Extract repo name from GitHub URL."""
    match = re.search(r'github\.com/[\w\-]+/([\w\-\.]+?)(?:\.git)?$', url.strip())
    if match:
        return match.group(1)
    return url.rstrip("/").split("/")[-1].replace(".git", "")


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
        "https://github.com/Dicky59/coding-agent",
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
        scan_path = f"{repo_path}/agent" if repo_name == "coding-agent" else repo_path
        report = await py_scan(scan_path)
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


# ─── Custom repo scan ─────────────────────────────────────────────────────────

async def scan_custom_repo(repo_url: str, language: str) -> bool:
    """Clone and scan a repo from a URL provided by the user."""
    repo_name = extract_repo_name_from_url(repo_url)
    repo_path = f"/tmp/repos/custom/{repo_name}"

    print(f"\n  🔍 Custom scan: {repo_name}")
    print(f"  📌 URL: {repo_url}")

    cloned = await clone_repo(repo_name, repo_url, repo_path)
    if not cloned:
        return False

    if language == "auto":
        language = detect_language(repo_path)
        print(f"  🔎 Auto-detected: {language}")

    scan_fn = SCAN_FUNCTIONS.get(language)
    if not scan_fn:
        print(f"  ❌ No scanner for: {language}")
        print(f"  Supported: {list(SCAN_FUNCTIONS.keys())}")
        return False

    return await scan_fn(repo_path, repo_name)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{'═' * 60}")
    print(f"  🤖 AI CODING AGENT — SCAN")
    print(f"  Mode: {SCAN_MODE}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  REPO_URL env: '{REPO_URL}'")
    print(f"  REPO_LANGUAGE env: '{REPO_LANGUAGE}'")
    print(f"  FORCE_SCAN env: '{FORCE_SCAN}'")
    if REPO_URL:
        print(f"  Custom URL: {REPO_URL}")
    print(f"{'═' * 60}")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ SUPABASE_URL and SUPABASE_KEY required")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY required")
        sys.exit(1)

    # ── Custom repo scan mode ──
    if REPO_URL:
        print(f"\n🔍 Custom repo scan")
        success = await scan_custom_repo(REPO_URL, REPO_LANGUAGE)
        if success:
            print(f"\n✅ Scan complete — check dashboard for results!")
        else:
            print(f"\n❌ Scan failed")
            sys.exit(1)
        return

    # ── Regular scheduled/manual scan ──
    print("\n📋 Checking Supabase settings...")
    settings = await get_settings()
    if not settings:
        print("❌ Could not fetch settings")
        sys.exit(1)

    weekly_enabled = settings.get("weekly_scan_enabled", True)
    configured_repos = settings.get("scan_repos", list(REPO_CONFIG.keys()))

    print(f"  Weekly scan enabled: {weekly_enabled}")
    print(f"  Configured repos:    {configured_repos}")

    if not weekly_enabled and not FORCE_SCAN:
        print("\n⏸️  Weekly scan is DISABLED.")
        print("   Toggle it on in ⚙️ Settings or use force=true.")
        sys.exit(0)

    if FORCE_SCAN:
        print("  ⚡ Force scan")

    if OVERRIDE_REPOS:
        repos_to_scan = [r.strip() for r in OVERRIDE_REPOS.split(",") if r.strip()]
        print(f"\n  Override repos: {repos_to_scan}")
    else:
        repos_to_scan = [r for r in configured_repos if r in REPO_CONFIG]
        print(f"\n  Repos to scan: {repos_to_scan}")

    if not repos_to_scan:
        print("⚠️  No repos to scan!")
        sys.exit(0)

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
            continue

        success = await scan_fn(repo_path, repo_name)
        results.append({
            "repo": repo_name,
            "status": "success" if success else "error",
            "language": language,
        })

        await asyncio.sleep(5)

    print(f"\n  📅 Updating timestamps...")
    await update_scan_timestamps()

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
