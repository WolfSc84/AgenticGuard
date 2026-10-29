# AGENTS.md — AgenticGuard Layer Repository Context & Conditioning Rules

> **Purpose**: This file conditions any AI Software-Development Assistant (`Claude Code`, `Cursor`, `GitHub Copilot`, `Codex`) operating in this repository to align with our **Centralized Project Context Database**, consume our **Containerized SDLC/STLC Agent Services via MCP**, and route all model inference through our self-hosted **Portkey AI Gateway (`portkey-ai/gateway`)**.

---

## 1. Mandatory AI Gateway Configuration (`portkey-ai/gateway` Control Plane)
All coding assistants and containerized agent services MUST consume LLMs through the centralized **Portkey AI Gateway** rather than direct vendor endpoints:
- **Portkey Gateway Base URL**: `http://localhost:8787/v1` (or `PORTKEY_GATEWAY_URL`)
- **Required Portkey Headers**:
  - `x-portkey-config`: Group-scoped Portkey routing, fallback, and `before_request_hooks` guardrail configuration JSON.
  - `x-portkey-metadata`: JSON object containing `user_id`, `user_group`, `harness_client` (`claude-code` | `cursor` | `codex`), `project_id`, and `story_id`.
- **Forbidden Direct Egress**: Never send `.env` files, private keys (`*.pem`), credentials, or raw production database dumps to any LLM context window.

---

## 2. Mandatory MCP Services Workflow (East-West Standardization Plane)
Developers and AI Coding Assistants can invoke the containerized **AgenticGuard MCP Services** (`http://localhost:8000/mcp`) **individually on-demand** or **in any custom sequence** depending on the current task and project maturity:

### Available MCP Tools (Invocable Individually or in Custom Order)
1. **`mcp__agenticguard__get_project_context`**:
   - **When to call**: At the start of any coding session or planning phase.
   - **Behavior**: Fetches the shared project architecture state, corporate engineering standards, active story Acceptance Criteria, and QA test contracts from the **Central Project Context Database** so all developers stay aligned.
2. **`mcp__agenticguard__backlog_ac_agent`**:
   - **When to call**: When starting from project documentation, ambiguous feature requests, or syncing with the ALM (`Jira` / `Linear` / `Azure DevOps`).
   - **Outcome Stored in DB**: Standardized Backlog Story + Gherkin Acceptance Criteria (`Given / When / Then`) + non-functional security constraints.
3. **`mcp__agenticguard__qa_stlc_agent`**:
   - **When to call**: Whenever test cases or executable test contracts are needed (can consume Acceptance Criteria from the Central DB or standalone input).
   - **Outcome Stored in DB**: Structured STLC Test Matrix (Happy Path, Edge Cases, Security/Negative Cases) + executable `pytest` contract stubs.
4. **`mcp__agenticguard__template_spec_agent`**:
   - **When to call**: Before implementing a new module or feature with the AI Coding Assistant.
   - **Outcome Stored in DB**: Generates **only** the standardized project scaffolding/template, interface signatures, and `SPEC.md` contract. *(The AI Coding Assistant then implements the business logic against this spec and the QA test cases).*
5. **`mcp__agenticguard__validation_guard_agent`**:
   - **When to call**: Mandatory before declaring any task complete or creating a Git commit / Pull Request.
   - **Outcome Stored in DB**: Runs deterministic guardrails (AST check, SAST security scan, type/docstring lint, QA test verification) + non-deterministic Spec/Acceptance Criteria Rubric Judge, issuing a signed `X-AgenticGuard-Validation-Receipt`.

---

## 3. Corporate Engineering & Security Standards (Inter-Project Baseline)
- **Type Safety & Documentation**: Every public Python class and function MUST include explicit type annotations and a clear docstring.
- **Database Safety**: All SQL queries MUST use parameterized bindings (`?` or `:param`). String concatenation or f-strings inside SQL statements are strictly blocked by the Validation Guard.
- **Zero Hardcoded Secrets & Unsafe Execution**: Never use `eval()`, `exec()`, `subprocess.Popen(..., shell=True)`, or hardcoded API keys/tokens.
- **Test-First Alignment**: Implementation code must satisfy all QA test contracts and Gherkin Acceptance Criteria registered for the active story in the Central Project Context DB.
