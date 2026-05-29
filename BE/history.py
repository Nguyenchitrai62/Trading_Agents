from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import datetime, timedelta

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
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    can_run_analysis INTEGER NOT NULL DEFAULT 0,
                    history_access_unlimited INTEGER NOT NULL DEFAULT 0,
                    history_access_days INTEGER,
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
            if "is_admin" not in user_columns:
                migration_statements.append(("ALTER TABLE auth_users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0", None))
            if "can_run_analysis" not in user_columns:
                migration_statements.append(("ALTER TABLE auth_users ADD COLUMN can_run_analysis INTEGER NOT NULL DEFAULT 0", None))
            if "history_access_unlimited" not in user_columns:
                migration_statements.append(("ALTER TABLE auth_users ADD COLUMN history_access_unlimited INTEGER NOT NULL DEFAULT 0", None))
            if "history_access_days" not in user_columns:
                migration_statements.append(("ALTER TABLE auth_users ADD COLUMN history_access_days INTEGER", None))
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
                email, google_sub, name, picture, email_verified, is_admin,
                can_run_analysis, history_access_unlimited, history_access_days, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                google_sub = excluded.google_sub,
                name = excluded.name,
                picture = excluded.picture,
                email_verified = excluded.email_verified,
                is_admin = CASE WHEN excluded.is_admin = 1 THEN 1 ELSE auth_users.is_admin END,
                can_run_analysis = CASE
                    WHEN excluded.is_admin = 1 THEN 1
                    ELSE auth_users.can_run_analysis
                END,
                history_access_unlimited = CASE
                    WHEN excluded.is_admin = 1 THEN 1
                    ELSE auth_users.history_access_unlimited
                END,
                history_access_days = CASE
                    WHEN excluded.is_admin = 1 OR auth_users.history_access_unlimited = 1 THEN NULL
                    ELSE COALESCE(auth_users.history_access_days, excluded.history_access_days)
                END,
                last_seen_at = excluded.last_seen_at
            """,
            [
                email,
                user.get("sub"),
                user.get("name"),
                user.get("picture"),
                bool(user.get("email_verified", True)),
                bool(user.get("is_admin", False)),
                bool(user.get("can_run_analysis", False)),
                bool(user.get("history_access_unlimited", False)),
                user.get("history_access_days"),
                seen_at,
                seen_at,
            ],
        )

    def _format_user_access(
        self,
        row: dict | None,
        email: str,
        default_history_access_days: int,
        admin_emails: frozenset[str],
    ) -> dict:
        normalized_email = email.strip().lower()
        is_seed_admin = normalized_email in admin_emails
        is_admin = is_seed_admin or bool(row.get("is_admin") if row else False)
        can_run_analysis = is_admin or bool(row.get("can_run_analysis") if row else False)
        history_access_unlimited = is_admin or bool(row.get("history_access_unlimited") if row else False)
        raw_days = row.get("history_access_days") if row else None
        history_access_days = None if history_access_unlimited else raw_days or default_history_access_days
        return {
            "email": normalized_email,
            "google_sub": row.get("google_sub") if row else None,
            "name": row.get("name") if row else "",
            "picture": row.get("picture") if row else "",
            "email_verified": bool(row.get("email_verified") if row else True),
            "is_admin": is_admin,
            "role": "admin" if is_admin else "runner" if can_run_analysis else "user",
            "can_run_analysis": can_run_analysis,
            "history_access_days": history_access_days,
            "history_access_unlimited": history_access_unlimited,
            "first_seen_at": row.get("first_seen_at") if row else None,
            "last_seen_at": row.get("last_seen_at") if row else None,
            "is_seed_admin": is_seed_admin,
        }

    def get_user_access(
        self,
        email: str,
        default_history_access_days: int,
        admin_emails: frozenset[str],
    ) -> dict:
        self.ensure_schema()
        normalized_email = email.strip().lower()
        rows = self._query_rows(
            """
            SELECT email, google_sub, name, picture, email_verified, is_admin,
                can_run_analysis, history_access_unlimited, history_access_days, first_seen_at, last_seen_at
            FROM auth_users
            WHERE email = ?
            LIMIT 1
            """,
            [normalized_email],
        )
        return self._format_user_access(rows[0] if rows else None, normalized_email, default_history_access_days, admin_emails)

    def list_users(self, default_history_access_days: int, admin_emails: frozenset[str]) -> list[dict]:
        self.ensure_schema()
        rows = self._query_rows(
            """
            SELECT email, google_sub, name, picture, email_verified, is_admin,
                can_run_analysis, history_access_unlimited, history_access_days, first_seen_at, last_seen_at
            FROM auth_users
            ORDER BY last_seen_at DESC
            """
        )
        users = [self._format_user_access(row, row["email"], default_history_access_days, admin_emails) for row in rows]
        seen = {user["email"] for user in users}
        for email in sorted(admin_emails - seen):
            users.append(self._format_user_access(None, email, default_history_access_days, admin_emails))
        return users

    def update_user_access(
        self,
        email: str,
        is_admin: bool | None,
        can_run_analysis: bool | None,
        history_access_days: int | None,
        history_access_unlimited: bool,
        default_history_access_days: int,
        admin_emails: frozenset[str],
    ) -> dict:
        self.ensure_schema()
        normalized_email = email.strip().lower()
        current = self.get_user_access(normalized_email, default_history_access_days, admin_emails)
        effective_is_admin = current["is_seed_admin"] or (bool(is_admin) if is_admin is not None else bool(current["is_admin"]))
        effective_can_run_analysis = effective_is_admin or (
            bool(can_run_analysis) if can_run_analysis is not None else bool(current.get("can_run_analysis"))
        )
        effective_history_unlimited = effective_is_admin or bool(history_access_unlimited)
        if effective_history_unlimited:
            effective_days = None
        elif history_access_days is not None:
            effective_days = max(1, int(history_access_days))
        else:
            effective_days = current.get("history_access_days") or default_history_access_days

        now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        self._execute(
            """
            INSERT INTO auth_users (
                email, google_sub, name, picture, email_verified, is_admin,
                can_run_analysis, history_access_unlimited, history_access_days, first_seen_at, last_seen_at
            ) VALUES (?, NULL, '', '', 0, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                is_admin = excluded.is_admin,
                can_run_analysis = excluded.can_run_analysis,
                history_access_unlimited = excluded.history_access_unlimited,
                history_access_days = excluded.history_access_days
            """,
            [normalized_email, effective_is_admin, effective_can_run_analysis, effective_history_unlimited, effective_days, now, now],
        )
        return self.get_user_access(normalized_email, default_history_access_days, admin_emails)

    @staticmethod
    def _history_cutoff(history_access_days: int | None) -> str | None:
        if history_access_days is None:
            return None
        return (datetime.utcnow() - timedelta(days=max(1, int(history_access_days)))).replace(microsecond=0).isoformat() + "Z"

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
                elapsed_seconds, created_at, section_count
            FROM analysis_runs
            ORDER BY created_at DESC
            LIMIT ?
            OFFSET ?
            """,
            [safe_limit, offset],
        )

    def list_accessible_runs(self, history_access_days: int | None, limit: int | None = None, offset: int = 0) -> list[dict]:
        self.ensure_schema()
        safe_limit = limit or self.page_size
        cutoff = self._history_cutoff(history_access_days)
        where_clause = "WHERE r.created_at >= ?" if cutoff else ""
        args: list[object] = [cutoff] if cutoff else []
        args.extend([safe_limit, offset])
        return self._query_rows(
            f"""
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date, r.lookback_days,
                r.output_language, r.research_depth, r.model, r.signal,
                r.elapsed_seconds, r.created_at, r.section_count, r.user_email
            FROM analysis_runs r
            {where_clause}
            ORDER BY r.created_at DESC
            LIMIT ?
            OFFSET ?
            """,
            args,
        )

    def list_run_section_metas_bulk(self, run_ids: list[str], history_access_days: int | None) -> dict[str, list[dict]]:
        self.ensure_schema()
        safe_run_ids = [str(run_id).strip() for run_id in run_ids if str(run_id).strip()]
        if not safe_run_ids:
            return {}

        placeholders = ", ".join("?" for _ in safe_run_ids)
        cutoff = self._history_cutoff(history_access_days)
        extra_where = "AND r.created_at >= ?" if cutoff else ""
        args: list[object] = [*safe_run_ids]
        if cutoff:
            args.append(cutoff)

        rows = self._query_rows(
            f"""
            SELECT
                s.run_id, s.section_key, s.title, s.agent, s.team, s.created_at
            FROM analysis_sections s
            INNER JOIN analysis_runs r ON r.id = s.run_id
            WHERE s.run_id IN ({placeholders})
              {extra_where}
            ORDER BY s.run_id ASC, s.display_order ASC
            """,
            args,
        )

        grouped = {run_id: [] for run_id in safe_run_ids}
        for row in rows:
            run_id = str(row.get("run_id") or "")
            if not run_id:
                continue
            grouped.setdefault(run_id, []).append({
                "section_key": row.get("section_key"),
                "title": row.get("title"),
                "agent": row.get("agent"),
                "team": row.get("team"),
                "created_at": row.get("created_at"),
            })
        return grouped

    def count_accessible_runs(self, history_access_days: int | None) -> int:
        self.ensure_schema()
        cutoff = self._history_cutoff(history_access_days)
        where_clause = "WHERE created_at >= ?" if cutoff else ""
        args: list[object] = [cutoff] if cutoff else []
        rows = self._query_rows(
            f"""
            SELECT COUNT(*) AS total_count
            FROM analysis_runs
            {where_clause}
            """,
            args,
        )
        if not rows:
            return 0
        return int(rows[0].get("total_count") or 0)

    def get_accessible_run_meta(self, run_id: str, history_access_days: int | None) -> dict | None:
        self.ensure_schema()
        cutoff = self._history_cutoff(history_access_days)
        where_clause = "AND created_at >= ?" if cutoff else ""
        args: list[object] = [run_id]
        if cutoff:
            args.append(cutoff)
        runs = self._query_rows(
            f"""
            SELECT id, symbol, asset_type, analysis_date, lookback_days,
                output_language, research_depth, model, signal, elapsed_seconds,
                created_at, section_count, user_email
            FROM analysis_runs
            WHERE id = ? {where_clause}
            LIMIT 1
            """,
            args,
        )
        return runs[0] if runs else None

    def list_run_section_metas(self, run_id: str, history_access_days: int | None) -> dict | None:
        item = self.get_accessible_run_meta(run_id, history_access_days)
        if item is None:
            return None
        sections = self._query_rows(
            """
            SELECT section_key, title, agent, team, created_at
            FROM analysis_sections
            WHERE run_id = ?
            ORDER BY display_order ASC
            """,
            [run_id],
        )
        return {"item": item, "sections": sections}

    def get_run_section(self, run_id: str, section_key: str, history_access_days: int | None) -> dict | None:
        item = self.get_accessible_run_meta(run_id, history_access_days)
        if item is None:
            return None
        sections = self._query_rows(
            """
            SELECT section_key, title, agent, team, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ? AND section_key = ?
            LIMIT 1
            """,
            [run_id, section_key],
        )
        if not sections:
            return None
        return {"item": item, "section": sections[0]}

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