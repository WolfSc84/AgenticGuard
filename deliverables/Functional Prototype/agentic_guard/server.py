"""Containerized HTTP Server Entrypoint for AgenticGuard Layer (Gateway + MCP Service).

Exposes both the OpenAI-compatible AI Gateway (`/v1/chat/completions`) and the
Containerized Modular SDLC/STLC Agent MCP endpoints (`/mcp`, `/mcp/tools`, `/mcp/invoke`,
`/context/{project_id}/{story_id}`) using Python's standard library HTTP server,
ensuring zero-friction, production-grade execution in any environment.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from agentic_guard.agents_mcp import AgenticGuardMCPService
from agentic_guard.db import CentralContextDB
from agentic_guard.gateway import AgenticGuardGateway, GatewayRequest


class AgenticGuardHTTPHandler(BaseHTTPRequestHandler):
    """Unified HTTP handler for the AI Gateway and Containerized MCP Agent Service."""

    db: CentralContextDB = CentralContextDB(
        os.getenv("AGENTICGUARD_DB_PATH", "agentic_guard.db")
    )
    gateway: AgenticGuardGateway = AgenticGuardGateway(db)
    mcp_service: AgenticGuardMCPService = AgenticGuardMCPService(db, gateway)

    def address_string(self) -> str:
        """Prevent slow reverse DNS lookups on client address."""
        return str(self.client_address[0])

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging during high-throughput execution."""
        return

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        """Serialize and write a JSON HTTP response."""
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests for health, MCP tool discovery, context, and telemetry scorecards."""
        path_clean = self.path.split("?")[0].rstrip("/")

        if path_clean == "/health":
            self._send_json(200, {"status": "healthy", "service": "AgenticGuard-Layer"})
        elif path_clean in ("/mcp", "/mcp/tools"):
            self._send_json(200, {"tools": self.mcp_service.list_mcp_tools()})
        elif path_clean == "/v1/telemetry/scorecard":
            self._send_json(
                200,
                {"harness_scorecard": self.db.get_harness_efficiency_scorecard()},
            )
        elif path_clean.startswith("/context/"):
            # Format: /context/{project_id}/{story_id}
            parts = [p for p in path_clean.strip("/").split("/") if p]
            if len(parts) >= 3:
                project_id, story_id = parts[1], parts[2]
                ctx = self.db.get_unified_project_context(project_id, story_id)
                self._send_json(
                    200,
                    {
                        "project_id": project_id,
                        "story_id": story_id,
                        "context": ctx,
                    },
                )
            else:
                self._send_json(
                    400,
                    {"error": "Invalid format. Expected /context/{project_id}/{story_id}"},
                )
        else:
            self._send_json(404, {"error": f"Endpoint '{self.path}' not found"})

    def do_POST(self) -> None:  # noqa: N802
        """Handle POST requests for `/v1/chat/completions`, `/mcp/invoke`, and MCP JSON-RPC `/mcp`."""
        content_len = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        path_clean = self.path.split("?")[0].rstrip("/")

        if path_clean == "/v1/chat/completions":
            req = GatewayRequest(
                session_id=str(data.get("session_id", "http-sess")),
                project_id=str(data.get("project_id", "PROJ-DEFAULT")),
                story_id=str(data.get("story_id", "STORY-1")),
                user_id=str(data.get("user_id", "dev-1")),
                user_group=str(data.get("user_group", "junior-dev")),
                harness_client=str(data.get("harness_client", "cursor")),
                requested_model=str(data.get("model", "claude-sonnet-4")),
                messages=list(data.get("messages", [])),
            )
            resp = self.gateway.process_chat_completion(req)
            self._send_json(
                resp.status_code,
                {
                    "allowed": resp.allowed,
                    "routed_model": resp.routed_model,
                    "provider": resp.provider,
                    "guardrail_action": resp.guardrail_action,
                    "cost_usd": resp.cost_usd,
                    "choices": [{"message": {"role": "assistant", "content": resp.content}}],
                },
            )
        elif path_clean in ("/mcp", "/mcp/invoke"):
            # Check if this is a standard JSON-RPC 2.0 MCP request
            if isinstance(data, dict) and data.get("jsonrpc") == "2.0":
                method = data.get("method")
                req_id = data.get("id")
                if method == "tools/list":
                    self._send_json(
                        200,
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {"tools": self.mcp_service.list_mcp_tools()},
                        },
                    )
                    return
                elif method == "tools/call":
                    params = data.get("params", {})
                    tool_name = params.get("name", "")
                    args = params.get("arguments", {})
                    project_id = str(args.get("project_id", "PROJ-DEFAULT"))
                    story_id = str(args.get("story_id", "STORY-1"))

                    if tool_name == "mcp__agenticguard__get_project_context":
                        ctx = self.db.get_unified_project_context(project_id, story_id)
                        self._send_json(
                            200,
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": {
                                    "content": [{"type": "text", "text": json.dumps(ctx, indent=2)}]
                                },
                            },
                        )
                        return
                    else:
                        agent_key = (
                            tool_name.replace("mcp__agenticguard__", "").replace("_agent", "")
                        )
                        if agent_key in self.mcp_service.SUPPORTED_AGENTS:
                            results = self.mcp_service.invoke_custom_sequence(
                                project_id=project_id,
                                story_id=story_id,
                                agent_sequence=[agent_key],
                                context_inputs=args,
                            )
                            self._send_json(
                                200,
                                {
                                    "jsonrpc": "2.0",
                                    "id": req_id,
                                    "result": {
                                        "content": [
                                            {"type": "text", "text": json.dumps(results, indent=2)}
                                        ]
                                    },
                                },
                            )
                            return
                        else:
                            self._send_json(
                                404,
                                {
                                    "jsonrpc": "2.0",
                                    "id": req_id,
                                    "error": {
                                        "code": -32601,
                                        "message": f"Tool '{tool_name}' not recognized.",
                                    },
                                },
                            )
                            return

            # REST-style invocation fallback
            project_id = str(data.get("project_id", "PROJ-DEFAULT"))
            story_id = str(data.get("story_id", "STORY-1"))
            sequence = list(data.get("agent_sequence", ["backlog_ac"]))
            inputs = dict(data.get("inputs", {}))
            try:
                results = self.mcp_service.invoke_custom_sequence(
                    project_id=project_id,
                    story_id=story_id,
                    agent_sequence=sequence,
                    context_inputs=inputs,
                )
                self._send_json(
                    200,
                    {
                        "project_id": project_id,
                        "story_id": story_id,
                        "results": results,
                    },
                )
            except Exception as exc:
                self._send_json(400, {"error": str(exc)})
        else:
            self._send_json(404, {"error": f"Endpoint '{self.path}' not found"})


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the containerized AgenticGuard HTTP server."""
    server = HTTPServer((host, port), AgenticGuardHTTPHandler)
    print(f"AgenticGuard Layer listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    env_host = os.getenv("HOST", "127.0.0.1")
    env_port = int(os.getenv("PORT", "8000"))
    run_server(host=env_host, port=env_port)
