from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime

import requests

from .config import SECTION_META, SETTINGS
from .models import AnalysisRequest


class TursoHistoryStore:
    def __init__(self, database_url: str, auth_token: str, page_size: int = SETTINGS.history_page_size):
        self.database_url = database_url.strip()
        self.auth_token = auth_token.strip()
        self.page_size = page_size
        self._schema_ready = False
        self._schema_error = ""
        self._schema_lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.database_url and self.auth_token)

    @property
    def pipeline_url(self) -> str:
        if self.database_url.startswith("libsql://"):
            base_url = "https://" + self.database_url[len("libsql://"):]
        else:
            base_url = self.database_url
        return f"{base_url.rstrip('/')}/v2/pipeline"

    def _value_to_hrana(self, value: object) -> dict:
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "integer", "value": "1" if value else "0"}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        return {"type": "text", "value": str(value)}

    def _value_from_hrana(self, value: object) -> object:
        if not isinstance(value, dict):
            return value
        value_type = value.get("type")
        raw = value.get("value")
        if value_type == "null":
            return None
        if value_type == "integer":
            try:
                return int(raw)
            except (TypeError, ValueError):
                return raw
        if value_type == "float":
            try:
                return float(raw)
            except (TypeError, ValueError):
                return raw
        return raw

    def _execute_many(self, statements: list[tuple[str, list[object] | None]]) -> list[dict]:
        if not self.configured:
            raise RuntimeError("Turso history database is not configured.")
        if not statements:
            return []
        response = requests.post(
            self.pipeline_url,
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
            },
            json={
                "requests": [
                    {
                        "type": "execute",
                        "stmt": {
                            "sql": sql,
                            "args": [self._value_to_hrana(arg) for arg in (args or [])],
                        },
                    }
                    for sql, args in statements
                ]
                + [
                    {"type": "close"},
                ]
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        output: list[dict] = []
        for result in results[: len(statements)]:
            if result.get("type") == "error":
                error = result.get("error") or {}
                raise RuntimeError(error.get("message") or "Turso SQL execution failed.")
            output.append(((result.get("response") or {}).get("result") or {}))
        return output

    def _execute(self, sql: str, args: list[object] | None = None) -> dict:
        results = self._execute_many([(sql, args)])
        return results[0] if results else {}

    def _query_rows(self, sql: str, args: list[object] | None = None) -> list[dict]:
        result = self._execute(sql, args)
        columns = [col.get("name") for col in result.get("cols", [])]
        rows = []
        for raw_row in result.get("rows", []):
            row_values = [self._value_from_hrana(value) for value in raw_row]
            rows.append(dict(zip(columns, row_values)))
        return rows

    def _table_columns(self, table_name: str) -> set[str]:
        rows = self._query_rows(f"PRAGMA table_info({table_name})")
        return {str(row.get("name") or "") for row in rows if row.get("name")}

    def ensure_schema(self) -> None:
        if not self.configured or self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            statements = [
                "PRAGMA foreign_keys = ON",
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    lookback_days INTEGER NOT NULL,
                    output_language TEXT NOT NULL,
                    research_depth TEXT NOT NULL,
                    model TEXT NOT NULL,
                    signal TEXT,
                    elapsed_seconds REAL,
                    section_count INTEGER NOT NULL DEFAULT 0,
                    user_email TEXT NOT NULL,
                    user_sub TEXT,
                    created_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS analysis_sections (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    section_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    team TEXT NOT NULL,
                    display_order INTEGER NOT NULL,
                    markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    email TEXT PRIMARY KEY,
                    google_sub TEXT,
                    name TEXT,
                    picture TEXT,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created ON analysis_runs(user_email, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_created ON analysis_runs(created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_symbol_date ON analysis_runs(user_email, symbol, analysis_date DESC)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_sections_run_order ON analysis_sections(run_id, display_order)",
                "CREATE INDEX IF NOT EXISTS idx_auth_users_google_sub ON auth_users(google_sub)",
                "CREATE INDEX IF NOT EXISTS idx_auth_users_last_seen ON auth_users(last_seen_at DESC)",
            ]
            self._execute_many([(statement, None) for statement in statements])
            run_columns = self._table_columns("analysis_runs")
            migration_statements: list[tuple[str, list[object] | None]] = []
            if "section_count" not in run_columns:
                migration_statements.append(("ALTER TABLE analysis_runs ADD COLUMN section_count INTEGER NOT NULL DEFAULT 0", None))
            user_columns = self._table_columns("auth_users")
            if "email_verified" not in user_columns:
                migration_statements.append(("ALTER TABLE auth_users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0", None))
            if migration_statements:
                self._execute_many(migration_statements)
            self._execute(
                """
                UPDATE analysis_runs
                SET section_count = (
                    SELECT COUNT(*) FROM analysis_sections s WHERE s.run_id = analysis_runs.id
                )
                WHERE section_count = 0
                """
            )
            self._schema_ready = True
            self._schema_error = ""

    def upsert_user(self, user: dict) -> None:
        if not self.configured:
            return
        self.ensure_schema()
        email = str(user.get("email") or "").strip().lower()
        if not email:
            return
        seen_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        self._execute(
            """
            INSERT INTO auth_users (
                email, google_sub, name, picture, email_verified, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                google_sub = excluded.google_sub,
                name = excluded.name,
                picture = excluded.picture,
                email_verified = excluded.email_verified,
                last_seen_at = excluded.last_seen_at
            """,
            [
                email,
                user.get("sub"),
                user.get("name"),
                user.get("picture"),
                bool(user.get("email_verified", True)),
                seen_at,
                seen_at,
            ],
        )

    def save_analysis(
        self,
        request: AnalysisRequest,
        user: dict,
        symbol: str,
        signal: str,
        elapsed_seconds: float,
        sections: list[dict],
    ) -> str | None:
        if not self.configured or not sections:
            return None
        self.ensure_schema()
        run_id = request.run_id or f"history-{uuid.uuid4().hex}"
        created_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        clean_sections = [section for section in sections if str(section.get("markdown") or "").strip()]
        statements: list[tuple[str, list[object] | None]] = [
            (
                """
                INSERT INTO analysis_runs (
                    id, symbol, asset_type, analysis_date, lookback_days, output_language,
                    research_depth, model, signal, elapsed_seconds, section_count, user_email, user_sub, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    symbol = excluded.symbol,
                    asset_type = excluded.asset_type,
                    analysis_date = excluded.analysis_date,
                    lookback_days = excluded.lookback_days,
                    output_language = excluded.output_language,
                    research_depth = excluded.research_depth,
                    model = excluded.model,
                    signal = excluded.signal,
                    elapsed_seconds = excluded.elapsed_seconds,
                    section_count = excluded.section_count,
                    user_email = excluded.user_email,
                    user_sub = excluded.user_sub,
                    created_at = excluded.created_at
                """,
                [
                    run_id,
                    symbol,
                    request.asset_type,
                    request.analysis_date,
                    request.lookback_days,
                    request.output_language,
                    request.research_depth,
                    request.model,
                    signal,
                    elapsed_seconds,
                    len(clean_sections),
                    user.get("email"),
                    user.get("sub"),
                    created_at,
                ],
            ),
            ("DELETE FROM analysis_sections WHERE run_id = ?", [run_id]),
        ]
        for index, section in enumerate(clean_sections):
            markdown = str(section.get("markdown") or "").strip()
            section_id = hashlib.sha1(f"{run_id}:{section.get('section_key')}".encode()).hexdigest()
            statements.append(
                (
                    """
                    INSERT INTO analysis_sections (
                        id, run_id, section_key, title, agent, team, display_order, markdown, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        section_id,
                        run_id,
                        section.get("section_key"),
                        section.get("title"),
                        section.get("agent"),
                        section.get("team"),
                        index,
                        markdown,
                        created_at,
                    ],
                )
            )
        self._execute_many(statements)
        return run_id

    def list_runs(self, user_email: str, limit: int | None = None, offset: int = 0) -> list[dict]:
        self.ensure_schema()
        safe_limit = limit or self.page_size
        return self._query_rows(
            """
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date, r.lookback_days,
                r.output_language, r.research_depth, r.model, r.signal,
                r.elapsed_seconds, r.created_at, r.section_count,
                (
                    SELECT s.markdown
                    FROM analysis_sections s
                    WHERE s.run_id = r.id AND s.section_key = 'final_trade_decision'
                    ORDER BY s.display_order DESC
                    LIMIT 1
                ) AS final_markdown
            FROM analysis_runs r
            WHERE r.user_email = ?
            ORDER BY r.created_at DESC
            LIMIT ?
            OFFSET ?
            """,
            [user_email, safe_limit, offset],
        )

    def list_public_runs(self, limit: int | None = None, offset: int = 0) -> list[dict]:
        self.ensure_schema()
        safe_limit = limit or self.page_size
        return self._query_rows(
            """
            SELECT
                id, symbol, asset_type, analysis_date, lookback_days,
                output_language, research_depth, model, signal,
                elapsed_seconds, created_at, section_count,
                (
                    SELECT s.markdown
                    FROM analysis_sections s
                    WHERE s.run_id = analysis_runs.id AND s.section_key = 'final_trade_decision'
                    ORDER BY s.display_order DESC
                    LIMIT 1
                ) AS final_markdown
            FROM analysis_runs
            ORDER BY created_at DESC
            LIMIT ?
            OFFSET ?
            """,
            [safe_limit, offset],
        )

    def get_run(self, run_id: str, user_email: str) -> dict | None:
        self.ensure_schema()
        runs = self._query_rows(
            """
            SELECT id, symbol, asset_type, analysis_date, lookback_days,
                output_language, research_depth, model, signal, elapsed_seconds, created_at
            FROM analysis_runs
            WHERE id = ? AND user_email = ?
            LIMIT 1
            """,
            [run_id, user_email],
        )
        if not runs:
            return None
        sections = self._query_rows(
            """
            SELECT section_key, title, agent, team, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ?
            ORDER BY display_order ASC
            """,
            [run_id],
        )
        return {"item": runs[0], "sections": sections}

    def get_public_run(self, run_id: str) -> dict | None:
        self.ensure_schema()
        runs = self._query_rows(
            """
            SELECT id, symbol, asset_type, analysis_date, lookback_days,
                output_language, research_depth, model, signal, elapsed_seconds, created_at
            FROM analysis_runs
            WHERE id = ?
            LIMIT 1
            """,
            [run_id],
        )
        if not runs:
            return None
        sections = self._query_rows(
            """
            SELECT section_key, title, agent, team, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ?
            ORDER BY display_order ASC
            """,
            [run_id],
        )
        return {"item": runs[0], "sections": sections}


def build_history_sections(final_state: dict) -> list[dict]:
    sections: list[dict] = []
    for section_key, meta in SECTION_META.items():
        markdown = str(final_state.get(section_key) or "").strip()
        if markdown:
            sections.append(
                {
                    "section_key": section_key,
                    "title": meta["title"],
                    "agent": meta["agent"],
                    "team": meta["team"],
                    "markdown": markdown,
                }
            )

    investment = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    extra_sections = [
        ("bull_research", "Bull Research", "Bull Researcher", "Research Team", investment.get("bull_history")),
        ("bear_research", "Bear Research", "Bear Researcher", "Research Team", investment.get("bear_history")),
        ("research_debate", "Research Debate", "Research Team", "Research Team", investment.get("history")),
        ("aggressive_risk", "Aggressive Risk", "Aggressive Analyst", "Risk Team", risk.get("aggressive_history") or risk.get("current_aggressive_response")),
        ("conservative_risk", "Conservative Risk", "Conservative Analyst", "Risk Team", risk.get("conservative_history") or risk.get("current_conservative_response")),
        ("neutral_risk", "Neutral Risk", "Neutral Analyst", "Risk Team", risk.get("neutral_history") or risk.get("current_neutral_response")),
        ("risk_debate", "Risk Debate", "Risk Team", "Risk Team", risk.get("history")),
    ]
    for section_key, title, agent, team, markdown in extra_sections:
        markdown = str(markdown or "").strip()
        if markdown:
            sections.append(
                {
                    "section_key": section_key,
                    "title": title,
                    "agent": agent,
                    "team": team,
                    "markdown": markdown,
                }
            )
    return sections