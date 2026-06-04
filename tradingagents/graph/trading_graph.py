# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.minimax_mcp import (
    get_minimax_mcp_langchain_tools,
    merge_tools_by_name,
    resolve_minimax_mcp_settings,
)

from tradingagents.agents import *
from tradingagents.agent_config import DEFAULT_CONFIG
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_crypto_indicators,
    get_crypto_ohlcv,
)
from tradingagents.agents.utils.web_search_tools import webfetch

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .builder import GraphSetup
from .propagation import Propagator
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "onchain", "social", "news"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Create necessary directories
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Initialize LLMs with provider-specific thinking configuration
        deep_kwargs = self._get_provider_kwargs("deep")
        quick_kwargs = self._get_provider_kwargs("quick")

        if self.callbacks:
            deep_kwargs["callbacks"] = self.callbacks
            quick_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **deep_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **quick_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        mcp_round_budget = int(self.config.get("minimax_mcp_max_tool_rounds") or 0)
        analyst_max_tool_iterations = max(24, mcp_round_budget * 6)
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
            analyst_concurrency_limit=self.config.get("analyst_concurrency_limit", 1),
            analyst_max_tool_iterations=analyst_max_tool_iterations,
            analyst_trace_callback=self.config.get("analysis_trace_callback"),
            cancel_check=self.config.get("analysis_cancel_check"),
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100),
        )
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self, role: str = "quick") -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation.

        Args:
            role: "quick" or "deep" — selects the appropriate reasoning effort config.
        """
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()
        max_tokens = self.config.get("analysis_llm_max_tokens")

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get(f"openai_{role}_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "deepseek":
            kwargs["reasoning_effort"] = self.config.get(f"openai_{role}_reasoning_effort") or "max"

        elif provider in ("anthropic", "minimax", "minimax-cn"):
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

            if provider in ("minimax", "minimax-cn"):
                kwargs.update(
                    {
                        "mcp_enabled": self.config.get("minimax_mcp_enabled", True),
                        "mcp_command": self.config.get("minimax_mcp_command"),
                        "mcp_args": self.config.get("minimax_mcp_args"),
                        "mcp_tool_names": self.config.get("minimax_mcp_tool_names"),
                        "mcp_max_tool_rounds": self.config.get("minimax_mcp_max_tool_rounds"),
                        "mcp_tool_result_char_limit": self.config.get("minimax_mcp_tool_result_char_limit"),
                        "mcp_call_timeout_seconds": self.config.get("minimax_mcp_call_timeout_seconds"),
                        "mcp_list_timeout_seconds": self.config.get("minimax_mcp_list_timeout_seconds"),
                        "mcp_reference_sources": self.config.get("preferred_reference_sources"),
                        "mcp_trace_callback": self.config.get("analysis_trace_callback"),
                    }
                )

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        mcp_tools = []
        provider = self.config.get("llm_provider", "").lower()
        if provider in ("minimax", "minimax-cn"):
            mcp_settings = resolve_minimax_mcp_settings(
                provider=provider,
                base_url=self.config.get("backend_url"),
                enabled=self.config.get("minimax_mcp_enabled", True),
                command=self.config.get("minimax_mcp_command"),
                args=self.config.get("minimax_mcp_args"),
                tool_names=self.config.get("minimax_mcp_tool_names"),
                max_tool_rounds=self.config.get("minimax_mcp_max_tool_rounds"),
                result_char_limit=self.config.get("minimax_mcp_tool_result_char_limit"),
                call_timeout_seconds=self.config.get("minimax_mcp_call_timeout_seconds"),
                list_timeout_seconds=self.config.get("minimax_mcp_list_timeout_seconds"),
            )
            mcp_tools = get_minimax_mcp_langchain_tools(mcp_settings)

        use_web_search_tool = provider == "deepseek"

        def with_mcp(tools: list) -> list:
            merged = merge_tools_by_name(tools, mcp_tools)
            if use_web_search_tool:
                merged = merge_tools_by_name(merged, [webfetch])
            return merged

        return {
            "market": ToolNode(
                with_mcp([
                    get_crypto_ohlcv,
                    get_crypto_indicators,
                ])
            ),
            "social": ToolNode(with_mcp([])),
            "news": ToolNode(with_mcp([])),
            "onchain": ToolNode(with_mcp([])),
        }

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
