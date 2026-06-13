---
trigger: always_on
---

## Collaboration & Pushback
- **Challenge Bad Decisions:** If you believe the user is making a poor technical choice, introducing an anti-pattern, or pursuing a flawed design, you MUST push back. Argue your case, discuss the trade-offs, and suggest the optimal alternative before proceeding. Do not blindly implement bad choices.

## Architecture & Code Quality
- **Pursue Perfection:** Strive for the highest possible quality in both code and architecture. Do not settle for "good enough" or simple patches if the underlying design is fundamentally flawed.
- **Encourage Architectural Rewrites:** If you encounter poorly structured code, tangled logic, or obsolete patterns, you are strongly encouraged to propose and execute architectural rewrites. Prioritize long-term maintainability, scalability, and elegance over quick fixes. Rewrites must focus on simplifying the system and removing complexity rather than introducing new, over-engineered abstractions.
- **Simplicity over Cleverness (KISS / YAGNI):** Pursuing perfection means writing code that is elegant, readable, and easy to maintain—not over-engineered. Avoid premature optimization, "clever" one-liners, and unnecessary abstractions. 

## Developer Experience (DX)
- **Prioritize Ergonomics:** Ensure that running simple commands, scripts, or daily tasks is straightforward and frictionless.
- **Eliminate Friction and Workarounds:** Avoid introducing patchy workarounds or complex, brittle setups just to perform routine development tasks. If a process is painful or requires hacks to run, you MUST fix the underlying tooling or configuration rather than passing the burden to the developer.

## Bug Fixing & Error Handling
- **Address Root Causes:** You MUST investigate and fix the underlying root cause of a bug rather than treating symptoms. Avoid temporary workarounds wherever possible.
- **Document Workarounds:** Workarounds should only be used as a last resort when the root cause is external (e.g., a bug in a third-party dependency, browser quirk, or OS-level constraint) and cannot be fixed directly. If a workaround is absolutely necessary, or if you are addressing a complex/unclear issue, you MUST add comprehensive inline documentation explaining *why* the code is written that way. This prevents future maintainers from inadvertently removing critical logic.
- **Fail Fast and Loud:** Never swallow exceptions silently. Handle errors gracefully where expected, but if an unexpected state occurs, fail fast, log the error clearly, and provide actionable error messages.
- **"Setup Once, Use Forever" Global Error Handling:** Avoid scattering `try/except` blocks across routes or callbacks just to catch and log unexpected errors. Instead, configure a global exception handler at the application's framework boundary (e.g., FastAPI's `@app.exception_handler`, Tkinter's `report_callback_exception`, or Python's `sys.excepthook`). This ensures all unhandled exceptions are automatically captured, logged, and gracefully handled in exactly one centralized place per application.

## Testing & Verification
- **Verify Everything:** Never consider a feature or fix complete without proving it works. Whenever possible, write or update automated tests. If automated testing isn't feasible, you must execute and document a clear manual verification plan.
- **Robust and Simple Tests:** Testing must be robust. Tests must be simple to reason about and easily understood. Avoid overcomplicating test logic.
- **Test-Driven Development (TDD):** Use test-driven development. Always write tests *before* the implementation. Do not apply tests after the implementation, as this often leads to poor, biased, or fragile tests. Note that this applies to new feature development and bug fixes (e.g., writing a failing test for a bug first, then fixing it), and does not prohibit backfilling missing automated tests for existing untested components.

## Code Comments
- **Write Declarative Comments:** When writing comments, do not mention that a change was made or reference previous states of the code (e.g., avoid "Updated this to..."). 
- **Start from Scratch Perspective:** Write comments as if the feature or function were written from scratch. Keep them direct, declarative, and clean.

## Python & Frameworks
- **Package Management (uv):** ALWAYS use `uv` for Python dependency management and script execution. You MUST strictly follow the latest `uv` recommendations and best practices.
- **Workspace Layout:** In a monorepo or workspace using a `src/` layout, every workspace member MUST be configured as a proper installable package by defining a `[build-system]` (e.g., `hatchling`). This ensures `uv` installs them in editable mode natively, allowing tools like `pytest` to resolve modules out-of-the-box without relying on `pythonpath` hacks or manual `PYTHONPATH` injection.
- **FastAPI & FastMCP Best Practices:** You MUST strictly adhere to the latest official documentation, recommended patterns, and best practices for FastAPI and FastMCP. Avoid outdated approaches or generic web server anti-patterns.

## Core Design Ideologies
- **SOLID Principles:** Adhere strictly to the Single Responsibility Principle (SRP) and Dependency Inversion Principle (DIP). Keep functions and classes focused on one task. Inject dependencies rather than hardcoding them to allow for easy mocking in tests.
- **Object-Oriented Domain Logic:** Encapsulate business logic and state mutations within dedicated domain service classes or rich domain models. The outer "shell" (API routes, UI events) should act as thin wrappers that instantiate or inject these classes and call their methods, keeping the domain logic decoupled from the transport layer.
- **Defensive Programming (Parse, Don't Validate):** Guarantee validity at the boundaries using strong typing (e.g., Pydantic). Once data enters the core system, it must be completely valid so the domain logic never has to check for nulls or malformed data.
- **Separation of Concerns (Domain vs. Transport):** Never leak transport-layer details (HTTP requests, WebSocket contexts) into domain logic. API routes and MCP tools must be extremely thin wrappers that simply parse inputs, call domain service methods or model logic, and format the outputs.

## Code Conventions & Consistency
- **Ruthless Consistency:** A perfect architecture requires uniformity. Code must look like it was written by a single person. Adhere strictly to established naming conventions, directory structures, and design patterns.
- **Automated Formatting & Linting:** Do not waste time debating formatting. Rely on standard, automated formatters and linters (e.g., `ruff` for Python) and ensure they pass before considering a task complete.

## Observability & Tracing
- **Structured and Contextual Logging:** When writing logs, ensure they contain enough context (IDs, state summaries) to make tracing execution flow and diagnosing issues in production trivial.
- **Log Significant Events:** Every significant state mutation, external API call, or error must be logged. Silent failures or silent successes of complex workflows are unacceptable.
- **Standard Stream Logging (stdout vs. stderr):** Default all application logging stream handlers to standard error (`sys.stderr`) instead of standard output (`sys.stdout`). Under POSIX guidelines, `stdout` is reserved for data payloads, and `stderr` is for diagnostics/logs. Logging to `sys.stderr` prevents JSON-RPC protocol corruption on stdio-based transport systems (such as MCP) and complies with the latest MCP specifications.
- **Detached Process Logs Redirecting:** When launching background or detached subprocesses, their `stdout` and `stderr` streams must always be routed to the parent's standard error (`sys.stderr`) to preserve observability and prevent swallowing errors (complying with the "Fail Fast and Loud" rule) without violating workspace file constraints or polluting standard output. This applies to background daemons or detached services, and does not apply to subprocesses executed synchronously to retrieve data payloads via `stdout`.
