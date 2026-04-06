"use client";

import { supabase } from "@/lib/supabase";
import { formatDate } from "@/lib/utils";
import Link from "next/link";
import { useEffect, useState } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Settings {
  id: number;
  weekly_scan_enabled: boolean;
  scan_day: string;
  scan_repos: string[];
  last_scan_at: string | null;
  next_scan_at: string | null;
  updated_at: string;
}

const AVAILABLE_REPOS = [
  { name: "DailyPulse",       language: "kotlin",     icon: "🤖" },
  { name: "next-store",       language: "typescript",  icon: "📘" },
  { name: "next-dicky",       language: "javascript",  icon: "💛" },
  { name: "spring-petclinic", language: "java",        icon: "☕" },
  { name: "coding-agent",     language: "python",      icon: "🐍" },
];

const DAYS = [
  { value: "monday",    label: "Monday"    },
  { value: "tuesday",   label: "Tuesday"   },
  { value: "wednesday", label: "Wednesday" },
  { value: "thursday",  label: "Thursday"  },
  { value: "friday",    label: "Friday"    },
];

const LANGUAGES = [
  { value: "auto",       label: "🔎 Auto-detect" },
  { value: "typescript", label: "📘 TypeScript"  },
  { value: "javascript", label: "💛 JavaScript"  },
  { value: "kotlin",     label: "🤖 Kotlin"      },
  { value: "java",       label: "☕ Java"         },
  { value: "python",     label: "🐍 Python"      },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isValidGitHubUrl(url: string): boolean {
  return /^https:\/\/github\.com\/[\w\-]+\/[\w\-\.]+\/?$/.test(url.trim());
}

async function triggerWorkflow(inputs: Record<string, string>): Promise<boolean> {
  const token = process.env.NEXT_PUBLIC_GITHUB_TOKEN || "";
  const resp = await fetch(
    "https://api.github.com/repos/Dicky59/coding-agent/actions/workflows/scheduled-scan.yml/dispatches",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    }
  );
  return resp.status === 204;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        enabled ? "bg-indigo-600" : "bg-slate-600"
      }`}
    >
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
        enabled ? "translate-x-6" : "translate-x-1"
      }`} />
    </button>
  );
}

function StatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
      enabled
        ? "bg-green-950 text-green-300 border border-green-800"
        : "bg-slate-700 text-slate-400 border border-slate-600"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${enabled ? "bg-green-400 animate-pulse" : "bg-slate-500"}`} />
      {enabled ? "Active" : "Paused"}
    </span>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Manual scan state
  const [triggering, setTriggering] = useState(false);
  const [triggerStatus, setTriggerStatus] = useState<"idle" | "success" | "error">("idle");

  // Custom repo scan state
  const [repoUrl, setRepoUrl] = useState("");
  const [repoLanguage, setRepoLanguage] = useState("auto");
  const [scanning, setScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState<"idle" | "success" | "error">("idle");
  const [scanError, setScanError] = useState("");

  useEffect(() => {
    async function fetchSettings() {
      const { data } = await supabase.from("settings").select("*").eq("id", 1).single();
      if (data) setSettings(data);
      setLoading(false);
    }
    fetchSettings();
  }, []);

  async function saveSettings(updates: Partial<Settings>) {
    if (!settings) return;
    setSaving(true);
    setSaved(false);
    const updated = { ...settings, ...updates, updated_at: new Date().toISOString() };
    setSettings(updated);
    await supabase.from("settings").update(updates).eq("id", 1);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function handleManualScan() {
    setTriggering(true);
    setTriggerStatus("idle");
    const ok = await triggerWorkflow({
      force: "true",
      repos: settings?.scan_repos.join(",") || "",
    });
    setTriggerStatus(ok ? "success" : "error");
    setTriggering(false);
  }

  async function handleCustomScan() {
    if (!isValidGitHubUrl(repoUrl)) {
      setScanError("Please enter a valid GitHub URL (e.g. https://github.com/owner/repo)");
      return;
    }
    setScanning(true);
    setScanStatus("idle");
    setScanError("");

    const ok = await triggerWorkflow({
      repo_url: repoUrl.trim(),
      repo_language: repoLanguage,
      force: "false",
    });

    if (ok) {
      setScanStatus("success");
      setRepoUrl("");
      setRepoLanguage("auto");
    } else {
      setScanStatus("error");
      setScanError("Could not trigger scan. Check that NEXT_PUBLIC_GITHUB_TOKEN is set.");
    }
    setScanning(false);
  }

  function toggleRepo(repoName: string) {
    if (!settings) return;
    const current = settings.scan_repos || [];
    const updated = current.includes(repoName)
      ? current.filter((r) => r !== repoName)
      : [...current, repoName];
    saveSettings({ scan_repos: updated });
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        <div className="text-center">
          <div className="text-3xl mb-3 animate-pulse">⚙️</div>
          <p>Loading settings...</p>
        </div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="text-center py-24">
        <div className="text-5xl mb-4">❌</div>
        <p className="text-slate-400">Could not load settings.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Settings</h1>
          <p className="text-slate-400 mt-1">Configure automated scans</p>
        </div>
        <Link href="/" className="text-indigo-400 hover:text-indigo-300 text-sm transition-colors">
          ← Dashboard
        </Link>
      </div>

      {/* ── Scan any GitHub repo ── */}
      <div className="bg-slate-800/50 border border-indigo-500/30 rounded-xl p-6 mb-4">
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-slate-200 font-semibold">🔍 Scan a GitHub Repository</h2>
          <span className="text-xs bg-indigo-900 text-indigo-300 px-2 py-0.5 rounded-full">New</span>
        </div>
        <p className="text-slate-400 text-sm mb-4">
          Paste any public GitHub repo URL and the AI will scan it for bugs, security issues, and code quality problems.
        </p>

        <div className="space-y-3">
          {/* URL input */}
          <div>
            <label className="text-slate-300 text-xs font-medium mb-1 block">
              GitHub Repository URL
            </label>
            <input
              type="url"
              value={repoUrl}
              onChange={(e) => {
                setRepoUrl(e.target.value);
                setScanStatus("idle");
                setScanError("");
              }}
              placeholder="https://github.com/owner/repository"
              className="w-full bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2.5 outline-none focus:border-indigo-500 placeholder-slate-600 transition-colors"
            />
            {scanError && (
              <p className="text-red-400 text-xs mt-1">{scanError}</p>
            )}
          </div>

          {/* Language selector */}
          <div>
            <label className="text-slate-300 text-xs font-medium mb-1 block">
              Language
            </label>
            <select
              value={repoLanguage}
              onChange={(e) => setRepoLanguage(e.target.value)}
              className="bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2.5 outline-none focus:border-indigo-500 w-full"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
            <p className="text-slate-500 text-xs mt-1">
              Auto-detect works for most repos — it checks for tsconfig.json, pom.xml, *.kt files etc.
            </p>
          </div>

          {/* Scan button */}
          <button
            onClick={handleCustomScan}
            disabled={scanning || !repoUrl.trim()}
            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors w-full justify-center"
          >
            {scanning ? (
              <>
                <span className="animate-spin">⏳</span>
                Triggering scan...
              </>
            ) : (
              <>🔍 Scan Repository</>
            )}
          </button>
        </div>

        {scanStatus === "success" && (
          <div className="mt-3 p-3 bg-green-950 border border-green-800 rounded-lg">
            <p className="text-green-300 text-sm font-medium">✅ Scan triggered successfully!</p>
            <p className="text-green-400/70 text-xs mt-1">
              The scan is running in GitHub Actions — it takes about 5-10 minutes.
              Results will appear on the{" "}
              <Link href="/" className="underline hover:text-green-300">dashboard</Link>{" "}
              automatically when complete.
            </p>
            <a
              href="https://github.com/Dicky59/coding-agent/actions"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-green-400 underline hover:text-green-300 mt-1"
            >
              Watch progress in GitHub Actions →
            </a>
          </div>
        )}
        {scanStatus === "error" && (
          <div className="mt-3 p-3 bg-red-950 border border-red-800 rounded-lg">
            <p className="text-red-300 text-sm">{scanError || "Scan failed — check GitHub Actions."}</p>
          </div>
        )}
      </div>

      {/* ── Weekly scan toggle ── */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6 mb-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-slate-200 font-semibold">Weekly Automatic Scan</h2>
            <p className="text-slate-400 text-sm mt-1">
              Automatically scan all configured repos on a schedule
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge enabled={settings.weekly_scan_enabled} />
            <Toggle
              enabled={settings.weekly_scan_enabled}
              onChange={(v) => saveSettings({ weekly_scan_enabled: v })}
            />
          </div>
        </div>

        {/* Scan day */}
        <div className="mt-4 pt-4 border-t border-slate-700">
          <label className="text-slate-300 text-sm font-medium">Scan day</label>
          <div className="flex gap-2 mt-2 flex-wrap">
            {DAYS.map((day) => (
              <button
                key={day.value}
                onClick={() => saveSettings({ scan_day: day.value })}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  settings.scan_day === day.value
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                }`}
              >
                {day.label}
              </button>
            ))}
          </div>
          <p className="text-slate-500 text-xs mt-2">Scans run at 8:00 AM UTC</p>
        </div>

        {/* Last / next scan */}
        <div className="mt-4 pt-4 border-t border-slate-700 grid grid-cols-2 gap-4">
          <div>
            <p className="text-slate-500 text-xs">Last scan</p>
            <p className="text-slate-300 text-sm mt-0.5">
              {settings.last_scan_at ? formatDate(settings.last_scan_at) : "Never"}
            </p>
          </div>
          <div>
            <p className="text-slate-500 text-xs">Next scan</p>
            <p className="text-slate-300 text-sm mt-0.5">
              {settings.weekly_scan_enabled
                ? settings.next_scan_at
                  ? formatDate(settings.next_scan_at)
                  : "Next Monday 8:00 AM UTC"
                : "Paused"}
            </p>
          </div>
        </div>
      </div>

      {/* ── Repos to scan ── */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6 mb-4">
        <h2 className="text-slate-200 font-semibold mb-1">Repos to Scan</h2>
        <p className="text-slate-400 text-sm mb-4">
          Choose which projects are included in automatic scans
        </p>
        <div className="space-y-2">
          {AVAILABLE_REPOS.map((repo) => {
            const enabled = settings.scan_repos?.includes(repo.name) ?? false;
            return (
              <div key={repo.name}
                className="flex items-center justify-between py-3 px-4 bg-slate-900/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <span className="text-xl">{repo.icon}</span>
                  <div>
                    <p className="text-slate-200 text-sm font-medium">{repo.name}</p>
                    <p className="text-slate-500 text-xs capitalize">{repo.language}</p>
                  </div>
                </div>
                <Toggle enabled={enabled} onChange={() => toggleRepo(repo.name)} />
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Manual scan ── */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6 mb-4">
        <h2 className="text-slate-200 font-semibold mb-1">Manual Scan</h2>
        <p className="text-slate-400 text-sm mb-4">
          Trigger a scan right now for all configured repos above.
        </p>
        <button
          onClick={handleManualScan}
          disabled={triggering}
          className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed text-slate-200 text-sm font-medium rounded-lg transition-colors"
        >
          {triggering ? <><span className="animate-spin">⏳</span> Triggering...</> : <>🔄 Run Scan Now</>}
        </button>

        {triggerStatus === "success" && (
          <div className="mt-3 flex items-center gap-2 text-green-400 text-sm">
            <span>✅ Scan triggered!</span>
            <a
              href="https://github.com/Dicky59/coding-agent/actions"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-green-300"
            >
              Watch in GitHub Actions →
            </a>
          </div>
        )}
        {triggerStatus === "error" && (
          <p className="mt-3 text-red-400 text-sm">
            ❌ Could not trigger scan. Check NEXT_PUBLIC_GITHUB_TOKEN in Vercel.
          </p>
        )}
      </div>

      {/* Save toast */}
      {(saving || saved) && (
        <div className={`fixed bottom-6 right-6 px-4 py-2 rounded-lg text-sm font-medium shadow-lg ${
          saved ? "bg-green-700 text-green-100" : "bg-slate-700 text-slate-200"
        }`}>
          {saving ? "💾 Saving..." : "✅ Saved!"}
        </div>
      )}
    </div>
  );
}
