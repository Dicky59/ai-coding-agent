import { NextResponse } from "next/server";

const WORKFLOW_URL =
  "https://api.github.com/repos/Dicky59/ai-coding-agent/actions/workflows/scheduled-scan.yml/dispatches";

export async function POST(req: Request) {
  const token = process.env.GITHUB_TOKEN; // server-only, no NEXT_PUBLIC_
  if (!token) {
    return NextResponse.json({ error: "Server is missing GITHUB_TOKEN" }, { status: 500 });
  }

  const body = await req.json().catch(() => ({}));
  const inputs: Record<string, string> = {};
  for (const [k, v] of Object.entries(body.inputs ?? {})) {
    if (typeof v === "string") inputs[k] = v.slice(0, 300);
  }

  // Only allow plain GitHub repo URLs
  const repoUrl = Object.values(inputs).find((v) => v.includes("github.com"));
  if (repoUrl && !/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/.test(repoUrl)) {
    return NextResponse.json({ error: "Invalid repository URL" }, { status: 400 });
  }

  const res = await fetch(WORKFLOW_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ ref: "main", inputs }),
  });

  if (res.status !== 204) {
    return NextResponse.json({ error: `GitHub returned ${res.status}` }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}