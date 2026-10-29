"""Centralized Project Context & Agent Outcomes Database.

Stores organization-wide engineering standards, shared project architectural context,
ALM-synchronized backlog items, modular SDLC/STLC agent outcomes, validation receipts,
and AI Gateway harness telemetry.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generator


@dataclass(frozen=True)
class AgentOutcomeRecord:
    """Represents a persisted outcome from one of the modular SDLC/STLC agents."""

    id: int
    project_id: str
    story_id: str
    agent_type: str
    status: str
    payload: dict[str, Any]
    created_by: str
    created_at: str


class CentralContextDB:
    """Centralized relational store for project context, SDLC/STLC outcomes, and gateway telemetry."""

    def __init__(self, db_path: str = ":memory:") -> None:
        """Initialize the database connection and schema.

        Args:
            db_path: File path to SQLite DB or ':memory:' for in-memory execution.
        """
        self.db_path = db_path
        self._persistent_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed_default_org_standards()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a transactional database connection."""
        if self._persistent_conn is not None:
            try:
                yield self._persistent_conn
                self._persistent_conn.commit()
            except Exception:
                self._persistent_conn.rollback()
                raise
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_schema(self) -> None:
        """Create tables and indexes for multi-developer and cross-project alignment."""
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS org_standards (
                    standard_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    rules_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    alm_provider TEXT NOT NULL,
                    shared_context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS project_developers (
                    project_id TEXT NOT NULL,
                    developer_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    preferred_harness TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 1,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, developer_id),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS developer_work_state (
                    project_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    developer_id TEXT NOT NULL,
                    git_branch TEXT NOT NULL,
                    git_commit_ref TEXT NOT NULL,
                    active_stage TEXT NOT NULL,
                    work_status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, story_id, developer_id),
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS alm_tickets (
                    story_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    acceptance_criteria_json TEXT NOT NULL,
                    synced_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS agent_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_outcomes_lookup
                    ON agent_outcomes(project_id, story_id, agent_type);

                CREATE TABLE IF NOT EXISTS gateway_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_group TEXT NOT NULL,
                    harness_client TEXT NOT NULL,
                    requested_model TEXT NOT NULL,
                    routed_model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    cached_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    blocked_by_guardrail INTEGER NOT NULL,
                    guardrail_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_harness
                    ON gateway_telemetry(harness_client, project_id);
                """
            )

    def _seed_default_org_standards(self) -> None:
        """Seed baseline corporate engineering and security standards."""
        now = datetime.now(timezone.utc).isoformat()
        default_rules = {
            "language": "python",
            "require_type_hints": True,
            "require_docstrings": True,
            "forbidden_calls": ["eval(", "exec(", "shell=True"],
            "require_parameterized_sql": True,
            "min_qa_categories": ["happy_path", "edge_case", "security_negative"],
            "mandatory_files": ["AGENTS.md", "SPEC.md"],
        }
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO org_standards (standard_id, name, rules_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "CORP-STD-001",
                    "Enterprise Python & AI Security Baseline v2.4",
                    json.dumps(default_rules),
                    now,
                ),
            )

    def register_project(
        self,
        project_id: str,
        name: str,
        domain: str,
        alm_provider: str,
        shared_context: dict[str, Any],
        allowed_developers: list[dict[str, str]] | None = None,
    ) -> None:
        """Register or update a project's shared context and allowed developers by project_id."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO projects
                (project_id, name, domain, alm_provider, shared_context_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, domain, alm_provider, json.dumps(shared_context), now),
            )
            if allowed_developers:
                for dev in allowed_developers:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO project_developers
                        (project_id, developer_id, role, preferred_harness, allowed, added_at)
                        VALUES (?, ?, ?, ?, 1, ?)
                        """,
                        (
                            project_id,
                            dev["developer_id"],
                            dev.get("role", "senior-eng"),
                            dev.get("preferred_harness", "cursor"),
                            now,
                        ),
                    )

    def authorize_project_developer(
        self,
        project_id: str,
        developer_id: str,
        role: str = "senior-eng",
        preferred_harness: str = "cursor",
    ) -> None:
        """Register an allowed developer for a specific project_id."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_developers
                (project_id, developer_id, role, preferred_harness, allowed, added_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (project_id, developer_id, role, preferred_harness, now),
            )

    def is_developer_allowed_in_project(self, project_id: str, developer_id: str) -> bool:
        """Verify if a developer is authorized to consume context or work in project_id."""
        with self._connection() as conn:
            total_devs = conn.execute(
                "SELECT COUNT(*) AS cnt FROM project_developers WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if total_devs and int(total_devs["cnt"]) == 0:
                return True
            row = conn.execute(
                """
                SELECT allowed FROM project_developers
                WHERE project_id = ? AND developer_id = ?
                """,
                (project_id, developer_id),
            ).fetchone()
            return bool(row and int(row["allowed"]) == 1)

    def assign_developer_work_state(
        self,
        project_id: str,
        story_id: str,
        developer_id: str,
        git_branch: str,
        active_stage: str,
        work_status: str = "IN_PROGRESS",
        git_commit_ref: str = "HEAD",
    ) -> dict[str, str]:
        """Record which developer is working on which feature/backlog item as a complement to Git."""
        if not self.is_developer_allowed_in_project(project_id, developer_id):
            raise PermissionError(
                f"Developer '{developer_id}' is not authorized in project '{project_id}'."
            )
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO developer_work_state
                (project_id, story_id, developer_id, git_branch, git_commit_ref, active_stage, work_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    story_id,
                    developer_id,
                    git_branch,
                    git_commit_ref,
                    active_stage,
                    work_status,
                    now,
                ),
            )
        return {
            "project_id": project_id,
            "story_id": story_id,
            "developer_id": developer_id,
            "git_branch": git_branch,
            "git_commit_ref": git_commit_ref,
            "active_stage": active_stage,
            "work_status": work_status,
            "updated_at": now,
        }

    def get_project_traceability_matrix(self, project_id: str) -> dict[str, Any]:
        """Return project-wide developer permissions and active feature/backlog assignments (Git complement)."""
        with self._connection() as conn:
            dev_rows = conn.execute(
                "SELECT developer_id, role, preferred_harness, allowed FROM project_developers WHERE project_id = ? ORDER BY developer_id ASC",
                (project_id,),
            ).fetchall()
            work_rows = conn.execute(
                "SELECT story_id, developer_id, git_branch, git_commit_ref, active_stage, work_status, updated_at FROM developer_work_state WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return {
            "project_id": project_id,
            "allowed_developers": [
                {
                    "developer_id": str(r["developer_id"]),
                    "role": str(r["role"]),
                    "preferred_harness": str(r["preferred_harness"]),
                    "allowed": bool(int(r["allowed"])),
                }
                for r in dev_rows
            ],
            "active_feature_assignments": [
                {
                    "story_id": str(r["story_id"]),
                    "developer_id": str(r["developer_id"]),
                    "git_branch": str(r["git_branch"]),
                    "git_commit_ref": str(r["git_commit_ref"]),
                    "active_stage": str(r["active_stage"]),
                    "work_status": str(r["work_status"]),
                    "updated_at": str(r["updated_at"]),
                }
                for r in work_rows
            ],
        }

    def get_org_standards(self, standard_id: str = "CORP-STD-001") -> dict[str, Any]:
        """Fetch corporate engineering standards for inter-project standardization."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT rules_json FROM org_standards WHERE standard_id = ?",
                (standard_id,),
            ).fetchone()
            if row is None:
                return {}
            return dict(json.loads(str(row["rules_json"])))

    def sync_alm_ticket(
        self,
        story_id: str,
        project_id: str,
        title: str,
        status: str,
        acceptance_criteria: list[str],
    ) -> None:
        """Synchronize a backlog story and its Acceptance Criteria with the ALM table."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO alm_tickets
                (story_id, project_id, title, status, acceptance_criteria_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (story_id, project_id, title, status, json.dumps(acceptance_criteria), now),
            )

    def get_alm_ticket(self, story_id: str) -> dict[str, Any] | None:
        """Retrieve a synchronized ALM ticket by story ID."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM alm_tickets WHERE story_id = ?",
                (story_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "story_id": str(row["story_id"]),
                "project_id": str(row["project_id"]),
                "title": str(row["title"]),
                "status": str(row["status"]),
                "acceptance_criteria": json.loads(str(row["acceptance_criteria_json"])),
                "synced_at": str(row["synced_at"]),
            }

    def save_agent_outcome(
        self,
        project_id: str,
        story_id: str,
        agent_type: str,
        status: str,
        payload: dict[str, Any],
        created_by: str = "agenticguard-mcp",
    ) -> int:
        """Persist the structured outcome of any modular SDLC/STLC agent."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_outcomes
                (project_id, story_id, agent_type, status, payload_json, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    story_id,
                    agent_type,
                    status,
                    json.dumps(payload),
                    created_by,
                    now,
                ),
            )
            return int(cursor.lastrowid or 0)

    def get_latest_outcome(
        self,
        project_id: str,
        story_id: str,
        agent_type: str,
    ) -> AgentOutcomeRecord | None:
        """Fetch the most recent outcome for a given project, story, and agent type."""
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_outcomes
                WHERE project_id = ? AND story_id = ? AND agent_type = ?
                ORDER BY id DESC LIMIT 1
                """,
                (project_id, story_id, agent_type),
            ).fetchone()
            if row is None:
                return None
            return AgentOutcomeRecord(
                id=int(row["id"]),
                project_id=str(row["project_id"]),
                story_id=str(row["story_id"]),
                agent_type=str(row["agent_type"]),
                status=str(row["status"]),
                payload=dict(json.loads(str(row["payload_json"]))),
                created_by=str(row["created_by"]),
                created_at=str(row["created_at"]),
            )

    def get_unified_project_context(self, project_id: str, story_id: str) -> dict[str, Any]:
        """Return the complete shared project context and all existing SDLC/STLC outcomes.

        Ensures every developer (and their AI coding assistant) operates from the
        same single source of truth regardless of which agent was triggered first.
        """
        with self._connection() as conn:
            proj_row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            outcome_rows = conn.execute(
                """
                SELECT agent_type, status, payload_json, created_by, created_at
                FROM agent_outcomes
                WHERE project_id = ? AND story_id = ?
                ORDER BY id ASC
                """,
                (project_id, story_id),
            ).fetchall()

        outcomes_by_stage: dict[str, Any] = {}
        for row in outcome_rows:
            outcomes_by_stage[str(row["agent_type"])] = {
                "status": str(row["status"]),
                "payload": json.loads(str(row["payload_json"])),
                "created_by": str(row["created_by"]),
                "created_at": str(row["created_at"]),
            }

        traceability = self.get_project_traceability_matrix(project_id)
        return {
            "project_id": project_id,
            "story_id": story_id,
            "project_metadata": (
                json.loads(str(proj_row["shared_context_json"])) if proj_row else {}
            ),
            "allowed_developers": traceability["allowed_developers"],
            "active_feature_assignments": traceability["active_feature_assignments"],
            "org_standards": self.get_org_standards(),
            "alm_ticket": self.get_alm_ticket(story_id),
            "stage_outcomes": outcomes_by_stage,
        }

    def log_gateway_call(
        self,
        session_id: str,
        project_id: str,
        story_id: str,
        user_id: str,
        user_group: str,
        harness_client: str,
        requested_model: str,
        routed_model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
        cost_usd: float,
        latency_ms: float,
        blocked_by_guardrail: bool = False,
        guardrail_reason: str = "NONE",
    ) -> None:
        """Record an AI Gateway inference or guardrail interception event."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO gateway_telemetry (
                    session_id, project_id, story_id, user_id, user_group,
                    harness_client, requested_model, routed_model, provider,
                    prompt_tokens, completion_tokens, cached_tokens, cost_usd,
                    latency_ms, blocked_by_guardrail, guardrail_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    project_id,
                    story_id,
                    user_id,
                    user_group,
                    harness_client,
                    requested_model,
                    routed_model,
                    provider,
                    prompt_tokens,
                    completion_tokens,
                    cached_tokens,
                    cost_usd,
                    latency_ms,
                    1 if blocked_by_guardrail else 0,
                    guardrail_reason,
                    now,
                ),
            )

    def get_user_spend_usd(self, user_id: str) -> float:
        """Calculate cumulative USD spend for a specific developer."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total_spend FROM gateway_telemetry WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return float(row["total_spend"]) if row else 0.0

    def get_harness_efficiency_scorecard(self) -> list[dict[str, Any]]:
        """Aggregate cost, token usage, cache hit ratio, and blocked threats per coding assistant."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    harness_client,
                    COUNT(*) AS total_calls,
                    SUM(CASE WHEN blocked_by_guardrail = 1 THEN 1 ELSE 0 END) AS blocked_calls,
                    SUM(prompt_tokens + completion_tokens) AS total_tokens,
                    SUM(cached_tokens) AS total_cached_tokens,
                    ROUND(SUM(cost_usd), 5) AS total_cost_usd,
                    ROUND(AVG(latency_ms), 2) AS avg_latency_ms
                FROM gateway_telemetry
                GROUP BY harness_client
                ORDER BY total_cost_usd DESC
                """
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            total_tok = int(row["total_tokens"] or 0)
            cached_tok = int(row["total_cached_tokens"] or 0)
            cache_ratio = round((cached_tok / total_tok) * 100.0, 1) if total_tok > 0 else 0.0
            results.append(
                {
                    "harness_client": str(row["harness_client"]),
                    "total_calls": int(row["total_calls"]),
                    "blocked_calls": int(row["blocked_calls"]),
                    "total_tokens": total_tok,
                    "cache_hit_pct": cache_ratio,
                    "total_cost_usd": float(row["total_cost_usd"] or 0.0),
                    "avg_latency_ms": float(row["avg_latency_ms"] or 0.0),
                }
            )
        return results

