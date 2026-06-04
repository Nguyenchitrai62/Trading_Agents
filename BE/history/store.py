from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta

import requests

from ..config import SETTINGS
from ..models import AnalysisRequest
from tradingagents.agents.utils.decision import compatibility_decision_fields


class TursoHistoryStore:
    def __init__(self, database_url: str, auth_token: str, page_size: int = SETTINGS.history_page_size):
        self.database_url = database_url.strip()
        self.auth_token = auth_token.strip()
        self.page_size = page_size
        self._schema_ready = False
        self._schema_error = ""
        self._schema_lock = threading.Lock()
        self._session: requests.Session | None = None

    @property
    def configured(self) -> bool:
        return bool(self.database_url and self.auth_token)

    def _ensure_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=2,
                pool_maxsize=4,
                max_retries=0,
            )
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        return self._session

    @staticmethod
    def _extract_md_numeric(markdown: str, labels: list[str]) -> float | None:
        import re
        if not markdown or not labels:
            return None
        for label in labels:
            escaped = re.escape(label)
            pattern = rf'(?i)(?:^|\n)\s*[-*]*\s*\**\s*{escaped}\s*\**\s*[:=-]\s*\$?\s*([\d,]+(?:\.\d+)?)'
            match = re.search(pattern, markdown)
            if match:
                raw = match.group(1).replace(",", "").replace("$", "").strip()
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    continue
        return None

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
        response = self._ensure_session().post(
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
                "DROP TABLE IF EXISTS analysis_decisions",
                "DROP TABLE IF EXISTS analysis_sections",
                "DROP TABLE IF EXISTS analysis_runs",
                """
                CREATE TABLE analysis_runs (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    quick_think_model TEXT NOT NULL,
                    deep_think_model TEXT NOT NULL,
                    output_language TEXT NOT NULL,
                    research_depth TEXT NOT NULL,
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

    def list_users(self, default_history_access_days: int, admin_emails: frozenset[str], limit: int = 500, offset: int = 0) -> list[dict]:
        self.ensure_schema()
        rows = self._query_rows(
            """
            SELECT email, google_sub, name, picture, email_verified, is_admin,
                can_run_analysis, history_access_unlimited, history_access_days, first_seen_at, last_seen_at
            FROM auth_users
            ORDER BY last_seen_at DESC
            LIMIT ?
            OFFSET ?
            """,
            [limit, offset],
        )
        users = [self._format_user_access(row, row["email"], default_history_access_days, admin_emails) for row in rows]
        if offset == 0:
            seen = {user["email"] for user in users}
            for email in sorted(admin_emails - seen):
                users.append(self._format_user_access(None, email, default_history_access_days, admin_emails))
        return users

    def count_users(self) -> int:
        self.ensure_schema()
        rows = self._query_rows("SELECT COUNT(*) AS total_count FROM auth_users", [])
        return int((rows[0].get("total_count") or 0) if rows else 0)

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
            return "1970-01-01T00:00:00Z"
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
                    id, symbol, asset_type, analysis_date, quick_think_model, deep_think_model,
                    output_language, research_depth, signal, elapsed_seconds, section_count, user_email, user_sub, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    symbol = excluded.symbol,
                    asset_type = excluded.asset_type,
                    analysis_date = excluded.analysis_date,
                    quick_think_model = excluded.quick_think_model,
                    deep_think_model = excluded.deep_think_model,
                    output_language = excluded.output_language,
                    research_depth = excluded.research_depth,
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
                    request.quick_think_model,
                    request.deep_think_model,
                    request.output_language,
                    request.research_depth,
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
            if not decision_signal:
                decision_signal = signal
            final_markdown = ""
            for section in (sections or []):
                if str(section.get("section_key") or "").strip() == "final_trade_decision":
                    final_markdown = str(section.get("markdown") or "").strip()
                    break
            if final_markdown:
                if not decision_signal or decision_signal in ("", "Completed"):
                    from tradingagents.agents.utils.rating import parse_rating
                    decision_signal = str(parse_rating(final_markdown, default=decision_signal or signal)).strip()
                if decision_fields.get("primary_limit_price") is None:
                    decision_fields["primary_limit_price"] = self._extract_md_numeric(
                        final_markdown,
                        ["Primary Limit Buy", "Limit Buy Price", "Buy Limit", "Entry Limit", "Primary Limit Buy Price",
                         "Primary Limit Sell", "Limit Sell Price", "Sell Limit", "Exit Limit", "Primary Limit Sell Price"],
                    )
                if decision_fields.get("secondary_limit_price") is None:
                    decision_fields["secondary_limit_price"] = self._extract_md_numeric(
                        final_markdown,
                        ["Secondary Limit Buy", "Secondary Buy Limit", "Secondary Limit Buy Price",
                         "Secondary Limit Sell", "Secondary Sell Limit", "Secondary Limit Sell Price"],
                    )
                if decision_fields.get("stop_loss") is None:
                    decision_fields["stop_loss"] = self._extract_md_numeric(
                        final_markdown,
                        ["Stop Loss", "Stop-Loss", "Stop loss", "Invalidation Level", "Invalidation"],
                    )
                if decision_fields.get("take_profit") is None:
                    decision_fields["take_profit"] = self._extract_md_numeric(
                        final_markdown,
                        ["Take Profit", "Take-Profit", "Take profit", "Target", "Profit Target", "Exit Target", "Exit Objective"],
                    )
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
                r.id, r.symbol, r.asset_type, r.analysis_date,
                r.quick_think_model, r.deep_think_model,
                r.output_language, r.research_depth,
                d.signal,
                d.current_price, d.primary_limit_price, d.secondary_limit_price,
                d.stop_loss, d.take_profit, d.position_sizing, d.time_horizon,
                d.verification_verdict, d.verification_action,
                r.elapsed_seconds, r.created_at, r.section_count,
                fm.markdown AS final_markdown
            FROM analysis_runs r
            LEFT JOIN analysis_decisions d ON d.run_id = r.id
            LEFT JOIN (
                SELECT run_id, MAX(markdown) AS markdown
                FROM analysis_sections
                WHERE section_key = 'final_trade_decision'
                GROUP BY run_id
            ) fm ON fm.run_id = r.id
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
                r.id, r.symbol, r.asset_type, r.analysis_date,
                r.quick_think_model, r.deep_think_model,
                r.output_language, r.research_depth,
                d.signal,
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
        where_clause = "WHERE r.created_at <= ?" if cutoff else ""
        args: list[object] = [cutoff] if cutoff else []
        args.extend([safe_limit, offset])
        return self._query_rows(
            f"""
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date,
                r.quick_think_model, r.deep_think_model,
                r.output_language, r.research_depth,
                d.signal,
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
        extra_where = "AND r.created_at <= ?" if cutoff else ""
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
        where_clause = "WHERE created_at <= ?" if cutoff else ""
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
        where_clause = "AND r.created_at <= ?" if cutoff else ""
        args: list[object] = [run_id]
        if cutoff:
            args.append(cutoff)
        runs = self._query_rows(
            f"""
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date,
                r.quick_think_model, r.deep_think_model,
                r.output_language, r.research_depth,
                d.signal,
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
                r.id, r.symbol, r.asset_type, r.analysis_date,
                r.quick_think_model, r.deep_think_model,
                r.output_language, r.research_depth,
                d.signal,
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
                r.id, r.symbol, r.asset_type, r.analysis_date,
                r.quick_think_model, r.deep_think_model,
                r.output_language, r.research_depth,
                d.signal,
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
