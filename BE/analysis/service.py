from __future__ import annotations

import threading
import time
from copy import deepcopy

from fastapi import HTTPException

from ..config import RESEARCH_DEPTH_OPTIONS, BackendSettings, logger, resolve_provider_settings, is_deepseek_model
from ..history import TursoHistoryStore
from ..models import AnalysisRequest

from .constants import STATE_UPDATE_KEYS
from .formatting_mixin import AnalysisFormattingMixin
from .chat_mixin import AnalysisChatMixin
from .prefetch_mixin import AnalysisPrefetchMixin
from .graph_mixin import AnalysisGraphMixin
from .emitter_mixin import AnalysisEmitterMixin
from .orchestrator_mixin import AnalysisOrchestratorMixin

try:
    from tradingagents.agent_config import DEFAULT_CONFIG as TRADINGAGENTS_DEFAULT_CONFIG
    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
    from tradingagents.graph.checkpointer import (
        checkpoint_step,
        clear_checkpoint,
        get_checkpointer,
        thread_id,
    )
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ANALYSIS_RUNTIME_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:
    TRADINGAGENTS_DEFAULT_CONFIG = {}
    ANALYST_NODE_SPECS = {}
    checkpoint_step = None
    clear_checkpoint = None
    get_checkpointer = None
    thread_id = None
    TradingAgentsGraph = None
    ANALYSIS_RUNTIME_IMPORT_ERROR = exc


class AnalysisService(
    AnalysisFormattingMixin,
    AnalysisChatMixin,
    AnalysisPrefetchMixin,
    AnalysisGraphMixin,
    AnalysisEmitterMixin,
    AnalysisOrchestratorMixin,
):
    def __init__(self, settings: BackendSettings, history_store: TursoHistoryStore):
        self.settings = settings
        self.history_store = history_store
        self.active_analysis_cancel_events: dict[str, threading.Event] = {}
        self.active_analysis_lock = threading.Lock()
        self.active_analysis_count = 0
        self.active_analyses: dict[str, dict] = {}
        self._active_analyses_lock = threading.Lock()

    def ensure_analysis_runtime_available(self) -> None:
        if ANALYSIS_RUNTIME_IMPORT_ERROR is None:
            return
        missing_name = ANALYSIS_RUNTIME_IMPORT_ERROR.name or "analysis dependency"
        raise HTTPException(
            status_code=500,
            detail=(
                "Analysis runtime dependencies are unavailable. Install the missing package "
                f"'{missing_name}' to use /api/analyze."
            ),
        )

    @staticmethod
    def normalize_ticker_symbol(ticker: str) -> str:
        normalized = ticker.strip().upper().replace(" ", "")
        if normalized and "/" not in normalized and "-" not in normalized:
            return f"{normalized}-USDT"
        return normalized

    @staticmethod
    def filter_analysts_for_crypto(selected_analysts: list[str]) -> list[str]:
        return [str(analyst or "").strip().lower() for analyst in selected_analysts if str(analyst or "").strip()]

    def try_reserve_analysis_slot(self) -> bool:
        with self.active_analysis_lock:
            if self.active_analysis_count >= self.settings.analysis_max_concurrent_runs:
                return False
            self.active_analysis_count += 1
            return True

    def release_analysis_slot(self) -> None:
        with self.active_analysis_lock:
            if self.active_analysis_count > 0:
                self.active_analysis_count -= 1

    def cancel_run(self, run_id: str) -> dict:
        with self.active_analysis_lock:
            cancel_event = self.active_analysis_cancel_events.get(run_id)

        if cancel_event is None:
            return {
                "cancelled": False,
                "run_id": run_id,
                "message": "No active analysis stream matched this run id.",
            }

        cancel_event.set()
        logger.info("analysis cancel requested: run_id=%s", run_id)
        return {
            "cancelled": True,
            "run_id": run_id,
            "message": "Cancellation requested for the active analysis stream.",
        }

    def _register_active_run(self, run_id: str, symbol: str, user: dict, started_at: float) -> None:
        if not run_id:
            return
        with self._active_analyses_lock:
            self.active_analyses[run_id] = {
                "run_id": run_id,
                "symbol": symbol,
                "user_email": str(user.get("email") or ""),
                "user_name": str(user.get("name") or ""),
                "started_at": started_at,
            }

    def _unregister_active_run(self, run_id: str) -> None:
        if not run_id:
            return
        with self._active_analyses_lock:
            self.active_analyses.pop(run_id, None)

    def list_active_runs(self) -> list[dict]:
        with self._active_analyses_lock:
            now = time.time()
            return [
                {
                    "run_id": run["run_id"],
                    "symbol": run["symbol"],
                    "user_email": run["user_email"],
                    "user_name": run["user_name"],
                    "started_at": run["started_at"],
                    "elapsed_seconds": round(now - run["started_at"], 1),
                }
                for run in self.active_analyses.values()
            ]

    def has_active_runs(self) -> bool:
        with self._active_analyses_lock:
            return len(self.active_analyses) > 0

    def run_analysis_background(self, request: AnalysisRequest, on_complete: Callable[[], None] | None = None) -> str:
        run_id = request.run_id or ""
        started_at = time.time()
        user = {
            "email": "auto-analysis@system",
            "name": "Auto Analysis",
            "is_admin": True,
            "can_run_analysis": True,
        }
        cancel_event = threading.Event()

        def _noop_emit(_event: str, _data: dict) -> None:
            pass

        if run_id:
            with self.active_analysis_lock:
                self.active_analysis_cancel_events[run_id] = cancel_event
        self._register_active_run(run_id, request.symbol, user, started_at)

        def _run() -> None:
            try:
                self.run_trading_analysis(request, _noop_emit, user, cancel_event)
            except Exception:
                logger.exception("auto-analysis background run failed: run_id=%s symbol=%s", run_id, request.symbol)
            finally:
                if run_id:
                    with self.active_analysis_lock:
                        self.active_analysis_cancel_events.pop(run_id, None)
                self._unregister_active_run(run_id)
                if on_complete is not None:
                    try:
                        on_complete()
                    except Exception:
                        pass

        threading.Thread(target=_run, daemon=True, name=f"auto-analysis-{run_id}").start()
        return run_id

    def build_analysis_runtime_profile(self, request: AnalysisRequest) -> dict:
        depth_config = RESEARCH_DEPTH_OPTIONS[request.research_depth]
        effective_depth = str(depth_config.get("effective_depth") or request.research_depth)
        requested_rounds = depth_config["rounds"]
        auto_escalation = bool(depth_config.get("auto_escalation"))
        return {
            "requested_depth": request.research_depth,
            "effective_depth": effective_depth,
            "requested_rounds": requested_rounds,
            "effective_rounds": requested_rounds,
            "llm_max_tokens": self.settings.analysis_llm_max_tokens,
            "mcp_max_tool_rounds": depth_config["mcp_tool_rounds"],
            "auto_escalation": auto_escalation,
        }

    def build_analysis_config(
        self,
        request: AnalysisRequest,
        provider_settings: dict,
        runtime_profile: dict,
        selected_analysts: list[str],
    ) -> dict:
        config = deepcopy(TRADINGAGENTS_DEFAULT_CONFIG)
        is_deepseek = is_deepseek_model(request.quick_think_model)
        analyst_count = len(selected_analysts)
        analyst_parallelism = max(analyst_count, config.get("analyst_concurrency_limit", analyst_count))
        config.update(
            {
                "llm_provider": provider_settings["provider"],
                "quick_think_llm": request.quick_think_model,
                "deep_think_llm": request.deep_think_model,
                "backend_url": provider_settings["base_url"],
                "output_language": request.output_language,
                "analysis_date": request.analysis_date,
                "max_debate_rounds": runtime_profile["effective_rounds"],
                "max_risk_discuss_rounds": runtime_profile["effective_rounds"],
                "analysis_llm_max_tokens": runtime_profile["llm_max_tokens"],
                "minimax_mcp_max_tool_rounds": runtime_profile["mcp_max_tool_rounds"],
                "minimax_mcp_enabled": False if is_deepseek else config.get("minimax_mcp_enabled", True),
                "analyst_concurrency_limit": analyst_parallelism,
                "openai_quick_reasoning_effort": request.quick_reasoning_effort,
                "openai_deep_reasoning_effort": request.deep_reasoning_effort,
                "checkpoint_enabled": request.checkpoint_enabled,
            }
        )
        owner_key = str(config.get("coinglass_owner_analyst") or "").strip()
        if owner_key not in selected_analysts:
            owner_key = selected_analysts[0]

        owner_spec = ANALYST_NODE_SPECS.get(owner_key)
        owner_label = owner_spec.agent_node if owner_spec is not None else str(
            config.get("coinglass_owner_agent_label") or owner_key or "Analyst"
        ).strip()
        config["coinglass_owner_analyst"] = owner_key
        config["coinglass_owner_agent_label"] = owner_label
        return config
