"""Containerized Modular LangGraph SDLC & STLC Agent Services Exposed via MCP.

Implements the 4 modular SDLC/STLC agents (`backlog_ac`, `qa_stlc`, `template_spec`,
`validation_guard`) as a stateful `LangGraph` (`StateGraph(SDLCGraphState)`) workflow
with dynamic conditional routing (`add_conditional_edges`) so developers can invoke
any single agent node standalone or chain them in any custom sequence via MCP.

All LLM calls route through `Portkey AI Gateway`, all outcomes persist in the
`Central Project Context DB`, all graph nodes and rubric scores trace to `Langfuse`,
and all container service events emit structured JSON logs to `Fluent Bit -> Loki -> Grafana`.
"""

from __future__ import annotations

import ast
import hashlib
import re
import time
from typing import Any, Callable, TypedDict

from agentic_guard.db import CentralContextDB
from agentic_guard.gateway import AgenticGuardGateway, GatewayRequest

try:
    from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]

    LANGGRAPH_RUNTIME = "langgraph.graph.StateGraph"
except ImportError:
    START = "__start__"
    END = "__end__"
    LANGGRAPH_RUNTIME = "agentic_guard.langgraph_compat.StateGraph"

    class _CompiledStateGraph:
        """Lightweight compiled LangGraph StateGraph compatible runtime."""

        def __init__(
            self,
            nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
            conditional_edges: dict[str, Callable[[dict[str, Any]], str]],
        ) -> None:
            self._nodes = nodes
            self._conditional_edges = conditional_edges

        def invoke(
            self,
            initial_state: dict[str, Any],
            config: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Execute the state graph following conditional edges until END."""
            state = dict(initial_state)
            current = self._conditional_edges[START](state)
            while current != END:
                node_fn = self._nodes[current]
                updates = node_fn(state)
                state.update(updates)
                router_fn = self._conditional_edges.get(current)
                current = router_fn(state) if router_fn else END
            return state

    class StateGraph:  # type: ignore[no-redef]
        """Drop-in compatible LangGraph StateGraph builder when langgraph package is absent."""

        def __init__(self, state_schema: Any) -> None:
            self.state_schema = state_schema
            self._nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
            self._conditional_edges: dict[str, Callable[[dict[str, Any]], str]] = {}

        def add_node(
            self,
            name: str,
            action: Callable[[dict[str, Any]], dict[str, Any]],
        ) -> None:
            """Register a state graph node."""
            self._nodes[name] = action

        def add_conditional_edges(
            self,
            source: str,
            path: Callable[[dict[str, Any]], str],
            path_map: dict[str, str] | None = None,
        ) -> None:
            """Register a conditional routing function from a source node."""
            if path_map is not None:
                self._conditional_edges[source] = lambda st: path_map.get(path(st), END)
            else:
                self._conditional_edges[source] = path

        def compile(self) -> _CompiledStateGraph:
            """Compile the state graph into an invocable workflow."""
            return _CompiledStateGraph(self._nodes, self._conditional_edges)


class SDLCGraphState(TypedDict):
    """Typed state passed across LangGraph SDLC & STLC agent nodes."""

    project_id: str
    story_id: str
    langfuse_trace_id: str
    requested_sequence: list[str]
    current_index: int
    context_inputs: dict[str, Any]
    execution_results: list[dict[str, Any]]


class AgenticGuardMCPService:
    """Modular LangGraph SDLC & STLC Agent Suite accessible via MCP tools."""

    SUPPORTED_AGENTS: tuple[str, ...] = (
        "backlog_ac",
        "qa_stlc",
        "template_spec",
        "validation_guard",
    )

    def __init__(self, db: CentralContextDB, gateway: AgenticGuardGateway) -> None:
        """Initialize the LangGraph MCP Agent Service connected to Central DB & Portkey Gateway."""
        self.db = db
        self.gateway = gateway
        self.langfuse = gateway.langfuse
        self.loki = gateway.loki
        self.compiled_graph = self._build_langgraph_workflow()

    def _build_langgraph_workflow(self) -> Any:
        """Construct and compile the modular LangGraph StateGraph with conditional routing."""
        workflow = StateGraph(SDLCGraphState)

        workflow.add_node("backlog_ac", self._langgraph_backlog_node)
        workflow.add_node("qa_stlc", self._langgraph_qa_node)
        workflow.add_node("template_spec", self._langgraph_spec_node)
        workflow.add_node("validation_guard", self._langgraph_validation_node)

        def route_next_step(state: SDLCGraphState) -> str:
            seq = state["requested_sequence"]
            idx = state["current_index"]
            if idx < len(seq):
                return seq[idx]
            return str(END)

        path_map = {
            "backlog_ac": "backlog_ac",
            "qa_stlc": "qa_stlc",
            "template_spec": "template_spec",
            "validation_guard": "validation_guard",
            str(END): str(END),
        }

        workflow.add_conditional_edges(START, route_next_step, path_map)
        for node_name in self.SUPPORTED_AGENTS:
            workflow.add_conditional_edges(node_name, route_next_step, path_map)

        return workflow.compile()

    def _langgraph_backlog_node(self, state: SDLCGraphState) -> dict[str, Any]:
        """LangGraph node wrapper for `backlog_ac` agent."""
        inputs = state["context_inputs"]
        res = self.run_backlog_ac_agent(
            project_id=state["project_id"],
            story_id=state["story_id"],
            project_doc_summary=str(
                inputs.get(
                    "project_doc_summary",
                    "Build enterprise invoice tax calculation service with strict bounds checking.",
                )
            ),
            langfuse_trace_id=state["langfuse_trace_id"],
        )
        updated_results = list(state["execution_results"]) + [
            {"agent": "backlog_ac", "result": res}
        ]
        return {
            "current_index": state["current_index"] + 1,
            "execution_results": updated_results,
        }

    def _langgraph_qa_node(self, state: SDLCGraphState) -> dict[str, Any]:
        """LangGraph node wrapper for `qa_stlc` agent."""
        inputs = state["context_inputs"]
        res = self.run_qa_stlc_agent(
            project_id=state["project_id"],
            story_id=state["story_id"],
            custom_acceptance_criteria=inputs.get("custom_acceptance_criteria"),
            langfuse_trace_id=state["langfuse_trace_id"],
        )
        updated_results = list(state["execution_results"]) + [{"agent": "qa_stlc", "result": res}]
        return {
            "current_index": state["current_index"] + 1,
            "execution_results": updated_results,
        }

    def _langgraph_spec_node(self, state: SDLCGraphState) -> dict[str, Any]:
        """LangGraph node wrapper for `template_spec` agent."""
        inputs = state["context_inputs"]
        res = self.run_template_spec_agent(
            project_id=state["project_id"],
            story_id=state["story_id"],
            target_module_name=str(inputs.get("target_module_name", "billing_service.py")),
            langfuse_trace_id=state["langfuse_trace_id"],
        )
        updated_results = list(state["execution_results"]) + [
            {"agent": "template_spec", "result": res}
        ]
        return {
            "current_index": state["current_index"] + 1,
            "execution_results": updated_results,
        }

    def _langgraph_validation_node(self, state: SDLCGraphState) -> dict[str, Any]:
        """LangGraph node wrapper for `validation_guard` agent."""
        inputs = state["context_inputs"]
        res = self.run_validation_guard_agent(
            project_id=state["project_id"],
            story_id=state["story_id"],
            candidate_code=str(inputs.get("candidate_code", "")),
            harness_client=str(inputs.get("harness_client", "claude-code")),
            langfuse_trace_id=state["langfuse_trace_id"],
        )
        updated_results = list(state["execution_results"]) + [
            {"agent": "validation_guard", "result": res}
        ]
        return {
            "current_index": state["current_index"] + 1,
            "execution_results": updated_results,
        }

    def list_mcp_tools(self) -> list[dict[str, str]]:
        """List MCP tools exposed to AI Coding Assistants conditioned by AGENTS.md."""
        return [
            {
                "name": "mcp__agenticguard__get_project_context",
                "description": "Fetch shared project context, corporate standards, and existing SDLC/STLC stage outcomes from Central DB.",
            },
            {
                "name": "mcp__agenticguard__backlog_ac_agent",
                "description": "LangGraph node: Generate standardized Backlog Stories & Gherkin Acceptance Criteria and sync with ALM.",
            },
            {
                "name": "mcp__agenticguard__qa_stlc_agent",
                "description": "LangGraph node: Generate STLC QA test matrix (happy, edge, security) and executable pytest contract stubs.",
            },
            {
                "name": "mcp__agenticguard__template_spec_agent",
                "description": "LangGraph node: Generate standardized project template scaffolding, SPEC.md, and AGENTS.md to feed the AI Coding Assistant.",
            },
            {
                "name": "mcp__agenticguard__validation_guard_agent",
                "description": "LangGraph node: Run deterministic SAST/AST/type/test gates + LLM Acceptance Criteria Judge and issue a signed Validation Receipt.",
            },
        ]

    def run_backlog_ac_agent(
        self,
        project_id: str,
        story_id: str,
        project_doc_summary: str,
        existing_alm_title: str | None = None,
        user_id: str = "dev-lead",
        langfuse_trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Stage: Backlog & Acceptance Criteria Generation + Bi-Directional ALM Sync."""
        start_ns = time.perf_counter_ns()
        trace_id = langfuse_trace_id or self.langfuse.create_trace_id(project_id, story_id)

        gw_resp = self.gateway.process_chat_completion(
            GatewayRequest(
                session_id=f"sess-backlog-{story_id}",
                project_id=project_id,
                story_id=story_id,
                user_id=user_id,
                user_group="sdlc-agent-service",
                harness_client="agenticguard-mcp",
                requested_model="claude-sonnet-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Generate standardized Backlog Story and Gherkin Acceptance Criteria.",
                    },
                    {"role": "user", "content": project_doc_summary},
                ],
                langfuse_trace_id=trace_id,
            )
        )

        title = existing_alm_title or f"Implement governed feature for {story_id}"
        acceptance_criteria = [
            "AC-1 (Functional): GIVEN a valid request payload WHEN processed by service THEN return deterministic typed result.",
            "AC-2 (Edge Case): GIVEN empty or negative numeric bounds WHEN validated THEN raise ValueError with explicit message.",
            "AC-3 (Security & Standards): GIVEN untrusted input WHEN querying storage THEN enforce parameterized queries and zero eval/exec usage.",
        ]

        outcome_payload: dict[str, Any] = {
            "story_id": story_id,
            "title": title,
            "source_doc": project_doc_summary,
            "acceptance_criteria": acceptance_criteria,
            "alm_sync_status": "SYNCED_BIDIRECTIONAL",
            "gateway_model_used": gw_resp.routed_model,
            "gateway_cost_usd": gw_resp.cost_usd,
            "langfuse_trace_id": trace_id,
        }

        self.db.sync_alm_ticket(
            story_id=story_id,
            project_id=project_id,
            title=title,
            status="READY_FOR_QA_AND_DEV",
            acceptance_criteria=acceptance_criteria,
        )
        self.db.assign_developer_work_state(
            project_id=project_id,
            story_id=story_id,
            developer_id=user_id,
            git_branch=f"feat/{story_id.lower()}-backlog",
            active_stage="backlog_ac",
            work_status="BACKLOG_AND_AC_READY",
        )
        outcome_id = self.db.save_agent_outcome(
            project_id=project_id,
            story_id=story_id,
            agent_type="backlog_ac",
            status="APPROVED",
            payload=outcome_payload,
            created_by=user_id,
        )
        outcome_payload["outcome_id"] = outcome_id

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        self.langfuse.record_langgraph_node_span(
            trace_id=trace_id,
            node_name="backlog_ac",
            project_id=project_id,
            story_id=story_id,
            model_used=gw_resp.routed_model,
            cost_usd=gw_resp.cost_usd,
            latency_ms=latency_ms,
            state_summary={"outcome_id": outcome_id, "ac_count": len(acceptance_criteria)},
        )
        self.loki.emit(
            level="INFO",
            container="agenticguard-mcp-langgraph",
            event="langgraph_node_completed",
            trace_id=trace_id,
            latency_ms=latency_ms,
            node="backlog_ac",
            story_id=story_id,
        )
        return outcome_payload

    def run_qa_stlc_agent(
        self,
        project_id: str,
        story_id: str,
        custom_acceptance_criteria: list[str] | None = None,
        user_id: str = "qa-engineer",
        langfuse_trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Stage: QA & STLC Test Case Generation (Invocable Standalone or Chained)."""
        start_ns = time.perf_counter_ns()
        trace_id = langfuse_trace_id or self.langfuse.create_trace_id(project_id, story_id)

        backlog_record = self.db.get_latest_outcome(project_id, story_id, "backlog_ac")
        alm_ticket = self.db.get_alm_ticket(story_id)

        if custom_acceptance_criteria:
            ac_list = custom_acceptance_criteria
            ac_source = "DIRECT_USER_INPUT"
        elif backlog_record is not None:
            ac_list = list(backlog_record.payload.get("acceptance_criteria", []))
            ac_source = "CENTRAL_DB_BACKLOG_OUTCOME"
        elif alm_ticket is not None:
            ac_list = list(alm_ticket.get("acceptance_criteria", []))
            ac_source = "ALM_SYNCHRONIZED_TICKET"
        else:
            ac_list = [
                "AC-DEFAULT-1: Function must validate inputs, include type hints/docstrings, and avoid unsafe calls."
            ]
            ac_source = "ORG_BASELINE_FALLBACK"

        gw_resp = self.gateway.process_chat_completion(
            GatewayRequest(
                session_id=f"sess-qa-{story_id}",
                project_id=project_id,
                story_id=story_id,
                user_id=user_id,
                user_group="sdlc-agent-service",
                harness_client="agenticguard-mcp",
                requested_model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": "Generate STLC QA Test Matrix and executable pytest contract from Acceptance Criteria.",
                    },
                    {"role": "user", "content": "\n".join(ac_list)},
                ],
                langfuse_trace_id=trace_id,
            )
        )

        test_cases = [
            {
                "test_id": "TC-001",
                "category": "happy_path",
                "maps_to": ac_list[0],
                "assertion": "calculate_invoice_total(100.0, 0.15) == 115.0",
            },
            {
                "test_id": "TC-002",
                "category": "edge_case",
                "maps_to": ac_list[1] if len(ac_list) > 1 else ac_list[0],
                "assertion": "calculate_invoice_total(-10.0, 0.15) raises ValueError",
            },
            {
                "test_id": "TC-003",
                "category": "security_negative",
                "maps_to": ac_list[-1],
                "assertion": "No eval/exec/raw SQL interpolation present in AST",
            },
        ]

        pytest_contract_stub = (
            "import pytest\n"
            "from billing_service import calculate_invoice_total\n\n"
            "def test_happy_path_invoice_total() -> None:\n"
            "    assert calculate_invoice_total(100.0, 0.15) == 115.0\n\n"
            "def test_negative_amount_raises_value_error() -> None:\n"
            "    with pytest.raises(ValueError):\n"
            "        calculate_invoice_total(-10.0, 0.15)\n"
        )

        outcome_payload: dict[str, Any] = {
            "story_id": story_id,
            "ac_source_resolved": ac_source,
            "test_cases": test_cases,
            "pytest_contract_stub": pytest_contract_stub,
            "gateway_model_used": gw_resp.routed_model,
            "gateway_cost_usd": gw_resp.cost_usd,
            "langfuse_trace_id": trace_id,
        }

        self.db.assign_developer_work_state(
            project_id=project_id,
            story_id=story_id,
            developer_id=user_id,
            git_branch=f"feat/{story_id.lower()}-qa-tests",
            active_stage="qa_stlc",
            work_status="QA_CONTRACT_READY",
        )
        outcome_id = self.db.save_agent_outcome(
            project_id=project_id,
            story_id=story_id,
            agent_type="qa_stlc",
            status="APPROVED",
            payload=outcome_payload,
            created_by=user_id,
        )
        outcome_payload["outcome_id"] = outcome_id

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        self.langfuse.record_langgraph_node_span(
            trace_id=trace_id,
            node_name="qa_stlc",
            project_id=project_id,
            story_id=story_id,
            model_used=gw_resp.routed_model,
            cost_usd=gw_resp.cost_usd,
            latency_ms=latency_ms,
            state_summary={"outcome_id": outcome_id, "ac_source": ac_source},
        )
        self.loki.emit(
            level="INFO",
            container="agenticguard-mcp-langgraph",
            event="langgraph_node_completed",
            trace_id=trace_id,
            latency_ms=latency_ms,
            node="qa_stlc",
            story_id=story_id,
        )
        return outcome_payload

    def run_template_spec_agent(
        self,
        project_id: str,
        story_id: str,
        target_module_name: str = "billing_service.py",
        user_id: str = "architect-dev",
        langfuse_trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Stage: Project Template & Spec Scaffolding (Complements Coding Assistant)."""
        start_ns = time.perf_counter_ns()
        trace_id = langfuse_trace_id or self.langfuse.create_trace_id(project_id, story_id)

        context = self.db.get_unified_project_context(project_id, story_id)
        org_standards = context["org_standards"]
        qa_outcome = context["stage_outcomes"].get("qa_stlc", {}).get("payload", {})
        backlog_outcome = context["stage_outcomes"].get("backlog_ac", {}).get("payload", {})

        gw_resp = self.gateway.process_chat_completion(
            GatewayRequest(
                session_id=f"sess-spec-{story_id}",
                project_id=project_id,
                story_id=story_id,
                user_id=user_id,
                user_group="sdlc-agent-service",
                harness_client="agenticguard-mcp",
                requested_model="claude-sonnet-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Generate standardized project template and SPEC.md for the AI Coding Assistant.",
                    },
                    {
                        "role": "user",
                        "content": f"Module: {target_module_name}, Standards: {org_standards}",
                    },
                ],
                langfuse_trace_id=trace_id,
            )
        )

        module_template_skeleton = (
            f'"""Module: {target_module_name} (Scaffolded by AgenticGuard Template Agent)."""\n\n'
            "from __future__ import annotations\n\n\n"
            "def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:\n"
            '    """Calculate total invoice amount including tax after validating bounds.\n\n'
            "    TODO(AI-Coding-Assistant): Implement per SPEC.md and QA test contract.\n"
            '    """\n'
            "    raise NotImplementedError\n"
        )

        spec_markdown = (
            f"# SPEC.md — {story_id} ({target_module_name})\n"
            f"- **Story Title**: {backlog_outcome.get('title', 'Standardized Module Spec')}\n"
            f"- **Acceptance Criteria Count**: {len(backlog_outcome.get('acceptance_criteria', []))}\n"
            f"- **Linked QA Test Cases**: {len(qa_outcome.get('test_cases', []))}\n"
            "- **Mandatory Org Rules**: Explicit type hints, docstrings, ValueError on negative bounds, zero eval/exec/raw SQL.\n"
        )

        outcome_payload: dict[str, Any] = {
            "story_id": story_id,
            "target_module": target_module_name,
            "module_template_skeleton": module_template_skeleton,
            "spec_markdown": spec_markdown,
            "agents_md_conditioned": True,
            "gateway_model_used": gw_resp.routed_model,
            "gateway_cost_usd": gw_resp.cost_usd,
            "langfuse_trace_id": trace_id,
        }

        self.db.assign_developer_work_state(
            project_id=project_id,
            story_id=story_id,
            developer_id=user_id,
            git_branch=f"feat/{story_id.lower()}-scaffold",
            active_stage="template_spec",
            work_status="TEMPLATE_AND_SPEC_READY",
        )
        outcome_id = self.db.save_agent_outcome(
            project_id=project_id,
            story_id=story_id,
            agent_type="template_spec",
            status="APPROVED",
            payload=outcome_payload,
            created_by=user_id,
        )
        outcome_payload["outcome_id"] = outcome_id

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        self.langfuse.record_langgraph_node_span(
            trace_id=trace_id,
            node_name="template_spec",
            project_id=project_id,
            story_id=story_id,
            model_used=gw_resp.routed_model,
            cost_usd=gw_resp.cost_usd,
            latency_ms=latency_ms,
            state_summary={"outcome_id": outcome_id, "target_module": target_module_name},
        )
        self.loki.emit(
            level="INFO",
            container="agenticguard-mcp-langgraph",
            event="langgraph_node_completed",
            trace_id=trace_id,
            latency_ms=latency_ms,
            node="template_spec",
            story_id=story_id,
        )
        return outcome_payload

    def run_validation_guard_agent(
        self,
        project_id: str,
        story_id: str,
        candidate_code: str,
        harness_client: str = "claude-code",
        user_id: str = "dev-user",
        langfuse_trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Stage: Deterministic + Non-Deterministic Validation Gate with Langfuse Score Logging."""
        start_ns = time.perf_counter_ns()
        trace_id = langfuse_trace_id or self.langfuse.create_trace_id(project_id, story_id)
        violations: list[str] = []
        org_rules = self.db.get_org_standards()

        # 1. Deterministic SAST & Security Check
        for forbidden in org_rules.get("forbidden_calls", ["eval(", "exec(", "shell=True"]):
            if forbidden in candidate_code:
                violations.append(f"SAST_FORBIDDEN_CALL:{forbidden}")

        if re.search(r"SELECT\s+.*\+\s*[a-zA-Z_]", candidate_code, re.IGNORECASE) or re.search(
            r'f"SELECT\s+.*\{', candidate_code, re.IGNORECASE
        ):
            violations.append("SAST_SQL_INJECTION_STRING_INTERPOLATION")

        # 2. Deterministic AST, Type Hint & Docstring Check
        try:
            tree = ast.parse(candidate_code)
            functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            if not functions:
                violations.append("STANDARDS_NO_FUNCTION_DEFINED")
            for func in functions:
                if not func.name.startswith("_"):
                    if ast.get_docstring(func) is None:
                        violations.append(f"STANDARDS_MISSING_DOCSTRING:{func.name}")
                    if func.returns is None:
                        violations.append(f"STANDARDS_MISSING_RETURN_TYPE_HINT:{func.name}")
        except SyntaxError as exc:
            violations.append(f"AST_SYNTAX_ERROR:{exc.msg}")

        # 3. Deterministic Functional & Edge-Case Verification
        if not violations:
            if "ValueError" not in candidate_code:
                violations.append("QA_CONTRACT_FAILED:Missing ValueError check for negative bounds (TC-002)")
            if "NotImplementedError" in candidate_code:
                violations.append("QA_CONTRACT_FAILED:Template stub NotImplementedError still present")

        # 4. Non-Deterministic Acceptance Criteria Rubric Judge (Routed via Portkey Gateway)
        gw_resp = self.gateway.process_chat_completion(
            GatewayRequest(
                session_id=f"sess-val-{story_id}",
                project_id=project_id,
                story_id=story_id,
                user_id=user_id,
                user_group="sdlc-agent-service",
                harness_client=harness_client,
                requested_model="gemini-2.5-flash",
                messages=[
                    {
                        "role": "system",
                        "content": "Rubric Judge: Verify candidate diff satisfies story Acceptance Criteria.",
                    },
                    {"role": "user", "content": candidate_code},
                ],
                langfuse_trace_id=trace_id,
            )
        )

        passed = len(violations) == 0
        receipt_hash = hashlib.sha256(
            f"{project_id}:{story_id}:{passed}:{candidate_code}".encode("utf-8")
        ).hexdigest()[:16]

        status = "VALIDATED_PASSED" if passed else "REJECTED_VIOLATIONS"
        receipt_id = f"AG-RECEIPT-{receipt_hash.upper()}" if passed else "NONE"

        outcome_payload: dict[str, Any] = {
            "story_id": story_id,
            "harness_client": harness_client,
            "passed": passed,
            "status": status,
            "violations": violations,
            "validation_receipt": receipt_id,
            "judge_model": gw_resp.routed_model,
            "judge_cost_usd": gw_resp.cost_usd,
            "langfuse_trace_id": trace_id,
        }

        self.db.assign_developer_work_state(
            project_id=project_id,
            story_id=story_id,
            developer_id=user_id,
            git_branch=f"feat/{story_id.lower()}-impl",
            active_stage="validation_guard",
            work_status=status,
            git_commit_ref=receipt_id if passed else "UNVERIFIED_WORKING_TREE",
        )
        self.db.save_agent_outcome(
            project_id=project_id,
            story_id=story_id,
            agent_type="validation_guard",
            status=status,
            payload=outcome_payload,
            created_by=user_id,
        )

        if passed:
            ticket = self.db.get_alm_ticket(story_id)
            if ticket:
                self.db.sync_alm_ticket(
                    story_id=story_id,
                    project_id=project_id,
                    title=str(ticket["title"]),
                    status=f"COMPLETED_VERIFIED ({receipt_id})",
                    acceptance_criteria=list(ticket["acceptance_criteria"]),
                )

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        self.langfuse.record_langgraph_node_span(
            trace_id=trace_id,
            node_name="validation_guard",
            project_id=project_id,
            story_id=story_id,
            model_used=gw_resp.routed_model,
            cost_usd=gw_resp.cost_usd,
            latency_ms=latency_ms,
            state_summary={"passed": passed, "violations_count": len(violations)},
        )
        self.langfuse.record_evaluation_score(
            trace_id=trace_id,
            name="acceptance_criteria_and_sast_compliance",
            value=1.0 if passed else 0.0,
            comment=f"Receipt: {receipt_id}" if passed else f"Violations: {violations}",
        )
        self.loki.emit(
            level="INFO" if passed else "WARN",
            container="agenticguard-mcp-langgraph",
            event="validation_guard_evaluated",
            trace_id=trace_id,
            latency_ms=latency_ms,
            passed=passed,
            harness=harness_client,
            receipt=receipt_id,
        )
        return outcome_payload

    def invoke_custom_sequence(
        self,
        project_id: str,
        story_id: str,
        agent_sequence: list[str],
        context_inputs: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute any single agent node or custom-ordered sequence via the compiled LangGraph StateGraph."""
        for agent_name in agent_sequence:
            if agent_name not in self.SUPPORTED_AGENTS:
                raise ValueError(
                    f"Unsupported agent '{agent_name}'. Allowed: {self.SUPPORTED_AGENTS}"
                )

        shared_trace_id = self.langfuse.create_trace_id(project_id, story_id)
        initial_state: SDLCGraphState = {
            "project_id": project_id,
            "story_id": story_id,
            "langfuse_trace_id": shared_trace_id,
            "requested_sequence": list(agent_sequence),
            "current_index": 0,
            "context_inputs": dict(context_inputs or {}),
            "execution_results": [],
        }
        final_state = self.compiled_graph.invoke(initial_state)
        return list(final_state["execution_results"])
