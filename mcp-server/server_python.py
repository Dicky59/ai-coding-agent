"""
MCP Server — Python Code Analysis Tools
Exposes tools for:
- Python bug detection (mutable defaults, bare except, None comparisons)
- Security issues (eval, pickle, subprocess shell, hardcoded secrets)
- Code quality (long functions, too many args, missing type hints)
- Async patterns (missing await, sync in async context)
"""

import json
import re
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("python-analyzer")

# ─── Helpers ─────────────────────────────────────────────────────────────────

IGNORE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}


def is_safe_path(base: str, target: str) -> bool:
    return Path(target).resolve().is_relative_to(Path(base).resolve())


def read_file_safe(file_path: str) -> str | None:
    try:
        return Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def should_skip_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("#") or stripped == ""


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


# ─── Tool definitions ─────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_python_bugs",
            description=(
                "Analyzes a Python file for common bugs: "
                "mutable default arguments, bare except clauses, "
                "comparison with None/True/False using ==, "
                "missing f-string prefix, and shadowing builtins."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "repo_path": {"type": "string"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_python_security",
            description=(
                "Scans Python files for security issues: "
                "eval/exec usage, pickle.loads, subprocess with shell=True, "
                "hardcoded secrets, SQL string concatenation, "
                "and yaml.load without Loader."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "repo_path": {"type": "string"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_python_quality",
            description=(
                "Reviews Python code quality: "
                "functions too long (50+ lines), too many parameters (6+), "
                "print statements in production code, missing type hints, "
                "TODO/FIXME comments, and deeply nested code."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "repo_path": {"type": "string"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_python_async",
            description=(
                "Checks Python async patterns: "
                "missing await on coroutines, blocking calls in async functions "
                "(time.sleep, requests.get), bare asyncio.run inside async, "
                "and missing async context managers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "repo_path": {"type": "string"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="list_python_files",
            description=(
                "Lists Python source files in a repository. "
                "Ignores __pycache__, .venv, test files by default."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "include_tests": {"type": "boolean", "default": False},
                },
                "required": ["repo_path"],
            },
        ),
    ]


# ─── Tool router ──────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    match name:
        case "analyze_python_bugs":
            return await _analyze_python_bugs(**arguments)
        case "analyze_python_security":
            return await _analyze_python_security(**arguments)
        case "analyze_python_quality":
            return await _analyze_python_quality(**arguments)
        case "analyze_python_async":
            return await _analyze_python_async(**arguments)
        case "list_python_files":
            return await _list_python_files(**arguments)
        case _:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ─── analyze_python_bugs ──────────────────────────────────────────────────────

async def _analyze_python_bugs(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    # Track indentation for scope detection
    in_class = False

    for i, line in enumerate(lines):
        if should_skip_line(line):
            continue
        stripped = line.strip()

        # Mutable default argument
        if re.search(r'def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|list\(\)|dict\(\)|set\(\))', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Mutable default argument",
                "Using mutable objects (list, dict, set) as default arguments "
                "is a classic Python bug. The default is shared across all calls "
                "that don't provide the argument, causing unexpected state.",
                "Use None as default and create inside function: "
                "def foo(items=None): items = items or []",
                "high", "bug",
            ))

        # Bare except
        if re.search(r'^\s*except\s*:', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Bare except clause",
                "Bare except: catches ALL exceptions including KeyboardInterrupt, "
                "SystemExit, and GeneratorExit. This can hide bugs and make the "
                "program impossible to interrupt.",
                "Catch specific exceptions: except (ValueError, TypeError) as e: "
                "or at minimum except Exception as e:",
                "high", "bug",
            ))

        # Comparison with None using ==
        if re.search(r'(?:==|!=)\s*None\b', line) and "==" in line:
            if not re.search(r'#.*==.*None', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Comparison to None with == instead of is",
                    "Comparing to None with == can be overridden by __eq__. "
                    "PEP 8 recommends using 'is' and 'is not' for None checks.",
                    "Use: if value is None: or if value is not None:",
                    "low", "bug",
                ))

        # Comparison with True/False using ==
        if re.search(r'==\s*(True|False)\b', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Comparison to True/False with ==",
                "Comparing with == True or == False is redundant and un-Pythonic. "
                "It also ignores truthy/falsy values.",
                "Use: if value: or if not value: directly",
                "low", "bug",
            ))

        # String that looks like it should be f-string
        if re.search(r'(?<!\bf)["\'].*\{[a-zA-Z_]\w*\}.*["\']', line):
            if not re.search(r'\bf["\']', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Possible missing f-string prefix",
                    "This string contains {variable} placeholders but doesn't "
                    "have the f prefix. The variables will be printed literally.",
                    "Add f prefix: f'Hello {name}' instead of 'Hello {name}'",
                    "medium", "bug",
                ))

        # Shadowing builtins
        builtins = {"list", "dict", "set", "tuple", "type", "id", "input",
                    "filter", "map", "zip", "range", "len", "str", "int", "float"}
        match = re.match(r'^\s*(\w+)\s*=', line)
        if match and match.group(1) in builtins:
            findings.append(make_finding(
                i + 1, stripped,
                f"Shadowing built-in name '{match.group(1)}'",
                f"Assigning to '{match.group(1)}' shadows the Python built-in. "
                "This can cause confusing bugs later in the same scope.",
                f"Use a more descriptive name like '{match.group(1)}_data' or "
                f"'{match.group(1)}_items'",
                "medium", "bug",
            ))

        # Using == instead of is for singleton comparisons
        if re.search(r'==\s*None\b|None\s*==', line):
            pass  # already caught above

        # assert in non-test code
        if stripped.startswith("assert ") and "test" not in file_path.lower():
            findings.append(make_finding(
                i + 1, stripped,
                "assert statement in production code",
                "assert statements are removed when Python runs with -O flag. "
                "They should not be used for input validation in production code.",
                "Use explicit if checks with raise ValueError/TypeError instead.",
                "medium", "bug",
            ))

    result = {
        "file": file_path,
        "language": "python",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_python_security ──────────────────────────────────────────────────

async def _analyze_python_security(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    for i, line in enumerate(lines):
        if should_skip_line(line):
            continue
        stripped = line.strip()

        # eval() / exec()
        if re.search(r'\beval\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "eval() usage — critical security risk",
                "eval() executes arbitrary Python code from a string. "
                "Any user input reaching eval() enables code injection.",
                "Never use eval(). Use ast.literal_eval() for safe literal "
                "parsing, or find a safer alternative.",
                "critical", "security",
            ))

        if re.search(r'\bexec\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "exec() usage — code injection risk",
                "exec() executes arbitrary Python code. "
                "Extremely dangerous with any user-controlled input.",
                "Avoid exec() entirely. Refactor to use proper functions.",
                "critical", "security",
            ))

        # pickle.loads
        if re.search(r'pickle\.loads?\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "pickle.load/loads — arbitrary code execution",
                "Deserializing untrusted pickle data can execute arbitrary code. "
                "Never unpickle data from untrusted sources.",
                "Use JSON, msgpack, or other safe serialization formats. "
                "If pickle is needed, only unpickle data you created yourself.",
                "critical", "security",
            ))

        # subprocess with shell=True
        if re.search(r'subprocess\.\w+\s*\(', line):
            if re.search(r'shell\s*=\s*True', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "subprocess with shell=True",
                    "shell=True passes the command to the shell interpreter, "
                    "enabling shell injection attacks if any input is user-controlled.",
                    "Use shell=False (default) and pass args as a list: "
                    "subprocess.run(['git', 'status'], shell=False)",
                    "high", "security",
                ))

        # os.system
        if re.search(r'\bos\.system\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "os.system() usage",
                "os.system() is vulnerable to shell injection and doesn't "
                "provide good error handling or output capture.",
                "Use subprocess.run() with shell=False instead.",
                "high", "security",
            ))

        # Hardcoded secrets
        if re.search(
            r'(?:secret|api_?key|password|passwd|token|private_?key)\s*=\s*["\'][^"\']{6,}["\']',
            line, re.IGNORECASE
        ):
            findings.append(make_finding(
                i + 1, stripped,
                "Hardcoded secret or credential",
                "Hardcoded secrets in source code are exposed in version control "
                "and can be extracted by anyone with repo access.",
                "Use environment variables: os.environ.get('MY_SECRET') "
                "or a secrets manager. Add .env to .gitignore.",
                "critical", "security",
            ))

        # yaml.load without Loader
        if re.search(r'yaml\.load\s*\([^)]*\)', line):
            if not re.search(r'Loader\s*=', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "yaml.load() without Loader argument",
                    "yaml.load() without a Loader can deserialize arbitrary "
                    "Python objects, enabling code execution.",
                    "Use yaml.safe_load() or yaml.load(data, Loader=yaml.SafeLoader)",
                    "high", "security",
                ))

        # SQL string concatenation
        if re.search(
            r'(?:execute|query)\s*\(\s*[f"\'].*(?:SELECT|INSERT|UPDATE|DELETE)',
            line, re.IGNORECASE
        ):
            findings.append(make_finding(
                i + 1, stripped,
                "Potential SQL injection via string formatting",
                "Building SQL queries with string formatting or f-strings "
                "with user input enables SQL injection attacks.",
                "Use parameterized queries: cursor.execute(sql, (param,)) "
                "or use an ORM like SQLAlchemy.",
                "critical", "security",
            ))

        # requests without timeout
        if re.search(r'requests\.\w+\s*\(', line):
            if not re.search(r'timeout\s*=', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "requests call without timeout",
                    "HTTP requests without a timeout can hang indefinitely, "
                    "blocking your application.",
                    "Always set a timeout: requests.get(url, timeout=30)",
                    "medium", "security",
                ))

    result = {
        "file": file_path,
        "language": "python",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_python_quality ───────────────────────────────────────────────────

async def _analyze_python_quality(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []
    is_test = "test" in file_path.lower() or "spec" in file_path.lower()

    # Check function lengths and parameter counts
    current_func_start = -1
    current_func_name = ""
    current_func_indent = 0
    brace_depth = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        # Detect function definitions
        func_match = re.match(r'\s*(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)', line)
        if func_match:
            func_name = func_match.group(1)
            params_str = func_match.group(2)

            # Count parameters (excluding self, cls, *args, **kwargs)
            if params_str.strip():
                params = [
                    p.strip() for p in params_str.split(",")
                    if p.strip() and p.strip() not in ("self", "cls")
                    and not p.strip().startswith("*")
                ]
                if len(params) > 5:
                    findings.append(make_finding(
                        i + 1, stripped,
                        f"Function '{func_name}' has too many parameters ({len(params)})",
                        "Functions with many parameters are hard to call correctly "
                        "and often indicate the function does too much.",
                        "Group related parameters into a dataclass or TypedDict, "
                        "or split the function into smaller pieces.",
                        "medium", "quality",
                    ))

            # Check missing return type hint
            if "->" not in line and func_name not in ("__init__", "__str__", "__repr__"):
                if not is_test:
                    findings.append(make_finding(
                        i + 1, stripped,
                        f"Function '{func_name}' missing return type hint",
                        "Type hints make code easier to understand and enable "
                        "static analysis tools to catch type errors.",
                        "Add return type: def foo(x: int) -> str: "
                        "or -> None for functions that don't return a value.",
                        "low", "quality",
                    ))

            # Track function for length check
            current_func_start = i
            current_func_name = func_name
            current_func_indent = indent

        # Check if we've left the function
        elif (current_func_start >= 0 and
              indent <= current_func_indent and
              stripped and
              not stripped.startswith("#") and
              i > current_func_start + 1):
            func_length = i - current_func_start
            if func_length > 50:
                findings.append(make_finding(
                    current_func_start + 1,
                    f"def {current_func_name}(...)",
                    f"Function '{current_func_name}' is too long ({func_length} lines)",
                    "Long functions are hard to understand, test, and maintain. "
                    "Each function should do one thing well.",
                    "Break into smaller functions. Aim for functions under 30 lines.",
                    "medium", "quality",
                ))
            current_func_start = -1

        if should_skip_line(line):
            continue

        # print() in non-test, non-script files
        if re.search(r'\bprint\s*\(', line) and not is_test:
            # Skip if it looks like a CLI script (has if __name__ == "__main__")
            if "__name__" not in content:
                findings.append(make_finding(
                    i + 1, stripped,
                    "print() statement in production code",
                    "print() statements left in production code clutter logs "
                    "and may expose sensitive information.",
                    "Use Python's logging module instead: "
                    "import logging; logger = logging.getLogger(__name__)",
                    "low", "quality",
                ))

        # TODO/FIXME
        if re.search(r'\b(?:TODO|FIXME|HACK|XXX)\b', line, re.IGNORECASE):
            findings.append(make_finding(
                i + 1, stripped,
                "TODO/FIXME comment",
                "TODO/FIXME comments indicate incomplete or problematic code "
                "that should be tracked in an issue tracker.",
                "Create a GitHub Issue and remove the comment, or fix it now.",
                "low", "quality",
            ))

        # Deep nesting (more than 4 levels)
        if indent >= 16 and stripped:  # 4 spaces * 4 levels
            findings.append(make_finding(
                i + 1, stripped,
                "Deeply nested code",
                f"Code nested {indent // 4} levels deep is hard to read and test. "
                "Deep nesting often indicates too much complexity in one function.",
                "Extract nested logic into helper functions. "
                "Use early returns to reduce nesting.",
                "medium", "quality",
            ))

    result = {
        "file": file_path,
        "language": "python",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_python_async ─────────────────────────────────────────────────────

async def _analyze_python_async(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]
    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    if "async" not in content and "await" not in content:
        result = {"file": file_path, "language": "python",
                  "total_findings": 0, "findings": []}
        return [TextContent(type="text", text=json.dumps(result))]

    lines = content.splitlines()
    findings = []
    in_async_func = False
    async_func_indent = 0

    for i, line in enumerate(lines):
        if should_skip_line(line):
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        # Track if we're inside an async function
        if re.match(r'\s*async\s+def\s+', line):
            in_async_func = True
            async_func_indent = indent
        elif in_async_func and indent <= async_func_indent and stripped and i > 0:
            if not re.match(r'\s*(?:async\s+)?def\s+', line):
                in_async_func = False

        # Blocking calls inside async functions
        if in_async_func:
            # time.sleep in async context
            if re.search(r'\btime\.sleep\s*\(', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "time.sleep() in async function (blocks event loop)",
                    "time.sleep() blocks the entire event loop, preventing "
                    "other coroutines from running during the sleep.",
                    "Use await asyncio.sleep() instead.",
                    "high", "async",
                ))

            # requests in async context
            if re.search(r'\brequests\.\w+\s*\(', line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Synchronous requests in async function",
                    "requests library is synchronous and blocks the event loop "
                    "when used inside async functions.",
                    "Use httpx with await: async with httpx.AsyncClient() as c: "
                    "resp = await c.get(url)",
                    "high", "async",
                ))

            # open() without async
            if re.search(r'\bopen\s*\(', line) and "await" not in line:
                findings.append(make_finding(
                    i + 1, stripped,
                    "Synchronous file I/O in async function",
                    "open() is synchronous and blocks the event loop. "
                    "For large files this can cause significant latency.",
                    "Use aiofiles: async with aiofiles.open(path) as f: "
                    "content = await f.read()",
                    "medium", "async",
                ))

        # asyncio.run() inside async function
        if re.search(r'\basyncio\.run\s*\(', line) and in_async_func:
            findings.append(make_finding(
                i + 1, stripped,
                "asyncio.run() inside async function",
                "asyncio.run() creates a new event loop and cannot be called "
                "from within a running event loop.",
                "Use await directly: await my_coroutine() "
                "instead of asyncio.run(my_coroutine())",
                "high", "async",
            ))

        # Missing await on common coroutines
        if re.search(r'(?<!\bawait\s)(?<!\breturn\s)asyncio\.sleep\s*\(', line):
            if "await" not in line:
                findings.append(make_finding(
                    i + 1, stripped,
                    "asyncio.sleep() called without await",
                    "asyncio.sleep() is a coroutine and must be awaited. "
                    "Without await it creates a coroutine object but doesn't sleep.",
                    "Add await: await asyncio.sleep(1)",
                    "high", "async",
                ))

    result = {
        "file": file_path,
        "language": "python",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── list_python_files ────────────────────────────────────────────────────────

async def _list_python_files(
    repo_path: str,
    include_tests: bool = False,
) -> list[TextContent]:
    repo = Path(repo_path)
    if not repo.exists():
        return [TextContent(type="text", text=f"Error: not found: {repo_path}")]

    files = []
    for path in sorted(repo.rglob("*.py")):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if not include_tests:
            if re.search(r'test_|_test\.py$|conftest\.py', path.name):
                continue

        rel = str(path.relative_to(repo)).replace("\\", "/")
        try:
            size = path.stat().st_size
            content_peek = path.read_text(encoding="utf-8", errors="replace")[:200]
            has_async = "async def" in content_peek or "await " in content_peek
            has_classes = "class " in content_peek

            file_type = "script"
            if "def " in content_peek and "class " in content_peek:
                file_type = "module"
            elif "class " in content_peek:
                file_type = "class"
            elif "async def" in content_peek:
                file_type = "async"
            elif path.name.startswith("test_"):
                file_type = "test"

            files.append({
                "path": rel,
                "name": path.name,
                "file_type": file_type,
                "has_async": has_async,
                "has_classes": has_classes,
                "size_kb": round(size / 1024, 1),
            })
        except OSError:
            continue

    result = {
        "repo": repo_path,
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
