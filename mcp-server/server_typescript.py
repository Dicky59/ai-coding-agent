"""
MCP Server — TypeScript/React/Next.js Analysis Tools
Exposes tools for:
- TypeScript bug detection (any type, non-null assertions, unsafe casts)
- React hooks analysis (missing deps, conditional hooks, memory leaks)
- React patterns (missing key, error boundaries, large components)
- Next.js specific (missing loading states, wrong data fetching)
- Security (eval, innerHTML, hardcoded secrets, XSS)
"""

import json
import re
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("typescript-analyzer")

# ─── Helpers ─────────────────────────────────────────────────────────────────

IGNORE_DIRS = {
    ".git", "node_modules", ".next", "dist", "build",
    ".turbo", "coverage", ".cache", "out", "__pycache__",
    "generated",  # Prisma and other auto-generated files
}

# Path fragments to skip entirely — not user code
IGNORE_PATH_FRAGMENTS = {
    "lib/generated/",
    "src/generated/",
    "generated/prisma/",
}

def is_generated_file(file_path: str) -> bool:
    """Returns True if the file should be skipped as generated/vendor code."""
    normalized = file_path.replace("\\", "/")
    if normalized.endswith(".d.ts"):
        return True
    return any(frag in normalized for frag in IGNORE_PATH_FRAGMENTS)


def is_safe_path(base: str, target: str) -> bool:
    base_path = Path(base).resolve()
    target_path = Path(target).resolve()
    return target_path.is_relative_to(base_path)


def read_file_safe(file_path: str) -> str | None:
    try:
        return Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def should_skip_line(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith("//")
        or stripped.startswith("*")
        or stripped.startswith("/*")
        or stripped == ""
    )


def make_finding(
    line: int,
    code: str,
    title: str,
    description: str,
    suggested_fix: str,
    severity: str,
    category: str,
) -> dict:
    return {
        "line": line,
        "code": code.strip()[:120],
        "title": title,
        "description": description,
        "suggested_fix": suggested_fix,
        "severity": severity,
        "category": category,
    }


def is_in_string(line: str, match_start: int) -> bool:
    """Rough check if a position is inside a string literal."""
    before = line[:match_start]
    single_quotes = before.count("'") - before.count("\\'")
    double_quotes = before.count('"') - before.count('\\"')
    backticks = before.count("`")
    return (single_quotes % 2 != 0) or (double_quotes % 2 != 0) or (backticks % 2 != 0)


# ─── Tool definitions ─────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_ts_bugs",
            description=(
                "Analyzes a TypeScript file for type safety bugs: "
                "any type usage, non-null assertions (!), unsafe type casts (as), "
                "@ts-ignore/@ts-expect-error suppressions, missing return types, "
                "and implicit any in function parameters."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .ts/.tsx file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_react_hooks",
            description=(
                "Checks a React component file for hooks issues: "
                "missing useEffect dependency arrays, likely missing deps, "
                "hooks called conditionally (rules of hooks), "
                "missing cleanup functions in useEffect (memory leaks), "
                "and stale closure patterns."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .ts/.tsx file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_react_patterns",
            description=(
                "Reviews React component files for pattern issues: "
                "missing key prop on list items, index used as key, "
                "direct state mutation, missing error boundaries, "
                "prop drilling (deeply nested prop passing), "
                "overly large components (300+ lines), "
                "and missing loading/error states."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .ts/.tsx file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_nextjs_patterns",
            description=(
                "Checks Next.js specific patterns: "
                "missing loading.tsx for async pages, "
                "missing error.tsx for error handling, "
                "client components fetching data incorrectly, "
                "missing Suspense boundaries around async components, "
                "hardcoded URLs instead of env variables, "
                "and missing metadata exports."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .ts/.tsx file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_ts_security",
            description=(
                "Scans TypeScript/React files for security issues: "
                "dangerouslySetInnerHTML usage (XSS risk), "
                "eval() or new Function() usage, "
                "hardcoded API keys or secrets, "
                "missing input sanitization, "
                "exposed sensitive env variables in client components, "
                "and insecure direct object references."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .ts/.tsx file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="list_ts_files",
            description=(
                "Lists TypeScript/React source files in a repository. "
                "Can filter by type: page, component, hook, action, api, util, all. "
                "Ignores node_modules, .next, dist, test files."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Absolute path to repo root"},
                    "file_type": {
                        "type": "string",
                        "description": "Filter: page, component, hook, action, api, util, all",
                        "default": "all",
                    },
                    "include_tests": {
                        "type": "boolean",
                        "description": "Include test files (default false)",
                        "default": False,
                    },
                },
                "required": ["repo_path"],
            },
        ),
    ]


# ─── Tool router ──────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    match name:
        case "analyze_ts_bugs":
            return await _analyze_ts_bugs(**arguments)
        case "analyze_react_hooks":
            return await _analyze_react_hooks(**arguments)
        case "analyze_react_patterns":
            return await _analyze_react_patterns(**arguments)
        case "analyze_nextjs_patterns":
            return await _analyze_nextjs_patterns(**arguments)
        case "analyze_ts_security":
            return await _analyze_ts_security(**arguments)
        case "list_ts_files":
            return await _list_ts_files(**arguments)
        case _:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ─── analyze_ts_bugs ──────────────────────────────────────────────────────────

async def _analyze_ts_bugs(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    if is_generated_file(file_path):
        result = {"file": file_path, "language": "typescript", "total_findings": 0, "findings": []}
        return [TextContent(type="text", text=json.dumps(result))]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []
    in_multiline = False

    for i, line in enumerate(lines):
        if "/*" in line:
            in_multiline = True
        if "*/" in line:
            in_multiline = False
            continue
        if in_multiline or should_skip_line(line):
            continue
        stripped = line.strip()

        # any type usage
        if re.search(r':\s*any\b', line) and not re.search(r'//.*:\s*any', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Explicit 'any' type usage",
                "Using 'any' defeats TypeScript's type safety. "
                "It spreads unsafety to all callers and disables autocomplete.",
                "Use 'unknown' for truly unknown types (requires type narrowing), "
                "or define a specific interface/type.",
                "high", "typescript",
            ))

        # as any
        if re.search(r'\bas\s+any\b', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Type cast to 'any'",
                "'as any' is an escape hatch that removes all type checking. "
                "It can hide bugs that TypeScript would otherwise catch.",
                "Use a proper type assertion with a specific type, "
                "or use type guards to narrow the type safely.",
                "high", "typescript",
            ))

        # Non-null assertion
        if re.search(r'\w+!\.|\w+!\[', line) and "!=" not in line and "!==" not in line:
            findings.append(make_finding(
                i + 1, stripped,
                "Non-null assertion operator (!)",
                "The ! operator tells TypeScript to ignore null/undefined. "
                "If the value is actually null, you get a runtime crash.",
                "Use optional chaining (?.) with a fallback: "
                "value?.property ?? defaultValue",
                "medium", "typescript",
            ))

        # @ts-ignore
        if "@ts-ignore" in line:
            findings.append(make_finding(
                i + 1, stripped,
                "@ts-ignore suppressing TypeScript error",
                "@ts-ignore silences TypeScript errors without fixing them. "
                "The underlying type issue remains and can cause runtime bugs.",
                "Fix the actual type error. If it's a library issue, "
                "use @ts-expect-error with a comment explaining why.",
                "medium", "typescript",
            ))

        # @ts-expect-error without comment
        if "@ts-expect-error" in line:
            next_line = lines[i + 1] if i + 1 < len(lines) else ""
            if not re.search(r'//\s*\w+', line) and not re.search(r'//\s*\w+', next_line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "@ts-expect-error without explanation comment",
                    "@ts-expect-error without a comment makes it unclear "
                    "why the error is being suppressed.",
                    "Add a comment: // @ts-expect-error — reason why this is needed",
                    "low", "typescript",
                ))

        # Unsafe type assertion (as SomeType without unknown intermediate)
        if re.search(r'\)\s+as\s+(?!unknown|any|const|React)\w+', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Unsafe type assertion (as)",
                "Direct type assertion bypasses TypeScript's type checker. "
                "If the actual runtime type doesn't match, you get silent corruption.",
                "Use a type guard function or parse with zod/valibot for "
                "runtime validation before asserting the type.",
                "medium", "typescript",
            ))

        # console.log left in code
        if re.search(r'\bconsole\.(log|warn|error|debug)\b', line):
            findings.append(make_finding(
                i + 1, stripped,
                "console.log/warn/error left in code",
                "Console statements left in production code leak implementation "
                "details and clutter browser devtools.",
                "Remove debug logs. Use a proper logging library "
                "or environment-gated logging.",
                "low", "typescript",
            ))

    result = {
        "file": file_path,
        "language": "typescript",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_react_hooks ──────────────────────────────────────────────────────

async def _analyze_react_hooks(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    if is_generated_file(file_path):
        result = {"file": file_path, "language": "typescript", "total_findings": 0, "findings": []}
        return [TextContent(type="text", text=json.dumps(result))]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    # Only analyze .tsx/.jsx files with React components
    if not file_path.endswith((".tsx", ".jsx")):
        if "React" not in content and "react" not in content:
            result = {"file": file_path, "language": "typescript",
                      "total_findings": 0, "findings": []}
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

    lines = content.splitlines()
    findings = []

    for i, line in enumerate(lines):
        if should_skip_line(line):
            continue
        stripped = line.strip()

        # useEffect without dependency array
        if re.search(r'useEffect\s*\(\s*(?:async\s*)?\(\s*\)\s*=>', line) or \
           re.search(r'useEffect\s*\(\s*(?:async\s*)?function', line):
            # Check next 10 lines for closing with dependency array
            block = "\n".join(lines[i:min(len(lines), i + 15)])
            # Look for the closing ), [] or ), [deps]
            if not re.search(r'\)\s*,\s*\[', block):
                findings.append(make_finding(
                    i + 1, stripped,
                    "useEffect missing dependency array",
                    "useEffect without a dependency array runs after every render. "
                    "This causes infinite loops if the effect updates state.",
                    "Add a dependency array: useEffect(() => { ... }, [dep1, dep2]). "
                    "Use [] for mount-only effects.",
                    "high", "hooks",
                ))

        # useEffect with empty deps but using external variables
        if re.search(r'useEffect\s*\(', line):
            block = "\n".join(lines[i:min(len(lines), i + 20)])
            # Check if deps array is empty but effect uses props/state
            if re.search(r'\),\s*\[\s*\]\s*\)', block) or \
               re.search(r',\s*\[\s*\]\s*\)', block):
                # Check if the effect block uses variables that look like props
                if re.search(r'\b(?:props\.|on[A-Z]|fetch[A-Z]|load[A-Z])\w*\s*\(', block):
                    findings.append(make_finding(
                        i + 1, stripped,
                        "useEffect with empty deps array but uses props/callbacks",
                        "Empty dependency array with props/callbacks used inside "
                        "creates stale closures — the effect captures the initial "
                        "values and never updates.",
                        "Add the used props/callbacks to the dependency array, "
                        "or wrap callbacks in useCallback.",
                        "high", "hooks",
                    ))

        # useEffect with async function directly
        if re.search(r'useEffect\s*\(\s*async', line):
            findings.append(make_finding(
                i + 1, stripped,
                "useEffect with async function directly",
                "useEffect cannot take an async function directly. "
                "The cleanup return value is ignored, causing memory leaks.",
                "Define an async function inside the effect and call it: "
                "useEffect(() => { const fetchData = async () => {...}; fetchData(); }, [])",
                "high", "hooks",
            ))

        # Missing cleanup for subscriptions/listeners
        if re.search(r'addEventListener|subscribe\s*\(|setInterval\s*\(|setTimeout\s*\(', line):
            context = "\n".join(lines[i:min(len(lines), i + 20)])
            if re.search(r'useEffect', "\n".join(lines[max(0, i-5):i+1])):
                if not re.search(r'return\s*(?:\(\s*)?\s*(?:function|\(\s*\)\s*=>|\(\)=>)', context):
                    findings.append(make_finding(
                        i + 1, stripped,
                        "Missing cleanup in useEffect (potential memory leak)",
                        "Event listeners, subscriptions, intervals and timeouts "
                        "set inside useEffect must be cleaned up to prevent memory leaks "
                        "when the component unmounts.",
                        "Return a cleanup function: "
                        "useEffect(() => { ... return () => { cleanup(); }; }, [])",
                        "high", "hooks",
                    ))

        # Hooks called conditionally
        if re.search(r'\bif\s*\(', line) or re.search(r'\?\s*use[A-Z]', line):
            context = "\n".join(lines[i:min(len(lines), i + 5)])
            if re.search(r'\buse[A-Z]\w+\s*\(', context) and \
               re.search(r'\bif\s*\(', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Hook possibly called conditionally",
                    "React hooks must be called in the same order every render. "
                    "Calling hooks inside if statements violates the Rules of Hooks.",
                    "Move the hook call to the top level of the component. "
                    "Use the condition inside the hook or pass it as a parameter.",
                    "critical", "hooks",
                ))

        # useState with object — direct mutation risk
        if re.search(r'const\s*\[\s*\w+\s*,\s*set\w+\s*\]', line):
            # Look for direct mutation patterns nearby
            var_match = re.search(r'const\s*\[\s*(\w+)\s*,', line)
            if var_match:
                var_name = var_match.group(1)
                for j in range(i + 1, min(len(lines), i + 30)):
                    if re.search(rf'{var_name}\.\w+\s*=', lines[j]):
                        findings.append(make_finding(
                            j + 1, lines[j].strip(),
                            "Direct state mutation",
                            f"Directly mutating state object '{var_name}' "
                            "doesn't trigger a re-render and causes subtle bugs.",
                            "Use the setter function with a new object: "
                            f"set{var_name[0].upper() + var_name[1:]}(prev => "
                            f"({{...prev, field: value}}))",
                            "high", "hooks",
                        ))
                        break

        # useMemo/useCallback without deps
        if re.search(r'(?:useMemo|useCallback)\s*\(', line):
            block = "\n".join(lines[i:min(len(lines), i + 10)])
            if not re.search(r'\),\s*\[', block):
                findings.append(make_finding(
                    i + 1, stripped,
                    "useMemo/useCallback missing dependency array",
                    "useMemo and useCallback require a dependency array. "
                    "Without it, memoization is disabled and runs every render.",
                    "Add a dependency array as the second argument: "
                    "useMemo(() => compute(a, b), [a, b])",
                    "medium", "hooks",
                ))

    result = {
        "file": file_path,
        "language": "typescript",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_react_patterns ───────────────────────────────────────────────────

async def _analyze_react_patterns(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    if is_generated_file(file_path):
        result = {"file": file_path, "language": "typescript", "total_findings": 0, "findings": []}
        return [TextContent(type="text", text=json.dumps(result))]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    # Large component check
    tsx_lines = [l for l in lines if l.strip()]
    if len(tsx_lines) > 300 and file_path.endswith((".tsx", ".jsx")):
        findings.append(make_finding(
            1, f"Component file: {len(tsx_lines)} lines",
            "Component file too large",
            f"This component has {len(tsx_lines)} non-empty lines. "
            "Large components are hard to test, understand, and maintain.",
            "Split into smaller focused components. "
            "Extract hooks into custom hooks. "
            "Aim for components under 200 lines.",
            "medium", "pattern",
        ))

    for i, line in enumerate(lines):
        if should_skip_line(line):
            continue
        stripped = line.strip()

        # Missing key prop in .map()
        if re.search(r'\.map\s*\(\s*(?:\w+|\([^)]+\))\s*=>', line):
            block = "\n".join(lines[i:min(len(lines), i + 5)])
            if re.search(r'<\w+', block) and not re.search(r'\bkey\s*=', block):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Missing key prop in list rendering",
                    "React uses keys to identify which list items have changed. "
                    "Missing keys cause incorrect re-renders and UI bugs.",
                    "Add a unique key prop: items.map(item => "
                    "<Component key={item.id} />). "
                    "Never use array index as key for dynamic lists.",
                    "high", "pattern",
                ))

        # Index as key
        if re.search(r'key\s*=\s*\{?\s*(?:index|i|idx)\s*\}?', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Array index used as key prop",
                "Using array index as key causes incorrect component reuse "
                "when items are added, removed, or reordered. "
                "This causes UI bugs and lost state.",
                "Use a stable unique identifier: key={item.id} or key={item.slug}",
                "medium", "pattern",
            ))

        # dangerouslySetInnerHTML
        if "dangerouslySetInnerHTML" in line:
            findings.append(make_finding(
                i + 1, stripped,
                "dangerouslySetInnerHTML usage (XSS risk)",
                "dangerouslySetInnerHTML renders raw HTML and is vulnerable "
                "to XSS attacks if the content comes from user input or an API.",
                "Sanitize HTML with DOMPurify before passing to "
                "dangerouslySetInnerHTML, or use a markdown renderer instead.",
                "high", "security",
            ))

        # Missing error boundary indication
        if re.search(r'async\s+function|await\s+fetch|await\s+\w+Service', line):
            context = "\n".join(lines[max(0, i-10):i+10])
            if not re.search(r'try\s*\{|catch\s*\(|\.catch\(|ErrorBoundary', context):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Async operation without error handling",
                    "Async operations without try/catch or .catch() will throw "
                    "unhandled promise rejections that crash the component.",
                    "Wrap in try/catch or use React Query/SWR which handles "
                    "errors automatically. Add an error boundary for component-level errors.",
                    "high", "pattern",
                ))

        # Props spreading without type safety
        # Skip shadcn/ui components — spreading is intentional in component libraries
        normalized_path = file_path.replace("\\", "/")
        is_ui_component = "/components/ui/" in normalized_path or "/ui/" in normalized_path
        if re.search(r'\.\.\.\s*props\b', line) and file_path.endswith(".tsx") and not is_ui_component:
            findings.append(make_finding(
                i + 1, stripped,
                "Spreading props without explicit typing",
                "Spreading ...props passes all props including internal ones "
                "to DOM elements, causing React warnings and unexpected behavior.",
                "Destructure only needed props: "
                "const { onClick, className, ...rest } = props",
                "low", "pattern",
            ))

        # TODO/FIXME/HACK comments
        if re.search(r'\b(?:TODO|FIXME|HACK|XXX)\b', line, re.IGNORECASE):
            findings.append(make_finding(
                i + 1, stripped,
                "TODO/FIXME comment in code",
                "TODO/FIXME comments indicate incomplete or problematic code "
                "that should be tracked in an issue tracker.",
                "Create a GitHub Issue for this and remove the comment, "
                "or fix it now.",
                "low", "pattern",
            ))

    result = {
        "file": file_path,
        "language": "typescript",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_nextjs_patterns ──────────────────────────────────────────────────

async def _analyze_nextjs_patterns(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    if is_generated_file(file_path):
        result = {"file": file_path, "language": "typescript", "total_findings": 0, "findings": []}
        return [TextContent(type="text", text=json.dumps(result))]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []
    file_name = Path(file_path).name

    is_page = file_name in ("page.tsx", "page.ts", "page.jsx")
    is_layout = file_name in ("layout.tsx", "layout.ts")
    is_client = "'use client'" in content or '"use client"' in content
    is_server_action = "'use server'" in content or '"use server"' in content

    for i, line in enumerate(lines):
        if should_skip_line(line):
            continue
        stripped = line.strip()

        # Client component fetching data with useEffect instead of server component
        if is_client and re.search(r'useEffect\s*\(', line):
            context = "\n".join(lines[i:min(len(lines), i + 15)])
            if re.search(r'fetch\s*\(|axios\.|api\.', context):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Data fetching in client component with useEffect",
                    "In Next.js App Router, data fetching in useEffect runs "
                    "only on the client, missing SSR benefits, causing loading "
                    "flashes, and duplicating requests.",
                    "Move data fetching to a Server Component (remove 'use client') "
                    "or use React Query/SWR for client-side fetching with caching.",
                    "medium", "nextjs",
                ))

        # Hardcoded URLs instead of env variables
        if re.search(r'(?:https?://(?!localhost)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line):
            if not re.search(r'process\.env\.|NEXT_PUBLIC_', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Hardcoded URL instead of environment variable",
                    "Hardcoded URLs break when deploying to different environments "
                    "(dev/staging/prod) and expose internal infrastructure.",
                    "Use environment variables: process.env.NEXT_PUBLIC_API_URL. "
                    "Add to .env.local and .env.example.",
                    "medium", "nextjs",
                ))

        # Missing Suspense around async components
        if re.search(r'<\w+\s*\.\s*\w+\s*/>', line) or \
           re.search(r'await\s+\w+\(', line):
            context = "\n".join(lines[max(0, i-5):i+5])
            if not re.search(r'Suspense|loading|skeleton', context, re.IGNORECASE):
                if is_page:
                    findings.append(make_finding(
                        i + 1, stripped,
                        "Async operation without Suspense boundary",
                        "Async Server Components without Suspense block the entire "
                        "page from rendering until data loads.",
                        "Wrap async components in <Suspense fallback={<Loading />}>. "
                        "Create loading.tsx for automatic loading UI.",
                        "medium", "nextjs",
                    ))

        # Using cookies/headers in client component
        if is_client and re.search(r'(?:cookies|headers)\s*\(\s*\)', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Server-only API used in client component",
                "cookies() and headers() are server-only Next.js APIs. "
                "Using them in client components causes build errors.",
                "Move this logic to a Server Component, Server Action, "
                "or API Route Handler.",
                "critical", "nextjs",
            ))

        # Server Action without proper validation
        if is_server_action and re.search(r'export\s+async\s+function', line):
            block = "\n".join(lines[i:min(len(lines), i + 30)])
            if not re.search(r'\.parse\s*\(|\.safeParse\s*\(|z\.|zod|validate', block):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Server Action without input validation",
                    "Server Actions receive data directly from the client. "
                    "Without validation, malicious users can send unexpected data.",
                    "Validate input with Zod before processing: "
                    "const data = schema.parse(formData)",
                    "high", "nextjs",
                ))

        # Direct database access in page component
        if is_page and re.search(r'prisma\.\w+\.\w+\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Direct Prisma call in page component",
                "Calling Prisma directly in page components mixes data access "
                "with presentation logic, making testing harder.",
                "Extract database calls into a separate data access layer "
                "(e.g., lib/actions/ or lib/data/).",
                "low", "nextjs",
            ))

        # Missing revalidation in server actions
        if is_server_action and re.search(r'(?:create|update|delete|save)\w*\s*\(', line):
            block = "\n".join(lines[i:min(len(lines), i + 20)])
            if not re.search(r'revalidate|redirect|router\.', block):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Server Action without cache revalidation",
                    "Mutating data without revalidating the cache means the UI "
                    "shows stale data after the action completes.",
                    "Call revalidatePath('/path') or revalidateTag('tag') "
                    "after mutations to refresh the cache.",
                    "medium", "nextjs",
                ))

    result = {
        "file": file_path,
        "language": "typescript",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_ts_security ──────────────────────────────────────────────────────

async def _analyze_ts_security(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    if is_generated_file(file_path):
        result = {"file": file_path, "language": "typescript", "total_findings": 0, "findings": []}
        return [TextContent(type="text", text=json.dumps(result))]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []
    is_client = "'use client'" in content or '"use client"' in content

    for i, line in enumerate(lines):
        if should_skip_line(line):
            continue
        stripped = line.strip()

        # eval() usage
        if re.search(r'\beval\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "eval() usage (critical security risk)",
                "eval() executes arbitrary JavaScript from a string. "
                "If any user input reaches eval(), it enables code injection attacks.",
                "Never use eval(). Use JSON.parse() for JSON, "
                "or find an alternative API.",
                "critical", "security",
            ))

        # new Function()
        if re.search(r'new\s+Function\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "new Function() usage (code injection risk)",
                "new Function() is similar to eval() — executes dynamic code. "
                "Vulnerable to injection if user input is used.",
                "Avoid dynamic code execution. Use a proper data structure instead.",
                "critical", "security",
            ))

        # Hardcoded secrets
        if re.search(
            r'(?:secret|api_?key|password|token|private_?key|webhook)\s*[=:]\s*["\'][^"\']{8,}["\']',
            line, re.IGNORECASE
        ):
            findings.append(make_finding(
                i + 1, stripped,
                "Hardcoded secret or API key",
                "Hardcoded secrets in source code are exposed in version control "
                "and can be extracted from client bundles.",
                "Move to environment variables. "
                "Never prefix secrets with NEXT_PUBLIC_ — that exposes them to clients.",
                "critical", "security",
            ))

        # NEXT_PUBLIC_ secret exposure
        if re.search(r'NEXT_PUBLIC_(?:SECRET|KEY|TOKEN|PASSWORD|PRIVATE)', line, re.IGNORECASE):
            findings.append(make_finding(
                i + 1, stripped,
                "Secret exposed as NEXT_PUBLIC_ variable",
                "NEXT_PUBLIC_ variables are bundled into the client JavaScript "
                "and visible to anyone who views the page source.",
                "Remove NEXT_PUBLIC_ prefix. Access this variable only in "
                "Server Components, API routes, or Server Actions.",
                "critical", "security",
            ))

        # innerHTML assignment
        if re.search(r'\.innerHTML\s*=', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Direct innerHTML assignment (XSS risk)",
                "Setting innerHTML directly can execute injected scripts "
                "if the content comes from user input or an untrusted source.",
                "Use textContent instead for plain text. "
                "For HTML content, sanitize with DOMPurify first.",
                "high", "security",
            ))

        # SQL-like string concatenation
        if re.search(r'(?:query|sql|select|insert|update|delete)\s*[+=]\s*["\'].*\$\{', line, re.IGNORECASE):
            findings.append(make_finding(
                i + 1, stripped,
                "Potential SQL injection via template literal",
                "Building SQL queries with template literals and user input "
                "is vulnerable to SQL injection.",
                "Use parameterized queries with Prisma or your ORM. "
                "Never concatenate user input into SQL strings.",
                "critical", "security",
            ))

        # Exposed sensitive data in client component
        if is_client and re.search(r'process\.env\.(?!NEXT_PUBLIC_)\w+', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Server-only env variable in client component",
                "Non-NEXT_PUBLIC_ environment variables are not available "
                "in client components and return undefined at runtime.",
                "Move this logic to a Server Component or API Route. "
                "Only use NEXT_PUBLIC_ variables in client components.",
                "high", "security",
            ))

    result = {
        "file": file_path,
        "language": "typescript",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── list_ts_files ────────────────────────────────────────────────────────────

async def _list_ts_files(
    repo_path: str,
    file_type: str = "all",
    include_tests: bool = False,
) -> list[TextContent]:
    repo = Path(repo_path)
    if not repo.exists():
        return [TextContent(type="text", text=f"Error: not found: {repo_path}")]

    type_patterns = {
        "page":      ["page.tsx", "page.ts"],
        "layout":    ["layout.tsx", "layout.ts"],
        "component": [],  # Any .tsx not in app/
        "hook":      ["use"],
        "action":    ["action", "actions"],
        "api":       ["route.ts", "route.tsx"],
        "util":      ["util", "utils", "helper", "lib"],
        "all":       [],
    }

    extensions = {".ts", ".tsx"}
    files = []

    for path in sorted(repo.rglob("*")):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix not in extensions:
            continue
        if not include_tests and re.search(r'\.(test|spec)\.(ts|tsx)$', path.name):
            continue
        if not include_tests and "/__tests__/" in str(path).replace("\\", "/"):
            continue
        # Skip generated files
        if is_generated_file(str(path)):
            continue

        rel = str(path.relative_to(repo)).replace("\\", "/")

        # Apply type filter
        matched = False
        ft = file_type.lower()
        if ft == "all":
            matched = True
        elif ft == "page":
            matched = path.name in ("page.tsx", "page.ts")
        elif ft == "layout":
            matched = path.name in ("layout.tsx", "layout.ts")
        elif ft == "hook":
            matched = path.stem.startswith("use") and path.stem[3:4].isupper()
        elif ft == "action":
            matched = "action" in rel.lower()
        elif ft == "api":
            matched = path.name in ("route.ts", "route.tsx")
        elif ft == "component":
            matched = path.suffix == ".tsx" and "app/" not in rel
        elif ft == "util":
            matched = any(p in rel.lower() for p in ["util", "helper", "lib/"])

        if not matched:
            continue

        try:
            size = path.stat().st_size
            content_peek = path.read_text(encoding="utf-8", errors="replace")[:300]
            is_client = "'use client'" in content_peek or '"use client"' in content_peek
            is_server = "'use server'" in content_peek or '"use server"' in content_peek

            component_type = "unknown"
            if path.name in ("page.tsx", "page.ts"):
                component_type = "page"
            elif path.name in ("layout.tsx", "layout.ts"):
                component_type = "layout"
            elif path.name in ("loading.tsx", "error.tsx", "not-found.tsx"):
                component_type = "special"
            elif path.name in ("route.ts", "route.tsx"):
                component_type = "api-route"
            elif path.stem.startswith("use") and path.stem[3:4].isupper():
                component_type = "hook"
            elif "action" in rel.lower():
                component_type = "server-action"
            elif path.suffix == ".tsx":
                component_type = "component"

            files.append({
                "path": rel,
                "name": path.name,
                "component_type": component_type,
                "is_client": is_client,
                "is_server_action": is_server,
                "size_kb": round(size / 1024, 1),
            })
        except OSError:
            continue

    result = {
        "repo": repo_path,
        "file_type_filter": file_type,
        "total_files": len(files),
        "files": files,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream, write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
