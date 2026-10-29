"""Unit and Integration Tests for AgenticGuard Layer MVP.

Tests Portkey AI Gateway, LangGraph StateGraph modular agents, Central Context DB,
Langfuse trace/score correlation, and Fluent Bit -> Loki -> Grafana structured logging.
"""

from __future__ import annotations

import json
import unittest

from agentic_guard.agents_mcp import AgenticGuardMCPService
from agentic_guard.db import CentralContextDB
from agentic_guard.gateway import AgenticGuardGateway, GatewayRequest


class TestAgenticGuardLayer(unittest.TestCase):
    """Test suite verifying the AgenticGuard Layer MVP components."""

    def setUp(self) -> None:
        """Initialize an isolated in-memory AgenticGuard Layer instance."""
        self.db = CentralContextDB(":memory:")
        self.db.register_project(
            project_id="PROJ-TEST",
            name="Test Project",
            domain="enterprise-core",
            alm_provider="Linear",
            shared_context={"stack": "Python 3.12"},
        )
        self.gateway = AgenticGuardGateway(self.db)
        self.mcp = AgenticGuardMCPService(self.db, self.gateway)

    def test_langgraph_individual_and_custom_order_execution(self) -> None:
        """Verify LangGraph StateGraph executes agents standalone or in custom order."""
        results = self.mcp.invoke_custom_sequence(
            project_id="PROJ-TEST",
            story_id="ST-CUSTOM-1",
            agent_sequence=["template_spec", "backlog_ac", "qa_stlc"],
            context_inputs={"target_module_name": "orders.py"},
        )
        self.assertEqual([r["agent"] for r in results], ["template_spec", "backlog_ac", "qa_stlc"])

        ctx = self.db.get_unified_project_context("PROJ-TEST", "ST-CUSTOM-1")
        self.assertEqual(
            set(ctx["stage_outcomes"].keys()),
            {"template_spec", "backlog_ac", "qa_stlc"},
        )
        self.assertIsNotNone(ctx["alm_ticket"])
        self.assertEqual(ctx["alm_ticket"]["status"], "READY_FOR_QA_AND_DEV")

    def test_standalone_qa_agent_graceful_resolution(self) -> None:
        """Verify a single LangGraph node (qa_stlc) works standalone without prior backlog DB state."""
        res = self.mcp.run_qa_stlc_agent(
            project_id="PROJ-TEST",
            story_id="ST-STANDALONE-QA",
            custom_acceptance_criteria=["AC-1: Must validate positive integers."],
        )
        self.assertEqual(res["ac_source_resolved"], "DIRECT_USER_INPUT")
        self.assertEqual(len(res["test_cases"]), 3)

    def test_portkey_before_request_hooks_block_secrets_and_env_files(self) -> None:
        """Verify Portkey deterministic `before_request_hooks` block leaked credentials and .env files."""
        secret_req = GatewayRequest(
            session_id="s-1",
            project_id="PROJ-TEST",
            story_id="ST-1",
            user_id="dev-1",
            user_group="senior-eng",
            harness_client="cursor",
            requested_model="claude-sonnet-4",
            messages=[{"role": "user", "content": "My key is AKIA1234567890ABCDEF"}],
        )
        resp = self.gateway.process_chat_completion(secret_req)
        self.assertFalse(resp.allowed)
        self.assertEqual(resp.status_code, 446)
        self.assertIn("PORTKEY_HOOK_DENY_DLP_SECRET:AWS_ACCESS_KEY", resp.guardrail_action)

        env_req = GatewayRequest(
            session_id="s-2",
            project_id="PROJ-TEST",
            story_id="ST-1",
            user_id="dev-1",
            user_group="senior-eng",
            harness_client="claude-code",
            requested_model="claude-sonnet-4",
            messages=[{"role": "user", "content": "Contents of .env.production file"}],
        )
        resp_env = self.gateway.process_chat_completion(env_req)
        self.assertFalse(resp_env.allowed)
        self.assertIn("PORTKEY_HOOK_DENY_RESTRICTED_FILE:.env.production", resp_env.guardrail_action)

    def test_portkey_config_generation_rbac_and_quota(self) -> None:
        """Verify Portkey x-portkey-config headers, RBAC model downgrade, and quota enforcement."""
        req = GatewayRequest(
            session_id="s-rbac",
            project_id="PROJ-TEST",
            story_id="ST-1",
            user_id="junior-1",
            user_group="junior-dev",
            harness_client="cursor",
            requested_model="claude-opus-4",
            messages=[{"role": "user", "content": "Write unit test helper."}],
        )
        resp = self.gateway.process_chat_completion(req)
        self.assertTrue(resp.allowed)
        self.assertEqual(resp.routed_model, "claude-sonnet-4")
        self.assertIn("RBAC_DOWNGRADED:claude-opus-4->claude-sonnet-4", resp.guardrail_action)

        portkey_cfg = json.loads(resp.portkey_headers["x-portkey-config"])
        portkey_meta = json.loads(resp.portkey_headers["x-portkey-metadata"])
        self.assertEqual(portkey_cfg["strategy"]["mode"], "fallback")
        self.assertTrue(portkey_meta["langfuse_trace_id"].startswith("lf-trace-"))

        self.db.log_gateway_call(
            session_id="s-exhaust",
            project_id="PROJ-TEST",
            story_id="ST-1",
            user_id="junior-1",
            user_group="junior-dev",
            harness_client="cursor",
            requested_model="claude-sonnet-4",
            routed_model="claude-sonnet-4",
            provider="aws-bedrock",
            prompt_tokens=1000,
            completion_tokens=1000,
            cached_tokens=0,
            cost_usd=6.00,
            latency_ms=2.0,
        )
        blocked_resp = self.gateway.process_chat_completion(req)
        self.assertFalse(blocked_resp.allowed)
        self.assertEqual(blocked_resp.status_code, 429)
        self.assertIn("BLOCKED_QUOTA_EXCEEDED", blocked_resp.guardrail_action)

    def test_langfuse_and_loki_observability_correlation(self) -> None:
        """Verify Langfuse records both Portkey & LangGraph spans/scores and Fluent Bit/Loki logs."""
        self.mcp.invoke_custom_sequence(
            project_id="PROJ-TEST",
            story_id="ST-OBS",
            agent_sequence=["backlog_ac", "validation_guard"],
            context_inputs={
                "candidate_code": (
                    '"""Module doc."""\n'
                    "def calculate_invoice_total(subtotal: float, tax_rate: float) -> float:\n"
                    '    """Func doc."""\n'
                    "    if subtotal < 0:\n"
                    '        raise ValueError("neg")\n'
                    "    return subtotal * (1.0 + tax_rate)\n"
                )
            },
        )
        lf_summary = self.gateway.langfuse.get_trace_summary()
        self.assertEqual(lf_summary["portkey_gateway_spans"], 2)
        self.assertEqual(lf_summary["langgraph_node_spans"], 2)
        self.assertEqual(lf_summary["evaluation_scores_recorded"], 1)
        self.assertEqual(lf_summary["scores"][0]["value"], 1.0)

        # Verify in-agent Fluentbit logging library -> Loki logs contain required Loki labels
        self.assertGreaterEqual(len(self.gateway.loki.log_buffer), 4)
        sample_log = self.gateway.loki.log_buffer[-1]
        self.assertEqual(sample_log["fluentbit_library"], "fluent-bit-python-handler")
        self.assertEqual(sample_log["loki_labels"]["job"], "fluent-bit")
        self.assertIn("container", sample_log["loki_labels"])

    def test_project_developer_authorization_and_git_complement_traceability(self) -> None:
        """Verify Central DB enforces allowed developers by project_id and tracks feature assignments."""
        self.db.authorize_project_developer("PROJ-TEST", "dev-alice", "senior-eng", "claude-code")
        self.db.authorize_project_developer("PROJ-TEST", "dev-bob", "junior-dev", "cursor")

        self.assertTrue(self.db.is_developer_allowed_in_project("PROJ-TEST", "dev-alice"))
        self.assertFalse(self.db.is_developer_allowed_in_project("PROJ-TEST", "dev-outsider"))

        with self.assertRaises(PermissionError):
            self.db.assign_developer_work_state(
                project_id="PROJ-TEST",
                story_id="ST-TRACE-1",
                developer_id="dev-outsider",
                git_branch="feat/unauthorized",
                active_stage="template_spec",
            )

        self.db.assign_developer_work_state(
            project_id="PROJ-TEST",
            story_id="ST-TRACE-1",
            developer_id="dev-alice",
            git_branch="feat/st-trace-1",
            active_stage="template_spec",
            work_status="IN_PROGRESS",
            git_commit_ref="a1b2c3d",
        )
        matrix = self.db.get_project_traceability_matrix("PROJ-TEST")
        self.assertEqual(len(matrix["allowed_developers"]), 2)
        self.assertEqual(len(matrix["active_feature_assignments"]), 1)
        self.assertEqual(matrix["active_feature_assignments"][0]["developer_id"], "dev-alice")
        self.assertEqual(matrix["active_feature_assignments"][0]["git_branch"], "feat/st-trace-1")

    def test_http_server_endpoints_and_jsonrpc_mcp(self) -> None:
        """Verify the unified HTTP server exposes health, MCP discovery, JSON-RPC, and chat endpoints."""
        import threading
        import time
        import urllib.request
        from http.server import HTTPServer
        from agentic_guard.server import AgenticGuardHTTPHandler

        # Override handler DB to use our test in-memory DB
        AgenticGuardHTTPHandler.db = self.db
        AgenticGuardHTTPHandler.gateway = self.gateway
        AgenticGuardHTTPHandler.mcp_service = self.mcp

        # Pick port 8765 for test server
        server = HTTPServer(("127.0.0.1", 8765), AgenticGuardHTTPHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)

        base_url = "http://127.0.0.1:8765"

        try:
            # 1. Health check
            with urllib.request.urlopen(f"{base_url}/health") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertEqual(data["status"], "healthy")

            # 2. GET /mcp and /mcp/tools
            for path in ("/mcp", "/mcp/tools"):
                with urllib.request.urlopen(f"{base_url}{path}") as resp:
                    self.assertEqual(resp.status, 200)
                    data = json.loads(resp.read().decode())
                    self.assertIn("tools", data)
                    self.assertEqual(len(data["tools"]), 5)

            # 3. GET /context/PROJ-TEST/ST-1
            with urllib.request.urlopen(f"{base_url}/context/PROJ-TEST/ST-1") as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertEqual(data["project_id"], "PROJ-TEST")
                self.assertEqual(data["story_id"], "ST-1")

            # 4. POST /mcp with standard JSON-RPC 2.0 tools/list
            req_data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
            req = urllib.request.Request(f"{base_url}/mcp", data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                res = json.loads(resp.read().decode())
                self.assertEqual(res["jsonrpc"], "2.0")
                self.assertIn("tools", res["result"])

            # 5. POST /mcp with standard JSON-RPC 2.0 tools/call for get_project_context
            req_data = json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "mcp__agenticguard__get_project_context",
                    "arguments": {"project_id": "PROJ-TEST", "story_id": "ST-1"}
                }
            }).encode()
            req = urllib.request.Request(f"{base_url}/mcp", data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                res = json.loads(resp.read().decode())
                self.assertEqual(res["jsonrpc"], "2.0")
                self.assertIn("content", res["result"])

            # 6. POST /v1/chat/completions (Portkey gateway completion)
            chat_data = json.dumps({
                "session_id": "s-test",
                "project_id": "PROJ-TEST",
                "story_id": "ST-1",
                "user_id": "dev-alice",
                "user_group": "senior-eng",
                "harness_client": "claude-code",
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "Help refactor invoice logic."}]
            }).encode()
            req = urllib.request.Request(f"{base_url}/v1/chat/completions", data=chat_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                res = json.loads(resp.read().decode())
                self.assertTrue(res["allowed"])
                self.assertEqual(res["routed_model"], "claude-sonnet-4")

            # 7. POST /v1/chat/completions with DLP violation -> 446
            bad_data = json.dumps({
                "session_id": "s-bad",
                "project_id": "PROJ-TEST",
                "story_id": "ST-1",
                "user_id": "dev-alice",
                "user_group": "senior-eng",
                "harness_client": "cursor",
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "Here is AWS key AKIA0000000000000000"}]
            }).encode()
            req = urllib.request.Request(f"{base_url}/v1/chat/completions", data=bad_data, headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req)
                self.fail("Should have raised HTTP 446")
            except urllib.error.HTTPError as err:
                with err:
                    self.assertEqual(err.code, 446)
                    body = json.loads(err.read().decode())
                    self.assertFalse(body["allowed"])
                    self.assertIn("DLP", body["guardrail_action"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
