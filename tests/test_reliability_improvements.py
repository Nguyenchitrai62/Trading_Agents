"""Tests for reliability and accuracy improvements."""

from __future__ import annotations

import pytest

from tradingagents.agents.managers.verifier import _build_deterministic_summary
from tradingagents.dataflows.coinglass_client import (
    HIGH_VALUE_ENDPOINTS,
    fetch_high_value_snapshot,
)
from tradingagents.graph.builder import GraphSetup
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.parallel_analysts import create_parallel_analyst_team


class TestVerifierLimitBuyBreakout:
    def _build_state(
        self,
        signal: str,
        primary_limit_buy_price: float | None = None,
        secondary_limit_buy_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        execution_summary: str = "",
        market_context: str = "",
        investment_thesis: str = "",
        current_price: float = 100.0,
    ) -> dict:
        return {
            "company_of_interest": "BTC-USDT",
            "final_trade_decision_structured": {
                "signal": signal,
                "primary_limit_buy_price": primary_limit_buy_price,
                "secondary_limit_buy_price": secondary_limit_buy_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "execution_summary": execution_summary,
                "market_context": market_context,
                "investment_thesis": investment_thesis,
            },
            "final_trade_decision": f"{signal}\n\n{execution_summary}\n{market_context}\n{investment_thesis}",
            "verification_reference_price": current_price,
        }

    def test_limit_buy_breakout_above_current_is_allowed(self):
        state = self._build_state(
            signal="Limit Buy",
            primary_limit_buy_price=105.0,
            secondary_limit_buy_price=103.0,
            stop_loss=98.0,
            take_profit=115.0,
            investment_thesis="Wait for a confirmed breakout above the local resistance before entering.",
            current_price=100.0,
        )
        summary = _build_deterministic_summary(state)
        assert "above current spot price" not in "\n".join(summary["blockers"])

    def test_limit_buy_above_current_blocked_without_breakout(self):
        state = self._build_state(
            signal="Limit Buy",
            primary_limit_buy_price=105.0,
            secondary_limit_buy_price=103.0,
            stop_loss=98.0,
            take_profit=115.0,
            investment_thesis="Scale into the dip because price looks cheap.",
            current_price=100.0,
        )
        summary = _build_deterministic_summary(state)
        assert any("above current spot price" in blocker for blocker in summary["blockers"])


class TestVerifierMarketSell:
    def _build_state(
        self,
        stop_loss: float | None,
        take_profit: float | None,
        current_price: float = 100.0,
    ) -> dict:
        return {
            "company_of_interest": "BTC-USDT",
            "final_trade_decision_structured": {
                "signal": "Market Sell",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
            "final_trade_decision": f"Market Sell\n\nStop Loss: {stop_loss}\nTake Profit: {take_profit}",
            "verification_reference_price": current_price,
        }

    def test_market_sell_stop_loss_below_current_blocked(self):
        state = self._build_state(stop_loss=99.0, take_profit=90.0, current_price=100.0)
        summary = _build_deterministic_summary(state)
        assert any("stop-loss" in blocker.lower() for blocker in summary["blockers"])

    def test_market_sell_take_profit_above_current_blocked(self):
        state = self._build_state(stop_loss=105.0, take_profit=110.0, current_price=100.0)
        summary = _build_deterministic_summary(state)
        assert any("take-profit" in blocker.lower() for blocker in summary["blockers"])

    def test_market_sell_valid_levels_allowed(self):
        state = self._build_state(stop_loss=105.0, take_profit=90.0, current_price=100.0)
        summary = _build_deterministic_summary(state)
        assert not summary["blockers"]


class TestDecisionExtractorInGraph:
    def test_graph_setup_imports_decision_extractor(self):
        # The builder module must import and create the decision extractor node.
        import tradingagents.graph.builder as builder_module
        assert hasattr(builder_module, "create_decision_extractor")

    def test_verifier_routes_to_decision_extractor_when_approved(self):
        state = {
            "verification_report_structured": {"verdict": "Approved"},
            "decision_revision_count": 0,
        }
        conditional_logic = ConditionalLogic()
        assert conditional_logic.should_continue_portfolio_verification(state) == "Decision Extractor"

    def test_verifier_routes_to_pm_for_revision(self):
        state = {
            "verification_report_structured": {"verdict": "Revise"},
            "decision_revision_count": 0,
        }
        conditional_logic = ConditionalLogic()
        assert conditional_logic.should_continue_portfolio_verification(state) == "Portfolio Manager"

    def test_verifier_routes_to_extractor_after_max_revisions(self):
        state = {
            "verification_report_structured": {"verdict": "Revise"},
            "decision_revision_count": 5,
        }
        conditional_logic = ConditionalLogic()
        assert conditional_logic.should_continue_portfolio_verification(state) == "Decision Extractor"


class TestSMA200Weekly:
    def test_weekly_bundle_has_sma200_values(self):
        from tradingagents.dataflows.ccxt_crypto import get_crypto_bundle

        bundle = get_crypto_bundle("BTC-USDT", "1w", preview_limit=50)
        indicators = bundle.get("indicators", {})
        assert "close_200_sma" in indicators
        # The SMA200 indicator text should contain at least some numeric values.
        sma_text = indicators["close_200_sma"]
        assert "N/A" in sma_text or any(char.isdigit() for char in sma_text)


class TestCoinGlassSymbolFiltering:
    def test_btc_only_endpoints_are_filtered_for_eth(self):
        btc_only_keys = {"etf_bitcoin_flow_history", "etf_bitcoin_list", "grayscale_holdings_list", "stock_flow"}
        eth_applicable = [
            spec
            for spec in HIGH_VALUE_ENDPOINTS
            if spec.applicable_coins is None or "ETH" in spec.applicable_coins
        ]
        eth_keys = {spec.key for spec in eth_applicable}
        assert not btc_only_keys & eth_keys

    def test_btc_endpoints_remain_for_btc(self):
        btc_applicable = [
            spec
            for spec in HIGH_VALUE_ENDPOINTS
            if spec.applicable_coins is None or "BTC" in spec.applicable_coins
        ]
        btc_keys = {spec.key for spec in btc_applicable}
        assert "etf_bitcoin_flow_history" in btc_keys
        assert "stock_flow" in btc_keys

    def test_macro_endpoints_are_kept_for_altcoins(self):
        macro_keys = {spec.key for spec in HIGH_VALUE_ENDPOINTS if spec.is_macro}
        eth_applicable = [
            spec
            for spec in HIGH_VALUE_ENDPOINTS
            if spec.applicable_coins is None or "ETH" in spec.applicable_coins
        ]
        eth_keys = {spec.key for spec in eth_applicable}
        assert macro_keys <= eth_keys


class TestParallelAnalystCrashIsolation:
    def test_run_analyst_catches_exception(self):
        from tradingagents.graph.analyst_execution import AnalystExecutionPlan, AnalystNodeSpec
        from langgraph.prebuilt import ToolNode

        def crashing_node(state):
            raise RuntimeError("Simulated analyst crash")

        plan = AnalystExecutionPlan(
            specs=[
                AnalystNodeSpec(
                    key="market",
                    agent_node="Market Analyst",
                    tool_node="tools_market",
                    clear_node="Msg Clear Market",
                    report_key="market_report",
                )
            ],
            concurrency_limit=1,
        )
        team_node = create_parallel_analyst_team(
            plan,
            {"market": lambda: crashing_node},
            {"market": ToolNode([])},
            max_tool_iterations=1,
        )
        result = team_node({})
        assert "market_report" in result
        assert "failed" in str(result["market_report"]).lower() or "error" in str(result["market_report"]).lower()
