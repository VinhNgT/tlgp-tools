---
trigger: always_on
---

## Collaboration & Pushback
- **Challenge Bad Decisions:** If you believe the user is making a poor technical choice, introducing an anti-pattern, or pursuing a flawed design, you MUST push back. Argue your case, discuss the trade-offs, and suggest the optimal alternative before proceeding. Do not blindly implement bad choices.

## Architecture & Code Quality
- **Pursue Perfection:** Strive for the highest possible quality in both code and architecture. Do not settle for "good enough" or simple patches if the underlying design is fundamentally flawed.
- **Encourage Architectural Rewrites:** If you encounter poorly structured code, tangled logic, or obsolete patterns, you are strongly encouraged to propose and execute architectural rewrites. Prioritize long-term maintainability, scalability, and elegance over quick fixes.
- **Simplicity over Cleverness (KISS / YAGNI):** Pursuing perfection means writing code that is elegant, readable, and easy to maintain—not over-engineered. Avoid premature optimization, "clever" one-liners, and unnecessary abstractions. 

## Bug Fixing & Error Handling
- **Address Root Causes:** You MUST investigate and fix the underlying root cause of a bug rather than treating symptoms. Avoid temporary workarounds wherever possible.
- **Document Workarounds:** If a workaround is absolutely necessary, or if you are addressing a complex/unclear issue, you MUST add comprehensive inline documentation explaining *why* the code is written that way. This prevents future maintainers from inadvertently removing critical logic.
- **Fail Fast and Loud:** Never swallow exceptions silently. Handle errors gracefully where expected, but if an unexpected state occurs, fail fast, log the error clearly, and provide actionable error messages.

## Testing & Verification
- **Verify Everything:** Never consider a feature or fix complete without proving it works. Whenever possible, write or update automated tests. If automated testing isn't feasible, you must execute and document a clear manual verification plan.
- **Robust and Simple Tests:** Testing must be robust. Tests must be simple to reason about and easily understood. Avoid overcomplicating test logic.
- **Test-Driven Development (TDD):** Use test-driven development. Always write tests *before* the implementation. Do not apply tests after the implementation, as this often leads to poor, biased, or fragile tests.

## Code Comments
- **Write Declarative Comments:** When writing comments, do not mention that a change was made or reference previous states of the code (e.g., avoid "Updated this to..."). 
- **Start from Scratch Perspective:** Write comments as if the feature or function were written from scratch. Keep them direct, declarative, and clean.

## Python & Frameworks
- **Package Management:** ALWAYS use `uv` for Python dependency management and script execution.
- **FastAPI & FastMCP Best Practices:** You MUST strictly adhere to the latest official documentation, recommended patterns, and best practices for FastAPI and FastMCP. Avoid outdated approaches or generic web server anti-patterns.

## Core Design Ideologies
- **SOLID Principles:** Adhere strictly to the Single Responsibility Principle (SRP) and Dependency Inversion Principle (DIP). Keep functions and classes focused on one task. Inject dependencies rather than hardcoding them to allow for easy mocking in tests.
- **Functional Core, Imperative Shell:** Push state mutations to the very edges of the application. Keep core domain logic as pure, side-effect-free functions and use immutable data structures where possible. The outer "shell" (API routes, UI events) should handle the imperative, stateful work.
- **Defensive Programming (Parse, Don't Validate):** Guarantee validity at the boundaries using strong typing (e.g., Pydantic). Once data enters the core system, it must be completely valid so the domain logic never has to check for nulls or malformed data.
- **Separation of Concerns (Domain vs. Transport):** Never leak transport-layer details (HTTP requests, WebSocket contexts) into domain logic. API routes and MCP tools must be extremely thin wrappers that simply parse inputs, call pure Python domain functions, and format the outputs.

## Code Conventions & Consistency
- **Ruthless Consistency:** A perfect architecture requires uniformity. Code must look like it was written by a single person. Adhere strictly to established naming conventions, directory structures, and design patterns.
- **Automated Formatting & Linting:** Do not waste time debating formatting. Rely on standard, automated formatters and linters (e.g., `ruff` for Python) and ensure they pass before considering a task complete.

## Observability & Tracing
- **Structured and Contextual Logging:** When writing logs, ensure they contain enough context (IDs, state summaries) to make tracing execution flow and diagnosing issues in production trivial.
- **Log Significant Events:** Every significant state mutation, external API call, or error must be logged. Silent failures or silent successes of complex workflows are unacceptable.
