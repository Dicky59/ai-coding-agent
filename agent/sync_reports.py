"""
sync_reports.py — Copy JSON reports to dashboard/public/reports/
Run this after any scan to update the dashboard with latest reports.

Usage:
    python sync_reports.py

Or add to reporter.py to run automatically after each scan.
"""

import json
import shutil
from pathlib import Path

def sync_reports():
    # Paths
    agent_dir = Path(__file__).parent
    reports_dir = agent_dir / "reports"
    dashboard_public = agent_dir.parent / "dashboard" / "public" / "reports"

    if not reports_dir.exists():
        print("⚠️  No reports/ folder found")
        return

    # Create destination
    dashboard_public.mkdir(parents=True, exist_ok=True)

    # Copy all JSON reports
    json_files = sorted(reports_dir.glob("*.json"))
    ids = []

    for src in json_files:
        dst = dashboard_public / src.name
        shutil.copy2(src, dst)
        ids.append(src.stem)  # filename without .json
        print(f"  ✅ Copied: {src.name}")

    # Write manifest
    manifest_path = dashboard_public / "manifest.json"
    manifest_path.write_text(
        json.dumps(ids, indent=2),
        encoding="utf-8",
    )
    print(f"\n  📋 Manifest updated: {len(ids)} reports")
    print(f"  📁 Destination: {dashboard_public}")


if __name__ == "__main__":
    print("🔄 Syncing reports to dashboard...")
    sync_reports()
    print("\n✅ Done! Commit and push to update Vercel.")
