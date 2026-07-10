# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI-powered code review platform. Scans repos across 5 languages via custom MCP servers, an
AI agent posts PR review comments and can auto-fix issues, results are stored in Supabase and
shown on a Next.js dashboard. Target languages being analyzed: Kotlin/Android, Java/Spring,
TypeScript/React, JavaScript, Python.

There is no test suite in this repo (no pytest/jest config) — verification is done by running
the CLI agents against a real target repo path.

## Architecture

Four layers, each a separate deployable unit:

```
dashboard/ (Next.js, Vercel)  --Supabase JS-->  Supabase (reports · findings · settings)
                                                        ^
agent/ (Python)  --httpx REST-->  Supabase             | stdio (MCP)
       |                                                |
       +--langchain-mcp-adapters-->  mcp-server/ (one stdio server per language)
```

- **mcp-server/**: one MCP stdio server per language (`server.py`=Kotlin, `server_java.py`,
  `server_typescript.py`, `server_javascript.py`, `server_python.py`). Each exposes tools like
  `analyze_*_bugs`/`get_repo_summary`/`search_code` that scan files with regex-based static
  analysis and return findings as JSON. **Never import agent code here** — these are standalone
  tool servers invoked over stdio.
- **agent/**: Python/LangGraph layer, one script per concern:
  - `agent.py` — Phase 1 repo-reader agent (LangGraph `StateGraph`, MCP tools bound to Claude);
    exposes `analyze_repo(repo_path, question)`, used by both the CLI and `api.py`.
  - `api.py` — FastAPI HTTP wrapper around `agent.py` for the `frontend/` chat UI (port 8000).
  - `bug_agent.py` / `java_agent.py` / `ts_agent.py` / `js_agent.py` / `py_agent.py` — per-language
    scanners that call the matching MCP server directly.
  - `multi_agent.py` — auto-detects languages in a repo and dispatches to the right scanner(s).
  - `fix_agent.py` / `fix_agent_ts.py` — read findings and generate/apply patches (interactive or
    `--auto`).
  - `pr_agent.py` — GitHub PR reviewer (posts inline review comments); runs inside a *target*
    repo's own `ai-review.yml` workflow, not in this repo.
  - `reporter.py` — shared module: renders the HTML report, writes JSON, upserts to Supabase
    (`reports`/`findings` tables), and syncs to `dashboard/public/reports/`.
  - `scheduled_scanner.py` / `github_action_runner.py` — orchestrators invoked by
    `.github/workflows/scheduled-scan.yml` (weekly cron + manual dispatch, including scanning an
    arbitrary `repo_url` passed in from the dashboard Settings page).
- **dashboard/**: Next.js 15 app (`app/page.tsx` reports home, `app/trends`, `app/settings`,
  `app/reports/[id]`) reading/writing Supabase directly via `lib/supabase.ts`. This is the
  deployed product (ai-coding-agent-five.vercel.app).
- **frontend/**: separate, early-stage Vite/React chat UI ("Phase 1 · Repo Reader") that talks to
  `agent/api.py` at `localhost:8000` — not the dashboard, a different prototype for the
  agent.py Q&A flow.

## Python style (agent/, mcp-server/)

- Always use type hints; Pydantic models for API/report contracts (see `reporter.py`, `api.py`).
- Prefer async/await throughout the agent layer.
- FastAPI dependency injection over global state in `api.py`.
- No business logic in `api.py` — it only calls into `agent.py`.
- No synchronous file I/O inside async functions.
- No hardcoded API keys — everything comes from `agent/.env` (`ANTHROPIC_API_KEY`,
  `GITHUB_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`) via `python-dotenv`.

## LangGraph patterns (agent/agent.py)

- `AgentState` is a `TypedDict` with `Annotated` fields (e.g. `messages: Annotated[list[BaseMessage], add_messages]`).
- Graph nodes are pure functions: `(state) -> partial state update`.
- Tools are loaded at runtime from the MCP server via `langchain-mcp-adapters`
  (`MultiServerMCPClient`), not hardcoded — new MCP tools become available to the agent
  automatically.

## Commands

### Python agent (run from `agent/`)

```bash
uv venv
source .venv/Scripts/activate   # Windows Git Bash; .venv/bin/activate on Mac/Linux
uv pip install -r requirements.txt
```

Requires `agent/.env` with `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`.

```bash
python bug_agent.py <repo_path>         # Kotlin/Android
python java_agent.py <repo_path>        # Java/Spring
python ts_agent.py <repo_path>          # TypeScript/React
python js_agent.py <repo_path>          # JavaScript
python py_agent.py <repo_path>          # Python
python multi_agent.py <repo_path>       # auto-detect language(s)

python fix_agent_ts.py <repo_path> [--auto] [--severity high]   # TS/JS fixer
python fix_agent.py <repo_path> --findings bugs.json            # Kotlin fixer

python agent.py <repo_path> "<question>"    # ask a question about a repo (CLI)
python api.py                               # serve agent.py over HTTP on :8000
```

### Dashboard (run from `dashboard/`)

```bash
npm install
npm run dev     # http://localhost:3333 (custom port)
npm run build
npm run lint
```

Requires `dashboard/.env.local` with `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_KEY`,
`NEXT_PUBLIC_GITHUB_TOKEN`.

### frontend/ (Phase 1 chat prototype)

Talks to `agent/api.py` on `localhost:8000`; run the FastAPI server first, then the Vite dev
server from `frontend/`.

## Supabase schema

Three tables: `reports` (one row per scan run, per repo/language), `findings` (FK to
`report_id`, one row per issue with file/line/severity/category/suggested_fix), `settings`
(single row, id=1 — controls weekly scan on/off, scan day, and `scan_repos` array used by
`scheduled_scanner.py`). Full `create table` DDL is in the root `README.md`.
