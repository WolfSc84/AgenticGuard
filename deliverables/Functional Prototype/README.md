# AgenticGuard Layer — Functional Prototype (MVP)

> **Guiding Principle**: *"Design the smallest credible product and technical strategy that could justify entering this market."*

This directory contains the self-contained, zero-dependency **Functional Prototype** of the **AgenticGuard Layer**. It proves the core technical and architectural feasibility of governing AI coding assistants without replacing them.

---

## What This Prototype Proves

1. **AI Gateway Governance (`agentic_guard/gateway.py`)**:
   - Generates authentic `x-portkey-config` (`fallback` routing, `before_request_hooks` DLP) and `x-portkey-metadata` for `portkeyai/gateway:latest`.
   - Enforces user-group RBAC model downgrade (`junior-dev` $\rightarrow$ `claude-sonnet-4`).
   - Enforces deterministic DLP secret blocking (`HTTP 446` with zero token leakage).
   - Handles simulated primary provider outages with automatic multi-cloud fallback (`AWS Bedrock` $\rightarrow$ `Azure OpenAI`).
2. **Centralized Project Context & Traceability (`agentic_guard/db.py`)**:
   - Stores shared architecture standards, project context, active stories, and stage outcomes.
   - Enforces allowed developer access by `project_id` and tracks branch/stage assignments as a complement to Git.
3. **Modular SDLC/STLC Agent Suite via MCP (`agentic_guard/agents_mcp.py`)**:
   - Implements `backlog_ac`, `qa_stlc`, `template_spec` (scaffolding and `SPEC.md` stubs), and `validation_guard`.
   - Supports **both individual standalone execution and custom-ordered sequences** (`invoke_custom_sequence`).
   - Issues cryptographic `X-AgenticGuard-Validation-Receipt` signatures upon passing AST/SAST/type checks.
4. **Unified HTTP / MCP Server (`agentic_guard/server.py`)**:
   - Implements Portkey-compatible `/v1/chat/completions`.
   - Implements standard MCP JSON-RPC 2.0 (`tools/list` & `tools/call`) and REST (`/mcp`, `/mcp/tools`, `/mcp/invoke`).
   - Exposes `/context/{project_id}/{story_id}` for on-demand project context retrieval.
5. **Two-Layer Observability (`agentic_guard/observability.py`)**:
   - **Layer 1 (AI/Agent Tracing)**: OpenTelemetry trace correlation in Langfuse with AC rubric scores.
   - **Layer 2 (Container Logs)**: Structured JSON logs mapped to Fluent Bit $\rightarrow$ Loki $\rightarrow$ Grafana.

---

## System & Environmental Prerequisites

### Mode 1: Fast Standalone Execution (Default / Zero-Setup)
- **Python**: **Python 3.10+** (tested on 3.10, 3.11, 3.12, 3.13, 3.14). Verify with:
  ```bash
  python3 --version
  ```
- **Pip Dependencies**: **None** (`pip install` is **NOT required**). The codebase relies strictly on standard library modules (`sqlite3`, `http.server`, `urllib`, `dataclasses`, `json`, `unittest`, `re`, `uuid`, `threading`, `time`).
- **Cloud Accounts / Keys**: **None**. All model routing, DLP token scanning, and telemetry records run in-process with authentic latency and cost math. No third-party API keys or internet connection are required.
- **Operating System**: macOS, Linux, or Windows (WSL2 / PowerShell).

### Mode 2: Multi-Container Production Stack (Optional)
- **Container Engine**: **Docker** (Docker Desktop / Docker Engine + Compose v2) or **Podman** (`podman compose` / `podman-compose`). Verify with:
  ```bash
  docker compose version
  # or
  podman compose version
  ```
- **Local Ports Required Free**:
  - `8000`: AgenticGuard MCP Service
  - `8787`: Portkey AI Gateway
  - `3000`: Langfuse Observability
  - `3001`: Grafana Dashboard
  - `3100`: Loki Log Ingestion
- **Memory**: 2 GB+ RAM recommended for container workloads.

---

## Quick Start (Zero External Dependencies)

Requires standard Python 3.10+ (no `pip install` required).

### Option 1: Run the Interactive Live Walkthrough
Runs an automated 5-scenario demo illustrating the entire workflow:
```bash
python3 demo_walkthrough.py
```

### Option 2: Run the Automated Test Suite
Runs the 7 unit and integration tests covering the database, gateway, agents, and HTTP server:
```bash
python3 -m unittest discover -s tests -v
```

---

## Running the HTTP & MCP Server Locally

Start the local server:
```bash
python3 -m agentic_guard.server
```
*(Server listens on `http://127.0.0.1:8000`)*

### Test Endpoints via `curl`:

#### 1. Service Health Check
```bash
curl -s http://127.0.0.1:8000/health
```
```json
{
  "status": "healthy",
  "service": "AgenticGuard-Layer"
}
```

#### 2. Discover MCP Tools (REST)
```bash
curl -s http://127.0.0.1:8000/mcp
```

#### 3. Discover MCP Tools (Standard JSON-RPC 2.0)
```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

#### 4. Fetch Project Context by Project and Story ID
```bash
curl -s http://127.0.0.1:8000/context/PROJ-FINTECH-CORE/FIN-101
```

#### 5. Safe Chat Completion via Portkey AI Gateway
```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJ-FINTECH-CORE",
    "story_id": "FIN-101",
    "user_id": "dev-alice",
    "user_group": "senior-eng",
    "model": "claude-sonnet-4",
    "messages": [{"role": "user", "content": "Help calculate invoice total."}]
  }'
```

#### 6. DLP Secret Interception (Blocked Pre-Flight)
```bash
curl -s -i -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "My AWS Key is AKIA1234567890EXAMPLE"}]
  }'
```
*Returns `HTTP/1.0 446` with `PORTKEY_HOOK_DENY_DLP_SECRET:AWS_ACCESS_KEY` — zero tokens sent to any cloud provider.*

---

## Production Container Stack (Docker or Podman Compose)

To spin up the complete enterprise architecture with all open-source services:

```bash
# Option A: With Docker Compose
docker compose up --build

# Option B: With Podman Compose
podman compose up --build
# (or: podman-compose up --build)
```

- **Portkey AI Gateway**: `http://localhost:8787` (Image: `portkeyai/gateway:latest`)
- **AgenticGuard MCP Service**: `http://localhost:8000` (Container: `agenticguard-mcp-langgraph`)
- **Langfuse AI Observability**: `http://localhost:3000`
- **Grafana Dashboard**: `http://localhost:3001` (user: `admin`, password: `admin`)
- **Loki Ingestion Endpoint**: `http://localhost:3100`

---

## File Layout

- [`agentic_guard/`](agentic_guard/):
  - [`agents_mcp.py`](agentic_guard/agents_mcp.py): Modular SDLC/STLC LangGraph agents (`backlog_ac`, `qa_stlc`, `template_spec`, `validation_guard`).
  - [`db.py`](agentic_guard/db.py): Centralized Project Context & Traceability SQLite store.
  - [`gateway.py`](agentic_guard/gateway.py): Portkey AI Gateway configuration generator, RBAC, quotas, and DLP engine.
  - [`observability.py`](agentic_guard/observability.py): Langfuse tracer bridge and Fluent Bit/Loki logger.
  - [`server.py`](agentic_guard/server.py): Zero-dependency unified HTTP & MCP server.
- [`tests/`](tests/):
  - [`test_agentic_guard.py`](tests/test_agentic_guard.py): 7 automated unit and integration tests.
- [`demo_walkthrough.py`](demo_walkthrough.py): Standalone live demo script.
- [`AGENTS.md`](AGENTS.md): Coding assistant conditioning file.
- [`Dockerfile`](Dockerfile) & [`docker-compose.yml`](docker-compose.yml): Production container definitions.
