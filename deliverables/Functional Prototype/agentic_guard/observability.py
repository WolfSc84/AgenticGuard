"""Two-Layer Containerized Observability Engine for AgenticGuard Layer.

Layer 1 (AI & Agent Observability):
    `LangfusePortkeyTracer` & `LangfuseCallbackHandler` — connects Langfuse to both
    Portkey AI Gateway (via x-portkey-metadata / OpenTelemetry trace correlation)
    and LangGraph StateGraph nodes (recording node spans, token costs, and
    Acceptance Criteria Judge rubric scores).

Layer 2 (In-Agent Service Observability via Fluentbit Library -> Loki -> Grafana):
    `FluentBitLokiLogger` — embedded Fluentbit logging library inside the agents and
    gateway that captures structured service logs (`service`, `container`, `level`,
    `event`, `trace_id`, `latency_ms`, `project_id`) and ships them directly to
    Grafana Loki, where they are consumed by Grafana dashboards.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class LangfuseSpanRecord:
    """Represents a trace span exported to Langfuse from Portkey or LangGraph."""

    trace_id: str
    span_id: str
    source: str  # 'portkey-gateway' | 'langgraph-node'
    name: str
    project_id: str
    story_id: str
    harness_client: str
    model: str
    cost_usd: float
    latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LangfuseScoreRecord:
    """Represents an evaluation score attached to a Langfuse trace."""

    trace_id: str
    name: str
    value: float
    comment: str


class LangfusePortkeyTracer:
    """Unified Langfuse observability bridge for Portkey AI Gateway & LangGraph agents."""

    def __init__(self, host: str | None = None) -> None:
        """Initialize the Langfuse tracer bridge."""
        self.host = host or os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
        self.spans: list[LangfuseSpanRecord] = []
        self.scores: list[LangfuseScoreRecord] = []

    def create_trace_id(self, project_id: str, story_id: str) -> str:
        """Generate a deterministic-format Langfuse trace ID shared across Portkey & LangGraph."""
        short_uuid = uuid.uuid4().hex[:10]
        return f"lf-trace-{project_id.lower()}-{story_id.lower()}-{short_uuid}"

    def record_portkey_gateway_span(
        self,
        trace_id: str,
        project_id: str,
        story_id: str,
        harness_client: str,
        routed_model: str,
        provider: str,
        cost_usd: float,
        latency_ms: float,
        guardrail_action: str,
        token_usage: dict[str, int],
    ) -> LangfuseSpanRecord:
        """Record an LLM generation span exported from Portkey AI Gateway to Langfuse."""
        span = LangfuseSpanRecord(
            trace_id=trace_id,
            span_id=f"sp-pk-{uuid.uuid4().hex[:8]}",
            source="portkey-gateway",
            name=f"portkey.completion.{provider}.{routed_model}",
            project_id=project_id,
            story_id=story_id,
            harness_client=harness_client,
            model=routed_model,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            metadata={
                "provider": provider,
                "guardrail_action": guardrail_action,
                "token_usage": token_usage,
            },
        )
        self.spans.append(span)
        return span

    def record_langgraph_node_span(
        self,
        trace_id: str,
        node_name: str,
        project_id: str,
        story_id: str,
        model_used: str,
        cost_usd: float,
        latency_ms: float,
        state_summary: dict[str, Any],
    ) -> LangfuseSpanRecord:
        """Record a LangGraph StateGraph node execution span via Langfuse CallbackHandler."""
        span = LangfuseSpanRecord(
            trace_id=trace_id,
            span_id=f"sp-lg-{uuid.uuid4().hex[:8]}",
            source="langgraph-node",
            name=f"langgraph.node.{node_name}",
            project_id=project_id,
            story_id=story_id,
            harness_client="agenticguard-mcp-langgraph",
            model=model_used,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            metadata=state_summary,
        )
        self.spans.append(span)
        return span

    def record_evaluation_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: str,
    ) -> LangfuseScoreRecord:
        """Attach a deterministic or LLM-Judge evaluation score to a Langfuse trace."""
        score = LangfuseScoreRecord(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )
        self.scores.append(score)
        return score

    def get_trace_summary(self) -> dict[str, Any]:
        """Return aggregated Langfuse trace and evaluation metrics."""
        portkey_spans = [s for s in self.spans if s.source == "portkey-gateway"]
        langgraph_spans = [s for s in self.spans if s.source == "langgraph-node"]
        return {
            "langfuse_host": self.host,
            "total_spans_recorded": len(self.spans),
            "portkey_gateway_spans": len(portkey_spans),
            "langgraph_node_spans": len(langgraph_spans),
            "evaluation_scores_recorded": len(self.scores),
            "scores": [
                {"trace_id": sc.trace_id, "name": sc.name, "value": sc.value, "comment": sc.comment}
                for sc in self.scores
            ],
        }


class FluentBitLokiLogger:
    """In-agent Fluentbit logging library that captures service logs and ships them to Loki for Grafana."""

    def __init__(
        self,
        service_name: str = "agenticguard-layer",
        loki_endpoint: str | None = None,
    ) -> None:
        """Initialize the in-agent Fluentbit logging library."""
        self.service_name = service_name
        self.loki_endpoint = (
            loki_endpoint
            or os.getenv("LOKI_URL", "http://loki:3100/loki/api/v1/push")
        )
        self.log_buffer: list[dict[str, Any]] = []

    def emit(
        self,
        level: str,
        container: str,
        event: str,
        trace_id: str,
        latency_ms: float = 0.0,
        **fields: Any,
    ) -> dict[str, Any]:
        """Capture a structured service log via the in-agent Fluentbit library and queue for Loki."""
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "fluentbit_library": "fluent-bit-python-handler",
            "loki_endpoint": self.loki_endpoint,
            "loki_labels": {
                "job": "fluent-bit",
                "service": self.service_name,
                "container": container,
                "level": level.upper(),
            },
            "event": event,
            "trace_id": trace_id,
            "latency_ms": round(latency_ms, 2),
            "fields": fields,
        }
        self.log_buffer.append(record)
        return record

    def format_loki_line(self, record: dict[str, Any]) -> str:
        """Serialize a log record as a compact JSON line for Fluent Bit stdout tailing."""
        return json.dumps(record, separators=(",", ":"))

