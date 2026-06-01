from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta

import requests

from .config import SECTION_META, SETTINGS
from .models import AnalysisRequest
from tradingagents.agents.utils.decision import compatibility_decision_fields
from tradingagents.agents.utils.evidence import evidence_items_to_markdown
from tradingagents.dataflows.endpoint_summary import format_endpoint_summaries_for_prompt


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

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

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
                    artifact_type TEXT NOT NULL DEFAULT 'markdown',
                    flow_stage TEXT,
                    flow_group TEXT,
                    source_kind TEXT,
                    source_key TEXT,
                    summary TEXT,
                    payload_json TEXT,
                    display_order INTEGER NOT NULL,
                    markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS analysis_decisions (
                    run_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    signal TEXT,
                    primary_limit_price REAL,
                    secondary_limit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    position_sizing TEXT,
                    time_horizon TEXT,
                    verification_verdict TEXT,
                    verification_action TEXT,
                    current_price REAL,
                    decision_json TEXT NOT NULL,
                    verification_json TEXT NOT NULL,
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
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created ON analysis_runs(user_email, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_created ON analysis_runs(created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_symbol_date ON analysis_runs(user_email, symbol, analysis_date DESC)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_sections_run_order ON analysis_sections(run_id, display_order)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_decisions_symbol_date ON analysis_decisions(symbol, analysis_date DESC)",
                "CREATE INDEX IF NOT EXISTS idx_auth_users_google_sub ON auth_users(google_sub)",
                "CREATE INDEX IF NOT EXISTS idx_auth_users_last_seen ON auth_users(last_seen_at DESC)",
            ]
            self._execute_many([(statement, None) for statement in statements])
            run_columns = self._table_columns("analysis_runs")
            migration_statements: list[tuple[str, list[object] | None]] = []
            if "section_count" not in run_columns:
                migration_statements.append(("ALTER TABLE analysis_runs ADD COLUMN section_count INTEGER NOT NULL DEFAULT 0", None))
            section_columns = self._table_columns("analysis_sections")
            section_column_defaults = {
                "artifact_type": "TEXT NOT NULL DEFAULT 'markdown'",
                "flow_stage": "TEXT",
                "flow_group": "TEXT",
                "source_kind": "TEXT",
                "source_key": "TEXT",
                "summary": "TEXT",
                "payload_json": "TEXT",
            }
            for column_name, column_def in section_column_defaults.items():
                if column_name not in section_columns:
                    migration_statements.append((f"ALTER TABLE analysis_sections ADD COLUMN {column_name} {column_def}", None))
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
            self._execute("CREATE INDEX IF NOT EXISTS idx_analysis_sections_run_stage ON analysis_sections(run_id, flow_stage, flow_group)")
            self._execute("CREATE INDEX IF NOT EXISTS idx_analysis_sections_run_key ON analysis_sections(run_id, section_key)")
            self._execute("CREATE INDEX IF NOT EXISTS idx_analysis_sections_run_artifact_group ON analysis_sections(run_id, artifact_type, flow_group, display_order)")
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

    @staticmethod
    def _normalize_history_access_days(value: object, default: int | None = None) -> int | None:
        if value is None:
            return default
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    def get_history_public_read(self, default_enabled: bool) -> bool:
        if not self.configured:
            return bool(default_enabled)
        self.ensure_schema()
        rows = self._query_rows(
            """
            SELECT value
            FROM app_settings
            WHERE key = ?
            LIMIT 1
            """,
            ["history_public_read"],
        )
        if not rows:
            return bool(default_enabled)
        value = str(rows[0].get("value") or "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def set_history_public_read(self, enabled: bool) -> bool:
        if not self.configured:
            return bool(enabled)
        self.ensure_schema()
        now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        self._execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            ["history_public_read", "1" if enabled else "0", now],
        )
        return bool(enabled)

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
        normalized_days = self._normalize_history_access_days(raw_days)
        history_access_days = None if history_access_unlimited else (
            normalized_days if normalized_days is not None else max(0, int(default_history_access_days))
        )
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
            effective_days = self._normalize_history_access_days(history_access_days, 0)
        else:
            effective_days = self._normalize_history_access_days(current.get("history_access_days"), default_history_access_days)

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
        normalized_days = max(0, int(history_access_days))
        if normalized_days == 0:
            return (datetime.utcnow() + timedelta(days=365 * 200)).replace(microsecond=0).isoformat() + "Z"
        return (datetime.utcnow() - timedelta(days=normalized_days)).replace(microsecond=0).isoformat() + "Z"

    def save_analysis(
        self,
        request: AnalysisRequest,
        user: dict,
        symbol: str,
        signal: str,
        elapsed_seconds: float,
        sections: list[dict],
        decision_payload: dict | None = None,
        verification_payload: dict | None = None,
        current_price: object = None,
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
            payload_json = section.get("payload_json")
            if payload_json not in (None, "") and not isinstance(payload_json, str):
                payload_json = json.dumps(payload_json, ensure_ascii=False, sort_keys=True, default=str)
            statements.append(
                (
                    """
                    INSERT INTO analysis_sections (
                        id, run_id, section_key, title, agent, team, artifact_type,
                        flow_stage, flow_group, source_kind, source_key, summary, payload_json,
                        display_order, markdown, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        section_id,
                        run_id,
                        section.get("section_key"),
                        section.get("title"),
                        section.get("agent"),
                        section.get("team"),
                        section.get("artifact_type") or "markdown",
                        section.get("flow_stage"),
                        section.get("flow_group"),
                        section.get("source_kind"),
                        section.get("source_key"),
                        section.get("summary"),
                        payload_json,
                        index,
                        markdown,
                        created_at,
                    ],
                )
            )
        decision_payload = decision_payload or {}
        verification_payload = verification_payload or {}
        if decision_payload or verification_payload or current_price is not None:
            decision_signal = str(decision_payload.get("signal") or signal or "").strip()
            decision_fields = compatibility_decision_fields(decision_payload)
            statements.append(
                (
                    """
                    INSERT INTO analysis_decisions (
                        run_id, symbol, analysis_date, signal, primary_limit_price,
                        secondary_limit_price, stop_loss, take_profit, position_sizing,
                        time_horizon, verification_verdict, verification_action,
                        current_price, decision_json, verification_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        symbol = excluded.symbol,
                        analysis_date = excluded.analysis_date,
                        signal = excluded.signal,
                        primary_limit_price = excluded.primary_limit_price,
                        secondary_limit_price = excluded.secondary_limit_price,
                        stop_loss = excluded.stop_loss,
                        take_profit = excluded.take_profit,
                        position_sizing = excluded.position_sizing,
                        time_horizon = excluded.time_horizon,
                        verification_verdict = excluded.verification_verdict,
                        verification_action = excluded.verification_action,
                        current_price = excluded.current_price,
                        decision_json = excluded.decision_json,
                        verification_json = excluded.verification_json,
                        created_at = excluded.created_at
                    """,
                    [
                        run_id,
                        symbol,
                        request.analysis_date,
                        decision_signal,
                        self._coerce_float(decision_fields.get("primary_limit_price")),
                        self._coerce_float(decision_fields.get("secondary_limit_price")),
                        self._coerce_float(decision_fields.get("stop_loss")),
                        self._coerce_float(decision_fields.get("take_profit")),
                        decision_fields.get("position_sizing"),
                        decision_fields.get("time_horizon"),
                        verification_payload.get("verdict"),
                        verification_payload.get("recommended_action"),
                        self._coerce_float(current_price),
                        json.dumps(decision_payload, ensure_ascii=False, sort_keys=True, default=str),
                        json.dumps(verification_payload, ensure_ascii=False, sort_keys=True, default=str),
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
                r.output_language, r.research_depth, r.model,
                COALESCE(d.signal, r.signal) AS signal,
                d.current_price, d.primary_limit_price, d.secondary_limit_price,
                d.stop_loss, d.take_profit, d.position_sizing, d.time_horizon,
                d.verification_verdict, d.verification_action,
                r.elapsed_seconds, r.created_at, r.section_count,
                (
                    SELECT s.markdown
                    FROM analysis_sections s
                    WHERE s.run_id = r.id AND s.section_key = 'final_trade_decision'
                    ORDER BY s.display_order DESC
                    LIMIT 1
                ) AS final_markdown
            FROM analysis_runs r
            LEFT JOIN analysis_decisions d ON d.run_id = r.id
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
                r.id, r.symbol, r.asset_type, r.analysis_date, r.lookback_days,
                r.output_language, r.research_depth, r.model,
                COALESCE(d.signal, r.signal) AS signal,
                d.current_price, d.primary_limit_price, d.secondary_limit_price,
                d.stop_loss, d.take_profit, d.position_sizing, d.time_horizon,
                d.verification_verdict, d.verification_action,
                r.elapsed_seconds, r.created_at, r.section_count
            FROM analysis_runs r
            LEFT JOIN analysis_decisions d ON d.run_id = r.id
            ORDER BY r.created_at DESC
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
                r.output_language, r.research_depth, r.model,
                COALESCE(d.signal, r.signal) AS signal,
                d.current_price, d.primary_limit_price, d.secondary_limit_price,
                d.stop_loss, d.take_profit, d.position_sizing, d.time_horizon,
                d.verification_verdict, d.verification_action,
                r.elapsed_seconds, r.created_at, r.section_count, r.user_email
            FROM analysis_runs r
            LEFT JOIN analysis_decisions d ON d.run_id = r.id
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
                s.run_id, s.section_key, s.title, s.agent, s.team,
                s.artifact_type, s.flow_stage, s.flow_group, s.source_kind, s.source_key, s.summary,
                s.created_at
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
                "artifact_type": row.get("artifact_type") or "markdown",
                "flow_stage": row.get("flow_stage"),
                "flow_group": row.get("flow_group"),
                "source_kind": row.get("source_kind"),
                "source_key": row.get("source_key"),
                "summary": row.get("summary"),
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
        where_clause = "AND r.created_at >= ?" if cutoff else ""
        args: list[object] = [run_id]
        if cutoff:
            args.append(cutoff)
        runs = self._query_rows(
            f"""
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date, r.lookback_days,
                r.output_language, r.research_depth, r.model,
                COALESCE(d.signal, r.signal) AS signal,
                d.current_price, d.primary_limit_price, d.secondary_limit_price,
                d.stop_loss, d.take_profit, d.position_sizing, d.time_horizon,
                d.verification_verdict, d.verification_action,
                r.elapsed_seconds, r.created_at, r.section_count, r.user_email
            FROM analysis_runs r
            LEFT JOIN analysis_decisions d ON d.run_id = r.id
            WHERE r.id = ? {where_clause}
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
            SELECT section_key, title, agent, team, artifact_type, flow_stage, flow_group, source_kind, source_key, summary, created_at
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
            SELECT section_key, title, agent, team, artifact_type, flow_stage, flow_group,
                source_kind, source_key, summary, payload_json, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ? AND section_key = ?
            LIMIT 1
            """,
            [run_id, section_key],
        )
        if not sections:
            return None
        return {"item": item, "section": sections[0]}

    def get_final_decision_markdown(self, run_id: str, history_access_days: int | None) -> dict | None:
        item = self.get_accessible_run_meta(run_id, history_access_days)
        if item is None:
            return None
        rows = self._query_rows(
            """
            SELECT section_key, title, agent, team, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ?
              AND section_key IN ('final_trade_decision', 'verification_report')
            ORDER BY CASE section_key
                WHEN 'final_trade_decision' THEN 0
                WHEN 'verification_report' THEN 1
                ELSE 2
            END
            """,
            [run_id],
        )
        if not rows:
            return None
        summary_lines = ["# Final Decision Snapshot", ""]
        summary_pairs = [
            ("Signal", item.get("signal")),
            ("Current Price", item.get("current_price")),
            ("Primary Limit Price", item.get("primary_limit_price")),
            ("Secondary Limit Price", item.get("secondary_limit_price")),
            ("Stop Loss", item.get("stop_loss")),
            ("Take Profit", item.get("take_profit")),
            ("Position Sizing", item.get("position_sizing")),
            ("Time Horizon", item.get("time_horizon")),
            ("Verification Verdict", item.get("verification_verdict")),
            ("Verification Action", item.get("verification_action")),
        ]
        for label, value in summary_pairs:
            if value in (None, ""):
                continue
            summary_lines.append(f"- {label}: {value}")
        if len(summary_lines) > 2:
            summary_lines.append("")
        markdown_blocks = []
        for row in rows:
            markdown = str(row.get("markdown") or "").strip()
            if not markdown:
                continue
            title = str(row.get("title") or row.get("section_key") or "Section").strip()
            markdown_blocks.append(f"# {title}\n\n{markdown}")
        if not markdown_blocks:
            return None
        return {
            "item": item,
            "section": {
                "section_key": "final_decision",
                "title": "Final Decision",
                "agent": "Portfolio Manager",
                "team": "Portfolio Management",
                "markdown": "\n".join(summary_lines + ["\n\n---\n\n".join(markdown_blocks)]).strip(),
                "created_at": rows[0].get("created_at"),
            },
        }

    def list_source_artifacts(
        self,
        run_id: str,
        history_access_days: int | None,
        flow_group: str | None = None,
        source_kind: str | None = None,
    ) -> dict | None:
        item = self.get_accessible_run_meta(run_id, history_access_days)
        if item is None:
            return None

        normalized_source_kind = str(source_kind or "").strip()
        artifact_filter = "artifact_type = 'flow_block'" if normalized_source_kind == "flow_block" else "artifact_type = 'source'"
        where = ["run_id = ?", artifact_filter]
        args: list[object] = [run_id]
        normalized_flow_group = str(flow_group or "").strip()
        if normalized_flow_group:
            where.append("flow_group = ?")
            args.append(normalized_flow_group)
        if normalized_source_kind:
            where.append("source_kind = ?")
            args.append(normalized_source_kind)
        rows = self._query_rows(
            f"""
            SELECT section_key, title, agent, team, artifact_type, flow_stage,
                flow_group, source_kind, source_key, summary, created_at
            FROM analysis_sections
            WHERE {" AND ".join(where)}
            ORDER BY display_order ASC
            """,
            args,
        )
        return {"item": item, "artifacts": rows}

    def get_source_artifact(self, run_id: str, section_key: str, history_access_days: int | None) -> dict | None:
        item = self.get_accessible_run_meta(run_id, history_access_days)
        if item is None:
            return None
        rows = self._query_rows(
            """
            SELECT section_key, title, agent, team, artifact_type, flow_stage,
                flow_group, source_kind, source_key, summary, payload_json, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ?
              AND section_key = ?
              AND artifact_type IN ('source', 'flow_block')
            LIMIT 1
            """,
            [run_id, section_key],
        )
        if not rows:
            return None
        return {"item": item, "artifact": rows[0]}

    def get_run(self, run_id: str, user_email: str) -> dict | None:
        self.ensure_schema()
        runs = self._query_rows(
            """
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date, r.lookback_days,
                r.output_language, r.research_depth, r.model,
                COALESCE(d.signal, r.signal) AS signal,
                d.current_price, d.primary_limit_price, d.secondary_limit_price,
                d.stop_loss, d.take_profit, d.position_sizing, d.time_horizon,
                d.verification_verdict, d.verification_action,
                r.elapsed_seconds, r.created_at
            FROM analysis_runs r
            LEFT JOIN analysis_decisions d ON d.run_id = r.id
            WHERE r.id = ? AND r.user_email = ?
            LIMIT 1
            """,
            [run_id, user_email],
        )
        if not runs:
            return None
        sections = self._query_rows(
            """
            SELECT section_key, title, agent, team, artifact_type, flow_stage, flow_group,
                source_kind, source_key, summary, payload_json, markdown, created_at
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
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date, r.lookback_days,
                r.output_language, r.research_depth, r.model,
                COALESCE(d.signal, r.signal) AS signal,
                d.current_price, d.primary_limit_price, d.secondary_limit_price,
                d.stop_loss, d.take_profit, d.position_sizing, d.time_horizon,
                d.verification_verdict, d.verification_action,
                r.elapsed_seconds, r.created_at
            FROM analysis_runs r
            LEFT JOIN analysis_decisions d ON d.run_id = r.id
            WHERE r.id = ?
            LIMIT 1
            """,
            [run_id],
        )
        if not runs:
            return None
        sections = self._query_rows(
            """
            SELECT section_key, title, agent, team, artifact_type, flow_stage, flow_group,
                source_kind, source_key, summary, payload_json, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ?
            ORDER BY display_order ASC
            """,
            [run_id],
        )
        return {"item": runs[0], "sections": sections}


def _history_section(
    section_key: str,
    title: str,
    agent: str,
    team: str,
    markdown: object,
    *,
    artifact_type: str = "markdown",
    flow_stage: str | None = None,
    flow_group: str | None = None,
    source_kind: str | None = None,
    source_key: str | None = None,
    summary: str | None = None,
    payload_json: object = None,
) -> dict | None:
    markdown_text = str(markdown or "").strip()
    if not markdown_text:
        return None
    return {
        "section_key": section_key,
        "title": title,
        "agent": agent,
        "team": team,
        "markdown": markdown_text,
        "artifact_type": artifact_type,
        "flow_stage": flow_stage,
        "flow_group": flow_group,
        "source_kind": source_kind,
        "source_key": source_key,
        "summary": summary,
        "payload_json": payload_json,
    }


def _structured_payload_to_markdown(title: str, payload: object) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    return "\n".join(
        [
            f"# {title}",
            "",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            "```",
        ]
    )


def _endpoint_summaries_to_markdown(endpoint_summaries: object) -> str:
    if not isinstance(endpoint_summaries, list) or not endpoint_summaries:
        return ""
    prompt_block = format_endpoint_summaries_for_prompt(endpoint_summaries, limit=max(1, len(endpoint_summaries)))
    rows = [
        "| Endpoint | Package | Status | Direction | Confidence | Source |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for item in endpoint_summaries:
        if not isinstance(item, dict):
            continue
        confidence = item.get("confidence")
        try:
            confidence_text = f"{float(confidence):.2f}"
        except (TypeError, ValueError):
            confidence_text = ""
        cells = [
            item.get("title") or item.get("endpoint_name") or "",
            item.get("package_label") or item.get("package") or "",
            item.get("status") or "",
            item.get("direction") or "",
            confidence_text,
            item.get("source") or "",
        ]
        rows.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    return "\n\n".join(["# Endpoint Summaries", prompt_block, "\n".join(rows)]).strip()


def _endpoint_summary_bucket(item: dict) -> str:
    text = " ".join(
        str(item.get(key) or "").lower()
        for key in ("package", "package_label", "endpoint_name", "title", "source", "source_type")
    )
    if any(token in text for token in ("coinglass", "derivative", "funding", "liquidation", "open interest")):
        return "coinglass"
    if any(token in text for token in ("news", "article", "global")):
        return "news"
    if any(token in text for token in ("social", "reddit", "stocktwits", "web")):
        return "social"
    if any(token in text for token in ("flow", "on-chain", "liquidity", "stablecoin", "tvl")):
        return "flow"
    if any(token in text for token in ("ccxt", "ohlcv", "indicator", "market")):
        return "ccxt"
    return ""


def _filter_endpoint_summaries(endpoint_summaries: object, bucket: str) -> list[dict]:
    if not isinstance(endpoint_summaries, list):
        return []
    return [
        item
        for item in endpoint_summaries
        if isinstance(item, dict) and _endpoint_summary_bucket(item) == bucket
    ]


def _source_group_artifacts(flow_artifacts: object, flow_group: str) -> list[dict]:
    if not isinstance(flow_artifacts, list):
        return []
    return [
        artifact
        for artifact in flow_artifacts
        if isinstance(artifact, dict) and artifact.get("flow_group") == flow_group
    ]


def _source_group_summary_markdown(title: str, endpoint_summaries: list[dict], artifacts: list[dict]) -> str:
    if endpoint_summaries:
        return _endpoint_summaries_to_markdown(endpoint_summaries).replace("# Endpoint Summaries", f"# {title}", 1)
    if not artifacts:
        return ""
    lines = [f"# {title}", "", "| Source | Kind | Summary |", "| --- | --- | --- |"]
    for artifact in artifacts[:24]:
        cells = [
            artifact.get("title") or artifact.get("source_key") or "",
            artifact.get("source_kind") or artifact.get("artifact_type") or "",
            artifact.get("summary") or artifact.get("source_key") or "",
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    return "\n".join(lines).strip()


def _flow_block_markdown(title: str, status: str, summary: str, payload: dict) -> str:
    related_sections = payload.get("related_sections") if isinstance(payload, dict) else []
    related_sources = payload.get("source_groups") if isinstance(payload, dict) else []
    lines = [
        f"# {title}",
        "",
        f"- Status: {status or 'pending'}",
    ]
    if summary:
        lines.append(f"- Summary: {summary}")
    if isinstance(related_sections, list) and related_sections:
        lines.append("- Related sections: " + ", ".join(str(item) for item in related_sections if item))
    if isinstance(related_sources, list) and related_sources:
        lines.append("- Related source groups: " + ", ".join(str(item) for item in related_sources if item))
    lines.extend(["", "```json", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), "```"])
    return "\n".join(lines).strip()


def _build_flow_block_sections(final_state: dict) -> list[dict]:
    sections: list[dict] = []
    selected_analysts = {
        str(item or "").strip().lower()
        for item in (final_state.get("selected_analysts") or ["market", "onchain", "social", "news"])
        if str(item or "").strip()
    }
    source_group_counts = final_state.get("source_artifact_groups") or {}
    flow_artifacts = final_state.get("flow_artifacts") or []
    endpoint_summaries = final_state.get("endpoint_summaries") or []

    def has_text(key: str) -> bool:
        return bool(str(final_state.get(key) or "").strip())

    def has_payload(key: str) -> bool:
        payload = final_state.get(key)
        return isinstance(payload, (dict, list)) and bool(payload)

    def status_for(ready: bool, prerequisite: bool = True) -> str:
        if ready:
            return "completed"
        return "pending" if prerequisite else "not_selected"

    def source_ready(*groups: str) -> bool:
        return any(int(source_group_counts.get(group) or 0) > 0 for group in groups)

    def add(
        block_key: str,
        title: str,
        stage: str,
        group: str,
        status: str,
        tone: str,
        *,
        summary: str = "",
        related_sections: list[str] | None = None,
        source_groups: list[str] | None = None,
        detail_type: str = "section",
        payload_extra: dict | None = None,
        markdown: str | None = None,
        agent: str = "Analysis Runtime",
        team: str = "Main View",
    ) -> None:
        payload = {
            "block_key": block_key,
            "title": title,
            "stage": stage,
            "group": group,
            "status": status,
            "tone": tone,
            "detail_type": detail_type,
            "related_sections": related_sections or [],
            "source_groups": source_groups or [],
        }
        if payload_extra:
            payload.update(payload_extra)
        sections.append(
            {
                "section_key": f"flow_block_{block_key}",
                "title": title,
                "agent": agent,
                "team": team,
                "markdown": markdown or _flow_block_markdown(title, status, summary, payload),
                "artifact_type": "flow_block",
                "flow_stage": stage,
                "flow_group": group,
                "source_kind": "flow_block",
                "source_key": block_key,
                "summary": summary,
                "payload_json": payload,
            }
        )

    source_specs = [
        ("ccxt_data", "CCXT Market Data", "market", "ccxt_market_data", "ccxt", ["ccxt_market_data"], False),
        ("market_summary", "Market Summary", "market", "ccxt_market_data", "ccxt", ["ccxt_market_data"], True),
        ("coinglass_data", "CoinGlass Data", "onchain", "coinglass_data", "coinglass", ["coinglass_data"], False),
        ("coinglass_summary", "Onchain Endpoint Summary", "onchain", "coinglass_data", "coinglass", ["coinglass_data", "endpoint_summaries"], True),
        ("news_data", "News Data", "news", "news_data", "news", ["news_data"], False),
        ("news_summary", "News Summary", "news", "news_data", "news", ["news_data"], True),
        ("social_data", "Social / Web Data", "social", "social_web_data", "social", ["social_web_data"], False),
        ("social_summary", "Social Summary", "social", "social_web_data", "social", ["social_web_data"], True),
    ]
    for block_key, title, analyst_key, group, bucket, source_groups, is_summary in source_specs:
        artifacts = _source_group_artifacts(flow_artifacts, group)
        summaries = _filter_endpoint_summaries(endpoint_summaries, bucket)
        ready = bool(summaries or artifacts or source_ready(group))
        selected = analyst_key in selected_analysts
        block_markdown = None
        detail_type = "source_summary" if is_summary else "source_group"
        block_summary = f"{title} source package for Main View."
        if is_summary:
            block_markdown = _source_group_summary_markdown(title, summaries, artifacts)
            block_summary = f"{len(summaries)} endpoint summary item(s), {len(artifacts)} source artifact(s)."
        else:
            block_summary = f"{len(artifacts)} source artifact(s) captured for {title}."
        add(
            block_key,
            title,
            "sources",
            group,
            status_for(ready, selected),
            "source",
            summary=block_summary,
            source_groups=source_groups,
            detail_type=detail_type,
            payload_extra={
                "endpoint_summary_count": len(summaries),
                "source_artifact_count": len(artifacts),
                "source_artifact_keys": [str(item.get("section_key") or "") for item in artifacts if item.get("section_key")],
                "source_artifacts": [
                    {
                        "section_key": str(item.get("section_key") or ""),
                        "title": str(item.get("title") or ""),
                        "source_kind": str(item.get("source_kind") or ""),
                        "source_key": str(item.get("source_key") or ""),
                        "summary": str(item.get("summary") or ""),
                    }
                    for item in artifacts[:48]
                ],
                "endpoint_summaries": summaries[:24],
            },
            markdown=block_markdown,
            agent="Source Layer",
            team="Source Layer",
        )

    evidence_ready = bool(final_state.get("evidence_items"))
    add("evidence_extractor", "Evidence Extractor", "evidence", "evidence_extractor", status_for(evidence_ready), "evidence", related_sections=["structured_evidence"], summary="Extracted structured evidence from source-backed analyst outputs.")

    analyst_specs = [
        ("market_analyst", "Market Analyst", "market", "market_report"),
        ("social_analyst", "Social Analyst", "social", "sentiment_report"),
        ("news_analyst", "News Analyst", "news", "news_report"),
        ("onchain_analyst", "Onchain Analyst", "onchain", "onchain_report"),
    ]
    for block_key, title, analyst_key, section_key in analyst_specs:
        selected = analyst_key in selected_analysts
        add(
            block_key,
            title,
            "analysts",
            "analyst_reports",
            status_for(has_text(section_key), selected),
            "signal",
            related_sections=[section_key],
            summary=f"{title} report block.",
            agent=title,
            team="Analyst Team",
        )

    add("evidence_ledger", "Evidence Ledger", "evidence", "evidence_extractor", status_for(evidence_ready), "evidence", related_sections=["structured_evidence"], summary="Evidence ledger available to downstream agents.")

    investment = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    add("bull_researcher", "Bull Researcher", "research", "research_debate", status_for(bool(investment.get("bull_history"))), "bull", related_sections=["bull_research"], agent="Bull Researcher", team="Research Team")
    add("bear_researcher", "Bear Researcher", "research", "research_debate", status_for(bool(investment.get("bear_history"))), "bear", related_sections=["bear_research"], agent="Bear Researcher", team="Research Team")
    add("research_debate", "Research Debate", "research", "research_debate", status_for(bool(investment.get("history"))), "debate", related_sections=["research_debate"], agent="Research Team", team="Research Team")
    add("aggressive_risk", "Aggressive Analyst", "risk", "risk_debate", status_for(bool(risk.get("aggressive_history") or risk.get("current_aggressive_response"))), "aggressive", related_sections=["aggressive_risk"], agent="Aggressive Analyst", team="Risk Team")
    add("conservative_risk", "Conservative Analyst", "risk", "risk_debate", status_for(bool(risk.get("conservative_history") or risk.get("current_conservative_response"))), "conservative", related_sections=["conservative_risk"], agent="Conservative Analyst", team="Risk Team")
    add("neutral_risk", "Neutral Analyst", "risk", "risk_debate", status_for(bool(risk.get("neutral_history") or risk.get("current_neutral_response"))), "neutral", related_sections=["neutral_risk"], agent="Neutral Analyst", team="Risk Team")
    add("risk_debate", "Risk Debate", "risk", "risk_debate", status_for(bool(risk.get("history"))), "risk", related_sections=["risk_debate"], agent="Risk Team", team="Risk Team")
    add("portfolio_manager", "Portfolio Manager", "portfolio", "final_trade_decision", status_for(has_text("final_trade_decision")), "decision", related_sections=["final_trade_decision"], agent="Portfolio Manager", team="Portfolio Management")
    add("verifier", "Verifier", "portfolio", "verification_report", status_for(has_text("verification_report")), "review", related_sections=["verification_report", "verification_report_structured"], agent="Verifier", team="Portfolio Management")
    add("decision_extractor", "Decision Extractor", "extraction", "final_trade_decision_structured", status_for(has_payload("final_trade_decision_structured")), "evidence", related_sections=["final_trade_decision_structured"], agent="Decision Extractor", team="Portfolio Management")
    add("persistence", "History + Decision Persistence", "persistence", "history_persistence", "completed", "evidence", related_sections=["history_persistence"], agent="History Store", team="Persistence")
    return sections


def build_history_sections(final_state: dict) -> list[dict]:
    sections: list[dict] = []
    seen_keys: set[str] = set()

    def add(section: dict | None) -> None:
        if not section:
            return
        key = str(section.get("section_key") or "").strip()
        if not key or key in seen_keys:
            return
        seen_keys.add(key)
        sections.append(section)

    for artifact in final_state.get("flow_artifacts") or []:
        if isinstance(artifact, dict):
            add(artifact)

    for flow_block in _build_flow_block_sections(final_state):
        add(flow_block)

    add(
        _history_section(
            "endpoint_summaries",
            "Endpoint Summaries",
            "Endpoint Summarizer",
            "Source Layer",
            _endpoint_summaries_to_markdown(final_state.get("endpoint_summaries") or []),
            artifact_type="summary",
            flow_stage="summaries",
            flow_group="endpoint_summaries",
            source_kind="summary",
            source_key="endpoint_summaries",
            payload_json=final_state.get("endpoint_summaries") or [],
        )
    )

    evidence_markdown = evidence_items_to_markdown(final_state.get("evidence_items") or [])
    add(
        _history_section(
            "structured_evidence",
            "Structured Evidence",
            "Evidence Extractor",
            "Verification",
            evidence_markdown,
            artifact_type="evidence",
            flow_stage="evidence",
            flow_group="evidence_extractor",
            source_kind="evidence",
            source_key="structured_evidence",
            payload_json=final_state.get("evidence_items") or [],
        )
    )

    for section_key in ("market_report", "onchain_report", "sentiment_report", "news_report"):
        meta = SECTION_META[section_key]
        add(
            _history_section(
                section_key,
                meta["title"],
                meta["agent"],
                meta["team"],
                final_state.get(section_key),
                artifact_type="agent_report",
                flow_stage="analysts",
                flow_group="analyst_reports",
                source_kind="agent_report",
                source_key=section_key,
            )
        )

    investment = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    extra_sections = [
        ("bull_research", "Bull Research", "Bull Researcher", "Research Team", investment.get("bull_history"), "research", "research_debate"),
        ("bear_research", "Bear Research", "Bear Researcher", "Research Team", investment.get("bear_history"), "research", "research_debate"),
        ("research_debate", "Research Debate", "Research Team", "Research Team", investment.get("history"), "research", "research_debate"),
        ("aggressive_risk", "Aggressive Risk", "Aggressive Analyst", "Risk Team", risk.get("aggressive_history") or risk.get("current_aggressive_response"), "risk", "risk_debate"),
        ("conservative_risk", "Conservative Risk", "Conservative Analyst", "Risk Team", risk.get("conservative_history") or risk.get("current_conservative_response"), "risk", "risk_debate"),
        ("neutral_risk", "Neutral Risk", "Neutral Analyst", "Risk Team", risk.get("neutral_history") or risk.get("current_neutral_response"), "risk", "risk_debate"),
        ("risk_debate", "Risk Debate", "Risk Team", "Risk Team", risk.get("history"), "risk", "risk_debate"),
    ]
    for section_key, title, agent, team, markdown, flow_stage, flow_group in extra_sections:
        add(
            _history_section(
                section_key,
                title,
                agent,
                team,
                markdown,
                artifact_type="agent_report",
                flow_stage=flow_stage,
                flow_group=flow_group,
                source_kind="agent_report",
                source_key=section_key,
            )
        )

    for section_key in ("final_trade_decision", "verification_report"):
        meta = SECTION_META[section_key]
        add(
            _history_section(
                section_key,
                meta["title"],
                meta["agent"],
                meta["team"],
                final_state.get(section_key),
                artifact_type="agent_report",
                flow_stage="decision",
                flow_group=section_key,
                source_kind="agent_report",
                source_key=section_key,
            )
        )

    structured_sections = [
        ("onchain_analysis_structured", "Onchain Analysis Payload", "Onchain Analyst", "Analyst Team", final_state.get("onchain_analysis_structured")),
        ("final_trade_decision_structured", "Decision Extractor", "Decision Extractor", "Portfolio Management", final_state.get("final_trade_decision_structured")),
        ("verification_report_structured", "Verifier Structured Payload", "Verifier", "Portfolio Management", final_state.get("verification_report_structured")),
    ]
    for section_key, title, agent, team, payload in structured_sections:
        add(
            _history_section(
                section_key,
                title,
                agent,
                team,
                _structured_payload_to_markdown(title, payload),
                artifact_type="structured_payload",
                flow_stage="extraction",
                flow_group=section_key,
                source_kind="structured_payload",
                source_key=section_key,
                payload_json=payload or {},
            )
        )
    add(
        _history_section(
            "history_persistence",
            "History + Decision Persistence",
            "History Store",
            "Persistence",
            "\n".join(
                [
                    "# History + Decision Persistence",
                    "",
                    "- Markdown/source sections were prepared from runtime state, source artifacts, debates, and final reports.",
                    "- Structured decision and verification payloads were prepared from `final_trade_decision_structured` and `verification_report_structured`.",
                    "- Numeric compatibility fields are written only when the structured decision passes validation.",
                ]
            ),
            artifact_type="persistence",
            flow_stage="persistence",
            flow_group="history_persistence",
            source_kind="persistence",
            source_key="history_persistence",
        )
    )
    return sections
