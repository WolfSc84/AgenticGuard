# Factored Forward Deployed Engineer — Take-Home Assessment

## Solution: AgenticGuard Layer
> **Guiding Principle**: *"Design the smallest credible product and technical strategy that could justify entering this market."*

---

## Executive Summary

The generative AI coding market is dominated by well-funded incumbents (Microsoft Copilot, OpenAI Codex, Cursor, Anthropic Claude Code) investing hundreds of millions in model training and IDE UX. Attempting to build "another AI coding assistant" is an unwinnable Red Queen race.

Instead of competing where incumbents are strongest, **AgenticGuard Layer** captures the enterprise gap they systematically ignore: **cross-assistant governance, SDLC/STLC standardization, and verifiable code evidence**.

We **buy** commodity coding assistants, **compose** proven open-source infrastructure (Portkey Gateway, LangGraph, Langfuse, Loki), and **build only the thin, high-leverage governance layer** (Central Project Context DB + 4 modular MCP agents + Validation Guardrails). This narrow scope enables a **2–4 engineer team** to deliver a stage-gated enterprise pilot for **\$30k**, avoiding a \$650k+ custom assistant build.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AI CODING ASSISTANTS                            │
│           (Cursor · Claude Code · Codex · GitHub Copilot)              │
│                [BUY: Keep developers in their flow]                    │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │ LLM Ingress / Egress            │ MCP Tool Invocations
                   ▼                                 ▼
┌─────────────────────────────────────┐  ┌───────────────────────────────┐
│         PORTKEY AI GATEWAY          │  │     CONTAINERIZED MCP AGENTS  │
│  • RBAC model catalog & routing     │  │  • backlog_ac (User Story+AC) │
│  • Token bucket quotas (Redis)      │  │  • qa_stlc (Test Contracts)   │
│  • Deterministic DLP (Secret regex) │  │  • template_spec (Scaffolding)│
│  • Multi-cloud failover             │  │  • validation_guard (AST/SAST)│
│       [COMPOSE: Open Source]        │  │     [BUILD: Thin / Modular]   │
└──────────────────┬──────────────────┘  └───────────────┬───────────────┘
                   │ AI Spans & Traces                   │ State & Traceability
                   ▼                                     ▼
┌─────────────────────────────────────┐  ┌───────────────────────────────┐
│       TWO-LAYER OBSERVABILITY       │  │   CENTRAL PROJECT CONTEXT DB  │
│  • Layer 1: Langfuse (AI Traces)    │  │  • Org engineering standards  │
│  • Layer 2: Loki/Grafana (Logs)     │  │  • Stage outcomes by project  │
│       [COMPOSE: Open Source]        │  │  • Git-complement work state  │
└─────────────────────────────────────┘  └───────────────────────────────┘
```

---

## Deliverables Directory & How to Consume

All assessment deliverables are located in [`deliverables/`](deliverables/):

| Deliverable | Path | How to Consume |
| :--- | :--- | :--- |
| **Technical Architecture & System Design** | [`deliverables/Technical Architecture - System Design/`](deliverables/Technical%20Architecture%20-%20System%20Design/) | **Read Document**: Open [`01_System_Design_AgenticGuard.md`](deliverables/Technical%20Architecture%20-%20System%20Design/01_System_Design_AgenticGuard.md) for the 8-dimension architecture, risks, assumptions, and CFO capital allocation.<br/>**View Architecture**: Open [`agenticguard-layer.html`](deliverables/Technical%20Architecture%20-%20System%20Design/agenticguard-layer.html) in any web browser to interact with the full 15-component system map. |
| **Functional Prototype (MVP)** | [`deliverables/Functional Prototype/`](deliverables/Functional%20Prototype/) | **Run Live Walkthrough**: `python3 demo_walkthrough.py`<br/>**Run Test Suite**: `python3 -m unittest discover -s tests -v`<br/>**Start MCP & Gateway Server**: `python3 -m agentic_guard.server`<br/>*(Zero external dependencies required; runs on standard library Python 3.10+)*. |
| **Executive Proposal & Pitch Deck** | [`deliverables/Proposal/`](deliverables/Proposal/) | **Present Deck**: Open [`AgenticGuard_Proposal_Deck.html`](deliverables/Proposal/AgenticGuard_Proposal_Deck.html) in any browser. 19-slide presentation deck covering Problem, Product, System, and CFO pitch with keyboard navigation (`←`/`→`/`Space`). |

---

## System & Environmental Prerequisites

To make reviewing as frictionless as possible, the prototype was deliberately engineered to run in **two modes**:

### 1. Fast Standalone Mode (Recommended for Assessment Review)
| Requirement | Specification |
| :--- | :--- |
| **Python Runtime** | **Python 3.10+** (Tested on Python 3.10, 3.11, 3.12, 3.13, and 3.14). Verify with `python3 --version`. |
| **Operating System** | macOS, Linux, or Windows (WSL2 / PowerShell). |
| **External Packages** | **None** (`pip install` is **NOT required**). The prototype runs entirely on Python standard library modules (`sqlite3`, `http.server`, `urllib`, `dataclasses`, `json`, `unittest`, `re`, `uuid`, `threading`). |
| **Cloud Accounts & API Keys** | **None**. LLM inference, provider failovers, and Langfuse/Loki exports are fully simulated in-process with authentic token calculations and headers. No OpenAI/Anthropic/AWS keys required. |
| **Resource Usage** | Runs in < 1 second; requires < 50 MB RAM and zero background daemons. |

### 2. Full Containerized Production Stack (Optional)
| Requirement | Specification |
| :--- | :--- |
| **Container Engine** | **Docker** (Docker Desktop / Docker Engine + Compose v2) or **Podman** (`podman compose` / `podman-compose`). Verify with `docker compose version` or `podman compose version`. |
| **Available Ports** | `8000` (MCP), `8787` (Portkey Gateway), `3000` (Langfuse), `3001` (Grafana), `3100` (Loki). |
| **Allocated Memory** | 2 GB+ RAM recommended for container workloads. |

---

## How to Run the Functional Prototype (Step-by-Step)

The prototype is completely self-contained and requires **zero external pip installations** or background daemons to test.

### Step 1: Run the Interactive Live Walkthrough

Simulates an end-to-end enterprise development lifecycle across 5 realistic scenarios:

```bash
cd "deliverables/Functional Prototype"
python3 demo_walkthrough.py
```

**What you will see:**
1. **Scenario 1 (Modular LangGraph Pipeline)**: Executes `backlog_ac` $\rightarrow$ `qa_stlc` $\rightarrow$ `template_spec` via Central DB and MCP, generating scaffolding without competing with the assistant.
2. **Scenario 2 (Standalone Agent Execution)**: Triggers the QA agent independently on a brownfield bug fix without prior backlog state.
3. **Scenario 3 (Portkey AI Gateway Governance)**: Downgrades an unauthorized junior model request (`claude-opus-4` $\rightarrow$ `claude-sonnet-4`), blocks leaked AWS credentials with HTTP 446 before tokens reach the cloud, and triggers automatic multi-cloud fallback (`AWS Bedrock` $\rightarrow$ `Azure OpenAI`).
4. **Scenario 4 (Validation Guard Gate)**: Catches AST/SAST violations (missing type hints, forbidden `eval()`), rejects the commit, and issues a signed `X-AgenticGuard-Validation-Receipt` upon remediation.
5. **Scenario 5 (Two-Layer Observability)**: Correlates 15 Langfuse spans with rubric scores, emits structured Loki logs via Fluent Bit, and prints an executive harness cost scorecard.

---

### Step 2: Run the Automated Test Suite

Executes the automated unit and integration tests verifying all components, security hooks, and HTTP endpoints:

```bash
cd "deliverables/Functional Prototype"
python3 -m unittest discover -s tests -v
```

**Expected output:**
```
test_http_server_endpoints_and_jsonrpc_mcp ... ok
test_langfuse_and_loki_observability_correlation ... ok
test_langgraph_individual_and_custom_order_execution ... ok
test_portkey_before_request_hooks_block_secrets_and_env_files ... ok
test_portkey_config_generation_rbac_and_quota ... ok
test_project_developer_authorization_and_git_complement_traceability ... ok
test_standalone_qa_agent_graceful_resolution ... ok

Ran 7 tests in ~0.7s — OK
```

---

### Step 3: Run the Containerized HTTP / MCP Server

Start the local server exposing both the Portkey AI Gateway endpoint (`/v1/chat/completions`) and the Containerized MCP Agent Service (`/mcp`):

```bash
cd "deliverables/Functional Prototype"
python3 -m agentic_guard.server
```

*(Server starts on `http://127.0.0.1:8000`)*

#### Test with `curl`:

**Health Check:**
```bash
curl -s http://127.0.0.1:8000/health
# Response: {"status": "healthy", "service": "AgenticGuard-Layer"}
```

**List Available MCP Tools:**
```bash
curl -s http://127.0.0.1:8000/mcp
```

**Fetch Project Context from Central DB:**
```bash
curl -s http://127.0.0.1:8000/context/PROJ-FINTECH-CORE/FIN-101
```

**Send Completion via AI Gateway (DLP Active):**
```bash
# Safe completion
curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Scaffold invoice calculation."}]}'

# Attempt secret leakage (Blocked by DLP with HTTP 446)
curl -s -i -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "My AWS key is AKIA1234567890EXAMPLE"}]}'
```

---

### Step 4: (Optional) Full Container Stack (Docker or Podman)

To run the complete production environment including `portkeyai/gateway:latest`, `langfuse`, `loki`, and `grafana`:

```bash
cd "deliverables/Functional Prototype"

# Option A: Using Docker Compose
docker compose up --build

# Option B: Using Podman Compose
podman compose up --build
# (or: podman-compose up --build)
```

- **Portkey AI Gateway**: `http://localhost:8787`
- **AgenticGuard MCP Service**: `http://localhost:8000`
- **Langfuse Observability**: `http://localhost:3000`
- **Grafana Dashboards**: `http://localhost:3001` (login `admin` / `admin`)
- **Loki Log Ingestion**: `http://localhost:3100`

---

## Why This is the "Smallest Credible Strategy"

| Strategy Dimension | Traditional Approach (High Risk) | AgenticGuard Strategy (Smallest Credible) |
| :--- | :--- | :--- |
| **Product Surface** | Build custom IDE or extension (competing with VS Code / Cursor). | Harness-agnostic governance layer connecting via standard `AGENTS.md` and MCP. |
| **Model Hosting** | Fine-tune custom LLM checkpoints (\$100k+ compute). | Dynamic model routing and DLP via self-hosted Portkey Gateway (\$0 license). |
| **Agent Architecture** | Monolithic custom autonomous agent runtime. | Modular LangGraph nodes invocable individually or in custom sequences. |
| **Observability** | Custom telemetry dashboard from scratch. | Compose open-source Langfuse (AI traces) + Fluent Bit / Loki / Grafana (logs). |
| **Team & Capital** | 15–20 engineers, \$2M–\$5M initial budget. | **2–4 engineers, \$30k pilot budget, 90-day time-to-value**. |
| **Kill Criteria** | Sunk cost fallacy after building an entire assistant. | Clear pilot exit gates: if receipt adoption is <80% or latency overhead >1.5s, abandon. |
