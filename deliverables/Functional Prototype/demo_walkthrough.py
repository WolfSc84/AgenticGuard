"""Interactive End-to-End Live Demo for AgenticGuard Layer (Functional Prototype MVP).

Run with:
    python3 demo_walkthrough.py

Validates our core architectural assumptions:
1. Modular LangGraph (`StateGraph`) SDLC/STLC Agent Services (invocable individually or in custom order)
2. Centralized Project Context & Outcomes Database keeping multiple developers aligned
3. 100% AI Consumption via Portkey AI Gateway (RBAC model routing, quotas, deterministic DLP, failover)
4. Complementarity with AI Coding Assistants via AGENTS.md conditioning + Validation Receipts
5. Two-Layer Containerized Observability:
   - Langfuse (connected to both Portkey Gateway & LangGraph CallbackHandler traces/scores)
   - Fluent Bit -> Loki -> Grafana (structured JSON container & service logs)
"""

from __future__ import annotations

from agentic_guard.agents_mcp import AgenticGuardMCPService
from agentic_guard.db import CentralContextDB
from agentic_guard.gateway import AgenticGuardGateway, GatewayRequest


def print_banner(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 90)
    print(f"  {title}")
    print("=" * 90)


def run_demo() -> None:
    """Execute the complete AgenticGuard Layer live demonstration."""
    db = CentralContextDB(":memory:")
    gateway = AgenticGuardGateway(db)
    mcp = AgenticGuardMCPService(db, gateway)

    project_id = "PROJ-FINTECH-CORE"
    story_id = "FIN-101"

    db.register_project(
        project_id=project_id,
        name="Enterprise Billing & Tax Calculation Service",
        domain="fintech-payments",
        alm_provider="Jira",
        shared_context={
            "architecture_pattern": "Hexagonal / Clean Service Layer",
            "database": "PostgreSQL (parameterized queries mandatory)",
        },
        allowed_developers=[
            {"developer_id": "dev-lead", "role": "staff-eng", "preferred_harness": "claude-code"},
            {"developer_id": "qa-engineer", "role": "qa-lead", "preferred_harness": "cursor"},
            {"developer_id": "architect-dev", "role": "principal-eng", "preferred_harness": "claude-code"},
            {"developer_id": "dev-alice", "role": "senior-eng", "preferred_harness": "claude-code"},
            {"developer_id": "dev-bob", "role": "junior-dev", "preferred_harness": "cursor"},
        ],
    )

    print_banner(
        "SCENARIO 1: Modular LangGraph StateGraph Agents — Custom Sequence via MCP & Central DB"
    )
    sequence_results = mcp.invoke_custom_sequence(
        project_id=project_id,
        story_id=story_id,
        agent_sequence=["backlog_ac", "qa_stlc", "template_spec"],
        context_inputs={
            "project_doc_summary": "Calculate invoice total with tax rate and reject negative bounds.",
            "target_module_name": "billing_service.py",
        },
    )
    for item in sequence_results:
        agent_name = item["agent"]
        res = item["result"]
        print(
            f"  [LangGraph Node: {agent_name:<13}] -> Central DB Outcome #{res['outcome_id']} "
            f"| Portkey Model: {res['gateway_model_used']} (${res['gateway_cost_usd']:.5f}) "
            f"| Langfuse Trace: {res['langfuse_trace_id']}"
        )

    unified_ctx = db.get_unified_project_context(project_id, story_id)
    print(f"\n  [Central Context DB Alignment Check by project_id={project_id} / {story_id}]")
    print(f"  • Allowed Project Developers : {[d['developer_id'] for d in unified_ctx['allowed_developers']]}")
    print(f"  • ALM Ticket Sync Status     : {unified_ctx['alm_ticket']['status']}")
    print(f"  • Stages Persisted in DB     : {list(unified_ctx['stage_outcomes'].keys())}")
    print("  • Developer-to-Feature Traceability (Git Complement in Central DB):")
    for assign in unified_ctx["active_feature_assignments"]:
        print(
            f"      - Dev: {assign['developer_id']:<14} | Story: {assign['story_id']:<14} "
            f"| Branch: {assign['git_branch']:<22} | Stage: {assign['active_stage']:<15} | Status: {assign['work_status']}"
        )
    print("  • Generated Template Stub (handed to AI Coding Assistant, NOT competing with it):")
    for line in unified_ctx["stage_outcomes"]["template_spec"]["payload"][
        "module_template_skeleton"
    ].splitlines():
        print(f"      {line}")

    print_banner("SCENARIO 2: Individual (Standalone) & Out-of-Order LangGraph Node Execution")
    standalone_qa = mcp.invoke_custom_sequence(
        project_id=project_id,
        story_id="FIN-202-HOTFIX",
        agent_sequence=["qa_stlc"],
        context_inputs={
            "custom_acceptance_criteria": [
                "AC-HOTFIX-1: Reject zero or negative currency conversion rates."
            ]
        },
    )[0]["result"]
    print(
        f"  • Standalone LangGraph QA Node triggered on brownfield ticket FIN-202-HOTFIX "
        f"(AC Source: {standalone_qa['ac_source_resolved']}) -> Generated {len(standalone_qa['test_cases'])} test cases."
    )

    print_banner("SCENARIO 3: Portkey AI Gateway — RBAC, Deterministic DLP & Multi-Cloud Failover")

    # 3A: Junior Dev in Cursor requests expensive claude-opus-4 -> Auto-downgraded by RBAC
    r_rbac = gateway.process_chat_completion(
        GatewayRequest(
            session_id="sess-cursor-1",
            project_id=project_id,
            story_id=story_id,
            user_id="dev-bob",
            user_group="junior-dev",
            harness_client="cursor",
            requested_model="claude-opus-4",
            messages=[
                {
                    "role": "user",
                    "content": "Implement calculate_invoice_total per SPEC.md and QA tests. " * 25,
                }
            ],
            cache_hit_ratio=0.15,
        )
    )
    print(
        f"  1. [Portkey RBAC Governance] Cursor ('junior-dev') requested 'claude-opus-4'\n"
        f"     -> Action: {r_rbac.guardrail_action} | Routed to: {r_rbac.routed_model} ({r_rbac.provider})"
    )

    # 3B: Assistant accidentally includes AWS Secret Key -> Deterministically Blocked at Portkey Hook
    r_dlp = gateway.process_chat_completion(
        GatewayRequest(
            session_id="sess-cursor-2",
            project_id=project_id,
            story_id=story_id,
            user_id="dev-bob",
            user_group="junior-dev",
            harness_client="cursor",
            requested_model="claude-sonnet-4",
            messages=[
                {
                    "role": "user",
                    "content": "Debug config with key AKIAIOSFODNN7EXAMPLE from production.",
                }
            ],
        )
    )
    print(
        f"  2. [Portkey before_request_hooks DLP] Assistant attempted to send AWS Access Key\n"
        f"     -> HTTP {r_dlp.status_code} | Action: {r_dlp.guardrail_action} (Zero tokens leaked to cloud)"
    )

    # 3C: Senior Dev in Claude Code experiences primary provider outage -> Automatic Fallback
    r_failover = gateway.process_chat_completion(
        GatewayRequest(
            session_id="sess-cc-1",
            project_id=project_id,
            story_id=story_id,
            user_id="dev-alice",
            user_group="senior-eng",
            harness_client="claude-code",
            requested_model="claude-sonnet-4",
            messages=[
                {
                    "role": "user",
                    "content": "Implement billing_service.py following SPEC.md contract.",
                }
            ],
            simulate_primary_outage=True,
            cache_hit_ratio=0.65,
        )
    )
    print(
        f"  3. [Portkey Fallback Strategy] Primary AWS Bedrock outage simulated\n"
        f"     -> Action: {r_failover.guardrail_action}"
    )

    print_banner("SCENARIO 4: LangGraph Validation Guard — SAST/AST Gate & Langfuse Rubric Score")

    bad_assistant_code = (
        "def calculate_invoice_total(subtotal, tax_rate):\n"
        "    return eval(f'{subtotal} * (1 + {tax_rate})')\n"
    )
    bad_val = mcp.run_validation_guard_agent(
        project_id=project_id,
        story_id=story_id,
        candidate_code=bad_assistant_code,
        harness_client="cursor",
        user_id="dev-bob",
    )
    print(f"  • Attempt 1 (Unstandardized Assistant Output) -> Status: {bad_val['status']}")
    print(f"    Violations Caught: {bad_val['violations']}")

    compliant_assistant_code = (
        '"""Governed implementation of billing_service.py."""\n\n'
        "def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:\n"
        '    """Calculate invoice total with tax after validating non-negative inputs."""\n'
        "    if subtotal < 0 or tax_rate < 0:\n"
        '        raise ValueError("Subtotal and tax_rate must be non-negative.")\n'
        "    return round(subtotal * (1.0 + tax_rate), 2)\n"
    )
    good_val = mcp.run_validation_guard_agent(
        project_id=project_id,
        story_id=story_id,
        candidate_code=compliant_assistant_code,
        harness_client="claude-code",
        user_id="dev-alice",
    )
    print(f"\n  • Attempt 2 (Spec-Aligned Assistant Output)   -> Status: {good_val['status']}")
    print(f"    Signed Validation Receipt: {good_val['validation_receipt']}")
    print(f"    Updated ALM Ticket Status: {db.get_alm_ticket(story_id)['status']}")

    print_banner(
        "SCENARIO 5: Two-Layer Observability — Langfuse (AI/Portkey) + Fluent Bit/Loki/Grafana"
    )
    lf_summary = gateway.langfuse.get_trace_summary()
    print("  [Layer 1: Langfuse AI & Agent Observability (Connected to Portkey & LangGraph)]")
    print(
        f"  • Total Spans Traced: {lf_summary['total_spans_recorded']} "
        f"(Portkey Gateway Spans: {lf_summary['portkey_gateway_spans']} | "
        f"LangGraph Node Spans: {lf_summary['langgraph_node_spans']})"
    )
    print("  • Langfuse Evaluation Scores Recorded:")
    for sc in lf_summary["scores"]:
        print(f"      - Trace {sc['trace_id']}: {sc['name']} = {sc['value']} ({sc['comment']})")

    print("\n  [Layer 2: Fluent Bit -> Loki -> Grafana Container & Service Logs (Sample Tail)]")
    for log_entry in gateway.loki.log_buffer[-3:]:
        print(f"      {gateway.loki.format_loki_line(log_entry)}")

    print("\n  [Executive Harness Cost & Efficiency Scorecard]")
    scorecard = db.get_harness_efficiency_scorecard()
    print(
        f"  {'HARNESS / CLIENT':<20} | {'CALLS':<6} | {'BLOCKED':<8} | "
        f"{'TOKENS':<8} | {'CACHE HIT %':<12} | {'TOTAL COST ($)':<14}"
    )
    print("  " + "-" * 80)
    for row in scorecard:
        print(
            f"  {row['harness_client']:<20} | {row['total_calls']:<6} | {row['blocked_calls']:<8} | "
            f"{row['total_tokens']:<8} | {row['cache_hit_pct']:>10.1f}% | ${row['total_cost_usd']:<13.5f}"
        )
    print("=" * 90 + "\n")


if __name__ == "__main__":
    run_demo()
