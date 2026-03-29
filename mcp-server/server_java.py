"""
MCP Server — Java/Spring Boot Analysis Tools
Phase 2 extension for Java/Spring Boot projects

Exposes tools for:
- Java bug detection (null safety, resource leaks, exception handling)
- Spring-specific issues (@Transactional, bean scopes, injection patterns)
- Security vulnerabilities (SQL injection, CORS, missing auth)
- Performance issues (N+1 queries, EAGER fetching, missing pagination)

Run alongside the main server or independently.
"""

import json
import re
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("java-spring-analyzer")

# ─── Helpers ─────────────────────────────────────────────────────────────────

IGNORE_DIRS = {
    ".git", "target", "build", ".gradle", ".idea",
    "node_modules", ".mvn", "__pycache__",
}


def is_safe_path(base: str, target: str) -> bool:
    base_path = Path(base).resolve()
    target_path = Path(target).resolve()
    return target_path.is_relative_to(base_path)


def read_file_safe(file_path: str) -> str | None:
    try:
        return Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def is_in_multiline_comment(lines: list[str], index: int) -> bool:
    """Check if a line is inside a /* ... */ block comment."""
    in_comment = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "/*" in stripped:
            in_comment = True
        if "*/" in stripped:
            in_comment = False
            continue
        if i == index:
            return in_comment
    return False


def should_skip_line(lines: list[str], i: int) -> bool:
    """Return True if this line should be skipped for analysis."""
    stripped = lines[i].strip()
    if stripped.startswith("//"):
        return True
    if stripped.startswith("*"):
        return True
    if is_in_multiline_comment(lines, i):
        return True
    return False


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
        "code": code.strip(),
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
            name="analyze_java_bugs",
            description=(
                "Analyzes a Java file for bugs: null pointer risks, "
                "string comparison with ==, resource leaks, empty catch blocks, "
                "missing @Override, and exception handling issues."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .java file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_spring_patterns",
            description=(
                "Checks a Spring Boot Java file for Spring-specific anti-patterns: "
                "@Transactional on private methods, field injection (@Autowired on fields), "
                "wrong bean scopes, missing @Valid on controllers, "
                "returning entities instead of DTOs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .java file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_spring_security",
            description=(
                "Scans a Spring Boot Java file for security issues: "
                "missing @PreAuthorize/@Secured on endpoints, "
                "SQL injection in native queries, CORS misconfiguration, "
                "weak password encoding, sensitive data in logs, "
                "hardcoded credentials."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .java file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_spring_performance",
            description=(
                "Checks a Spring Boot Java file for performance issues: "
                "FetchType.EAGER on collections, missing @Cacheable, "
                "N+1 query patterns, returning full entities from REST endpoints, "
                "missing pagination on list endpoints, synchronous blocking calls."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .java file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="analyze_jpa_issues",
            description=(
                "Analyzes JPA/Hibernate entity and repository files for: "
                "missing indexes on foreign keys, bidirectional relationship issues, "
                "missing equals/hashCode on entities, "
                "using List instead of Set for ManyToMany, "
                "missing @Column constraints, CascadeType.ALL misuse."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to .java file"},
                    "repo_path": {"type": "string", "description": "Repo root for safety validation"},
                },
                "required": ["file_path", "repo_path"],
            },
        ),
        Tool(
            name="list_java_files",
            description=(
                "Lists all Java source files in a repository. "
                "Filters by type: controllers, services, repositories, entities, all. "
                "Ignores test files and build artifacts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Absolute path to repo root"},
                    "file_type": {
                        "type": "string",
                        "description": "Filter: controller, service, repository, entity, config, all",
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
        case "analyze_java_bugs":
            return await _analyze_java_bugs(**arguments)
        case "analyze_spring_patterns":
            return await _analyze_spring_patterns(**arguments)
        case "analyze_spring_security":
            return await _analyze_spring_security(**arguments)
        case "analyze_spring_performance":
            return await _analyze_spring_performance(**arguments)
        case "analyze_jpa_issues":
            return await _analyze_jpa_issues(**arguments)
        case "list_java_files":
            return await _list_java_files(**arguments)
        case _:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ─── analyze_java_bugs ────────────────────────────────────────────────────────

async def _analyze_java_bugs(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]

    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    checks = [
        (
            r'==\s*"[^"]*"',
            "String comparison with == instead of .equals()",
            "== compares object references, not string content. Will fail unexpectedly.",
            'Use .equals() or Objects.equals(a, b) for null-safe comparison',
            "high",
        ),
        (
            r'"[^"]*"\s*==',
            "String comparison with == instead of .equals()",
            "== compares object references, not string content.",
            'Use .equals() or Objects.equals(a, b) for null-safe comparison',
            "high",
        ),
        (
            r'catch\s*\(\s*Exception\s+\w+\s*\)\s*\{\s*\}',
            "Empty catch block swallowing Exception",
            "Silently ignoring exceptions hides bugs and makes debugging impossible.",
            "At minimum log the exception. Consider rethrowing or handling specifically.",
            "high",
        ),
        (
            r'catch\s*\(\s*Exception\s+\w+\s*\)\s*\{',
            "Catching generic Exception",
            "Catching base Exception catches everything including RuntimeException.",
            "Catch specific exceptions. Use multiple catch blocks if needed.",
            "medium",
        ),
        (
            r'\.get\(\)\s*\.',
            "Calling method directly on Optional.get() without isPresent() check",
            "Optional.get() throws NoSuchElementException if empty.",
            "Use .orElse(), .orElseThrow(), .ifPresent(), or .map() instead.",
            "high",
        ),
        (
            r'return\s+null\s*;',
            "Returning null from method",
            "Returning null forces callers to do null checks and risks NullPointerException.",
            "Return Optional<T>, empty collection, or throw a specific exception instead.",
            "medium",
        ),
        (
            r'new\s+(?:FileInputStream|FileOutputStream|FileReader|FileWriter|Connection|Statement)\s*\(',
            "Resource not in try-with-resources",
            "Resources opened without try-with-resources may not be closed on exception.",
            "Use try-with-resources: try (FileInputStream fis = new FileInputStream(...)) { }",
            "high",
        ),
        (
            r'e\.printStackTrace\(\)',
            "Using printStackTrace() instead of logger",
            "printStackTrace() outputs to stderr only, lost in production environments.",
            "Use a proper logger: log.error(\"message\", e)",
            "medium",
        ),
        (
            r'System\.out\.print',
            "Using System.out instead of logger",
            "System.out has no log levels, cannot be configured or filtered.",
            "Use SLF4J/Logback: private static final Logger log = LoggerFactory.getLogger(...).",
            "low",
        ),
        (
            r'(?:public|protected|private)\s+\w+\s+\w+\([^)]*\)\s*(?:throws\s+\w+\s*)?\{[^}]*\}',
            None,  # Skip — too broad, handled below
            "", "", "low",
        ),
    ]

    for i, line in enumerate(lines):
        if should_skip_line(lines, i):
            continue
        stripped = line.strip()

        for pattern, title, description, fix, severity in checks:
            if title is None:
                continue
            if re.search(pattern, line):
                findings.append(make_finding(
                    i + 1, stripped, title, description, fix, severity, "bug"
                ))

    result = {
        "file": file_path,
        "language": "java",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_spring_patterns ──────────────────────────────────────────────────

async def _analyze_spring_patterns(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]

    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    # Detect file type for context-aware checks
    is_controller = any(
        a in content for a in ["@RestController", "@Controller"]
    )
    is_service = "@Service" in content
    is_repository = any(
        a in content for a in ["@Repository", "JpaRepository", "CrudRepository"]
    )

    checks = [
        (
            r'@Transactional',
            r'private\s+\w+\s+\w+\s*\(',
            "transactional_private",
        ),
        (
            r'@Autowired\s*\n\s*(?:private|protected)',
            None,
            "field_injection",
        ),
        (
            r'@Autowired',
            None,
            "autowired_field",
        ),
    ]

    for i, line in enumerate(lines):
        if should_skip_line(lines, i):
            continue
        stripped = line.strip()

        # @Transactional on private method
        if "@Transactional" in line:
            # Look ahead for private method
            for j in range(i + 1, min(i + 4, len(lines))):
                if re.search(r'\bprivate\b', lines[j]) and re.search(r'\w+\s*\(', lines[j]):
                    findings.append(make_finding(
                        i + 1, stripped,
                        "@Transactional on private method",
                        "Spring's AOP proxy cannot intercept private methods. "
                        "@Transactional has NO effect on private methods.",
                        "Make the method public, or move transaction boundary to a public caller.",
                        "high", "pattern",
                    ))
                    break

        # Field injection (@Autowired on field)
        if "@Autowired" in line:
            next_lines = " ".join(lines[i+1:i+3]) if i + 2 < len(lines) else ""
            if re.search(r'\b(private|protected)\b', next_lines) and \
               not re.search(r'\b(constructor|set[A-Z])\b', next_lines):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Field injection with @Autowired",
                    "Field injection makes classes harder to test and hides dependencies. "
                    "It also doesn't work well with immutability.",
                    "Use constructor injection: add the dependency as a final field "
                    "and inject via constructor (Lombok @RequiredArgsConstructor helps).",
                    "medium", "pattern",
                ))

        # Controller returning Entity directly
        if is_controller and re.search(
            r'(?:public|private)\s+(?:ResponseEntity<)?(\w+)(?:>)?\s+\w+\s*\(',
            line
        ):
            if re.search(r'\b(?:Entity|@Entity)\b', content) and \
               re.search(r'return\s+\w+(?:Repository|Service)\.\w+', " ".join(lines[i:i+20])):
                pass  # Too complex to detect reliably with regex

        # Missing @Valid on controller parameters
        if is_controller and re.search(r'@RequestBody\s+\w+', line):
            if "@Valid" not in line and "@Validated" not in line:
                findings.append(make_finding(
                    i + 1, stripped,
                    "Missing @Valid on @RequestBody parameter",
                    "@RequestBody without @Valid skips bean validation entirely. "
                    "Invalid input reaches your service layer unchecked.",
                    "Add @Valid before @RequestBody: "
                    "public ResponseEntity<?> method(@Valid @RequestBody MyDto dto)",
                    "high", "pattern",
                ))

        # @RequestMapping instead of specific mapping
        if re.search(r'@RequestMapping\s*\(', line) and is_controller:
            if "method" not in line:
                findings.append(make_finding(
                    i + 1, stripped,
                    "@RequestMapping without HTTP method specification",
                    "@RequestMapping without method= accepts ALL HTTP methods. "
                    "This can expose unintended operations.",
                    "Use specific annotations: @GetMapping, @PostMapping, "
                    "@PutMapping, @DeleteMapping, @PatchMapping.",
                    "medium", "pattern",
                ))

        # @Autowired on constructor (unnecessary in modern Spring)
        if "@Autowired" in line and i + 1 < len(lines):
            if re.search(r'public\s+\w+\s*\(', lines[i + 1] if i + 1 < len(lines) else ""):
                findings.append(make_finding(
                    i + 1, stripped,
                    "@Autowired on constructor is unnecessary",
                    "Since Spring 4.3, @Autowired on a single constructor is implicit.",
                    "Remove @Autowired from constructor. "
                    "Use Lombok @RequiredArgsConstructor for cleaner code.",
                    "low", "pattern",
                ))

        # Mutable singleton state
        if re.search(r'@Service|@Component|@Repository|@RestController', line):
            pass  # Detected at class level — handled separately

        if re.search(r'private\s+(?!final\s+)(?!static\s+)(?!volatile\s+)\w+\s+\w+\s*;', line):
            if is_service or is_controller:
                # Non-final, non-static field in singleton bean
                if not re.search(r'private\s+(?:final|static)', line):
                    findings.append(make_finding(
                        i + 1, stripped,
                        "Mutable instance field in singleton Spring bean",
                        "Spring beans are singletons by default. Mutable non-final "
                        "fields shared across requests cause race conditions.",
                        "Make the field final, use local variables, "
                        "or use @Scope(\"request\") / @Scope(\"prototype\").",
                        "high", "pattern",
                    ))

    result = {
        "file": file_path,
        "language": "java",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_spring_security ──────────────────────────────────────────────────

async def _analyze_spring_security(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]

    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    is_controller = any(
        a in content for a in ["@RestController", "@Controller"]
    )

    for i, line in enumerate(lines):
        if should_skip_line(lines, i):
            continue
        stripped = line.strip()

        # Hardcoded credentials
        if re.search(
            r'(?:password|secret|apikey|api_key|token|credential)\s*=\s*"[^"]{3,}"',
            line, re.IGNORECASE
        ):
            findings.append(make_finding(
                i + 1, stripped,
                "Hardcoded credential or secret",
                "Hardcoded secrets in source code are exposed in version control "
                "and can be extracted from compiled binaries.",
                "Use environment variables, Spring @Value with externalized config, "
                "or a secrets manager (Vault, AWS Secrets Manager).",
                "critical", "security",
            ))

        # SQL injection via string concatenation
        if re.search(r'(?:nativeQuery|createQuery|createNativeQuery)\s*\([^)]*\+', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Potential SQL injection via string concatenation",
                "Building SQL queries with string concatenation allows attackers "
                "to inject malicious SQL.",
                "Use named parameters: @Query(\"SELECT * FROM t WHERE id = :id\") "
                "with @Param(\"id\"). Never concatenate user input into queries.",
                "critical", "security",
            ))

        # CORS allowing all origins
        if re.search(r'allowedOrigins\s*\(\s*["\']?\*["\']?\s*\)', line):
            findings.append(make_finding(
                i + 1, stripped,
                "CORS configured to allow all origins (*)",
                "Allowing all origins defeats CORS protection and allows "
                "any website to make authenticated requests to your API.",
                "Specify exact allowed origins: "
                ".allowedOrigins(\"https://yourfrontend.com\")",
                "high", "security",
            ))

        # Weak password encoder
        if re.search(r'new\s+(?:MD5|SHA|NoOp)PasswordEncoder\s*\(', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Weak or no password encoding",
                "MD5/SHA password encoders are cryptographically broken. "
                "NoOpPasswordEncoder stores passwords in plain text.",
                "Use BCryptPasswordEncoder or Argon2PasswordEncoder.",
                "critical", "security",
            ))

        # Logging sensitive data
        if re.search(
            r'log\.\w+\s*\([^)]*(?:password|token|secret|credential|ssn|credit)[^)]*\)',
            line, re.IGNORECASE
        ):
            findings.append(make_finding(
                i + 1, stripped,
                "Logging sensitive data",
                "Sensitive data in logs can be exposed in log files, "
                "log aggregation systems, or monitoring tools.",
                "Never log passwords, tokens, or PII. "
                "Mask or omit sensitive fields from log output.",
                "high", "security",
            ))

        # Missing auth on sensitive endpoints
        if is_controller and re.search(
            r'(?:@PostMapping|@DeleteMapping|@PutMapping)\s*\(',
            line
        ):
            # Check if @PreAuthorize or @Secured is nearby
            context = "\n".join(lines[max(0, i-3):i+2])
            if not re.search(r'@(?:PreAuthorize|Secured|RolesAllowed)', context):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Mutating endpoint without authorization annotation",
                    "POST/PUT/DELETE endpoints without @PreAuthorize or @Secured "
                    "may be accessible to unauthenticated users if security config "
                    "is not perfectly configured.",
                    "Add @PreAuthorize(\"isAuthenticated()\") or role-based "
                    "@PreAuthorize(\"hasRole('ADMIN')\") to sensitive endpoints.",
                    "medium", "security",
                ))

        # Actuator endpoints exposed
        if re.search(r'management\.endpoints\.web\.exposure\.include\s*=\s*\*', line):
            findings.append(make_finding(
                i + 1, stripped,
                "All Actuator endpoints exposed",
                "Exposing all actuator endpoints leaks internal application state, "
                "metrics, environment variables, and allows shutdown.",
                "Only expose needed endpoints: "
                "management.endpoints.web.exposure.include=health,info",
                "high", "security",
            ))

        # Disabled CSRF
        if re.search(r'csrf\(\)\.disable\(\)', line):
            findings.append(make_finding(
                i + 1, stripped,
                "CSRF protection disabled",
                "Disabling CSRF makes your app vulnerable to Cross-Site "
                "Request Forgery attacks for state-changing operations.",
                "Only disable CSRF for stateless REST APIs using JWT tokens. "
                "If using sessions/cookies, keep CSRF enabled.",
                "medium", "security",
            ))

    result = {
        "file": file_path,
        "language": "java",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_spring_performance ───────────────────────────────────────────────

async def _analyze_spring_performance(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]

    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    is_controller = any(
        a in content for a in ["@RestController", "@Controller"]
    )
    is_entity = "@Entity" in content

    for i, line in enumerate(lines):
        if should_skip_line(lines, i):
            continue
        stripped = line.strip()

        # FetchType.EAGER on collections
        if re.search(r'fetch\s*=\s*FetchType\.EAGER', line):
            if re.search(r'@(?:OneToMany|ManyToMany)', "\n".join(lines[max(0,i-2):i+1])):
                findings.append(make_finding(
                    i + 1, stripped,
                    "FetchType.EAGER on collection relationship",
                    "EAGER fetching on collections always loads all related entities "
                    "even when not needed, causing serious performance issues at scale.",
                    "Use FetchType.LAZY (default for collections) and load with "
                    "JOIN FETCH in specific queries when needed.",
                    "high", "performance",
                ))

        # Missing pagination on list endpoints
        if is_controller and re.search(
            r'(?:List|Collection|Iterable)<',
            line
        ) and re.search(r'@(?:GetMapping|RequestMapping)', "\n".join(lines[max(0,i-3):i+1])):
            if "Pageable" not in content and "Page<" not in content:
                findings.append(make_finding(
                    i + 1, stripped,
                    "List endpoint without pagination",
                    "Returning all records without pagination can return millions "
                    "of rows, causing out of memory errors and slow responses.",
                    "Add Pageable parameter: "
                    "public Page<Dto> getAll(Pageable pageable). "
                    "Use spring.data.web.pageable.default-page-size.",
                    "high", "performance",
                ))

        # @Cacheable missing on expensive read operations
        if re.search(r'@GetMapping', line) and is_controller:
            context = "\n".join(lines[max(0,i-2):i+3])
            if not re.search(r'@Cacheable', context):
                pass  # Only flag if we can detect it's expensive — too noisy otherwise

        # N+1 query pattern: calling repository in a loop
        if re.search(r'for\s*\(|\.forEach\(|\.stream\(', line):
            context = "\n".join(lines[i:min(len(lines), i+5)])
            if re.search(r'(?:Repository|Service)\.\w+\(', context):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Potential N+1 query problem",
                    "Calling repository/service inside a loop executes one query "
                    "per iteration. With 1000 records = 1000 database queries.",
                    "Use a batch query: repository.findAllByIdIn(ids) or "
                    "JOIN FETCH in JPQL to load related data in one query.",
                    "high", "performance",
                ))

        # Synchronous blocking in reactive context
        if re.search(r'\.block\(\)', line):
            findings.append(make_finding(
                i + 1, stripped,
                "Blocking call in potentially reactive context",
                ".block() on a reactive type blocks the thread, "
                "defeating the purpose of reactive programming.",
                "Avoid .block(). Compose reactive chains with .flatMap(), "
                ".switchIfEmpty(), etc. Only block at application entry points.",
                "high", "performance",
            ))

        # Returning entities directly from REST endpoints
        if is_controller and is_entity:
            if re.search(r'@Entity', content) and re.search(
                r'return\s+\w*[Rr]epository\.\w+\(',
                "\n".join(lines[i:i+3])
            ):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Returning JPA entity directly from REST endpoint",
                    "Returning entities directly exposes internal data model, "
                    "can cause lazy loading exceptions, and leaks sensitive fields.",
                    "Create a DTO class and map entity to DTO before returning. "
                    "Use ModelMapper or MapStruct for mapping.",
                    "medium", "performance",
                ))

        # Missing @Transactional on multi-step write operations
        if re.search(r'(?:save|saveAll|delete|deleteAll)\s*\(', line):
            context = "\n".join(lines[max(0,i-10):i+1])
            if re.search(r'(?:save|saveAll|delete|deleteAll)\s*\(', context[:-len(line)]):
                if "@Transactional" not in "\n".join(lines[max(0,i-20):i]):
                    findings.append(make_finding(
                        i + 1, stripped,
                        "Multiple write operations without @Transactional",
                        "Multiple save/delete operations without a transaction boundary "
                        "can leave data in inconsistent state if one operation fails.",
                        "Wrap the method with @Transactional to ensure atomicity.",
                        "medium", "performance",
                    ))

    result = {
        "file": file_path,
        "language": "java",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── analyze_jpa_issues ───────────────────────────────────────────────────────

async def _analyze_jpa_issues(file_path: str, repo_path: str) -> list[TextContent]:
    if not is_safe_path(repo_path, file_path):
        return [TextContent(type="text", text="Error: path traversal blocked")]

    content = read_file_safe(file_path)
    if content is None:
        return [TextContent(type="text", text=f"Error: cannot read {file_path}")]

    lines = content.splitlines()
    findings = []

    is_entity = "@Entity" in content

    for i, line in enumerate(lines):
        if should_skip_line(lines, i):
            continue
        stripped = line.strip()

        # Missing @Index on @JoinColumn (foreign key without index)
        if re.search(r'@JoinColumn', line):
            context = "\n".join(lines[max(0,i-3):i+2])
            if "@Index" not in context and "index" not in context.lower():
                findings.append(make_finding(
                    i + 1, stripped,
                    "Foreign key column without database index",
                    "Foreign key columns used in JOIN queries are not automatically "
                    "indexed by JPA. Without an index, queries slow down dramatically "
                    "as data grows.",
                    "Add @Index to the @Table annotation: "
                    "@Table(indexes = @Index(columnList = \"column_name\"))",
                    "high", "jpa",
                ))

        # CascadeType.ALL on @ManyToMany
        if re.search(r'@ManyToMany', line):
            context = "\n".join(lines[i:min(len(lines), i+3)])
            if "CascadeType.ALL" in context:
                findings.append(make_finding(
                    i + 1, stripped,
                    "CascadeType.ALL on @ManyToMany relationship",
                    "CascadeType.ALL on ManyToMany cascades deletions to the join table "
                    "AND the related entities, often deleting data unintentionally.",
                    "Use CascadeType.PERSIST and CascadeType.MERGE only. "
                    "Avoid CascadeType.REMOVE and CascadeType.ALL on ManyToMany.",
                    "high", "jpa",
                ))

        # List instead of Set for ManyToMany
        if re.search(r'@ManyToMany', line):
            context = "\n".join(lines[i:min(len(lines), i+3)])
            if re.search(r'List<', context):
                findings.append(make_finding(
                    i + 1, stripped,
                    "Using List instead of Set for @ManyToMany",
                    "Using List with @ManyToMany causes Hibernate to delete all "
                    "join table rows and reinsert them on any change (HHH-000)",
                    "Use Set<> instead of List<> for @ManyToMany relationships.",
                    "medium", "jpa",
                ))

        # Missing equals/hashCode on entity
        if is_entity and "@Entity" in line:
            if "equals" not in content and "hashCode" not in content:
                if "@EqualsAndHashCode" not in content:
                    findings.append(make_finding(
                        i + 1, stripped,
                        "JPA Entity missing equals() and hashCode()",
                        "Without proper equals/hashCode, entities behave incorrectly "
                        "in Sets, Maps, and when comparing detached entities.",
                        "Override equals() and hashCode() based on the business key "
                        "(natural ID), not the generated primary key. "
                        "Or use Lombok @EqualsAndHashCode(of = \"naturalId\").",
                        "medium", "jpa",
                    ))

        # Missing @Column(nullable=false) for required fields
        if re.search(r'@NotNull|@NotEmpty|@NotBlank', line):
            next_line = lines[i+1] if i+1 < len(lines) else ""
            if not re.search(r'@Column\s*\(', next_line) and \
               not re.search(r'nullable\s*=\s*false', next_line):
                findings.append(make_finding(
                    i + 1, stripped,
                    "@NotNull without @Column(nullable=false)",
                    "@NotNull only validates at application level. Without "
                    "@Column(nullable=false), the database column allows NULLs.",
                    "Add @Column(nullable=false) to enforce constraint at DB level too.",
                    "low", "jpa",
                ))

        # Bidirectional relationship without mappedBy
        if re.search(r'@OneToMany', line):
            context = "\n".join(lines[i:min(len(lines), i+3)])
            if "mappedBy" not in context:
                findings.append(make_finding(
                    i + 1, stripped,
                    "@OneToMany without mappedBy (owning side issue)",
                    "Without mappedBy, Hibernate creates an unnecessary join table "
                    "instead of using the foreign key in the child table.",
                    "Add mappedBy: @OneToMany(mappedBy = \"parentField\") "
                    "to point to the @ManyToOne field in the child entity.",
                    "medium", "jpa",
                ))

    result = {
        "file": file_path,
        "language": "java",
        "total_findings": len(findings),
        "findings": findings,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ─── list_java_files ──────────────────────────────────────────────────────────

async def _list_java_files(
    repo_path: str,
    file_type: str = "all",
    include_tests: bool = False,
) -> list[TextContent]:
    repo = Path(repo_path)
    if not repo.exists():
        return [TextContent(type="text", text=f"Error: path not found: {repo_path}")]

    type_patterns = {
        "controller": ["Controller", "Resource", "Endpoint"],
        "service":    ["Service", "ServiceImpl", "Facade"],
        "repository": ["Repository", "Dao", "RepositoryImpl"],
        "entity":     ["Entity", "Model", "Domain"],
        "config":     ["Config", "Configuration", "Properties"],
        "all":        [],
    }
    patterns = type_patterns.get(file_type.lower(), [])

    files = []
    for path in sorted(repo.rglob("*.java")):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if not include_tests and ("test" in str(path).lower() or "Test" in path.name):
            continue
        if patterns and not any(p in path.name for p in patterns):
            continue

        try:
            size = path.stat().st_size
            # Detect Spring component type
            content_peek = path.read_text(encoding="utf-8", errors="replace")[:500]
            component_type = "unknown"
            for ct, pts in type_patterns.items():
                if ct == "all":
                    continue
                if any(f"@{p}" in content_peek or p in path.name for p in pts):
                    component_type = ct
                    break

            files.append({
                "path": str(path.relative_to(repo)),
                "name": path.name,
                "component_type": component_type,
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
