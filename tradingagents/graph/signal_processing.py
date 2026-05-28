"""Extract the final execution signal from the Portfolio Manager's decision.

The Portfolio Manager produces a typed ``PortfolioDecision`` via structured
output and renders it to markdown that carries a stable ``**Signal**: X``
header (see :func:`tradingagents.agents.schemas.render_pm_decision`). The
deterministic heuristic in :mod:`tradingagents.agents.utils.rating` is more
than sufficient to extract that signal; no extra LLM call is needed.

This module exists for backwards compatibility with callers that expect a
``SignalProcessor.process_signal(text)`` interface.
"""

from __future__ import annotations

from typing import Any

from tradingagents.agents.utils.rating import parse_rating


class SignalProcessor:
    """Read the final execution signal out of a Portfolio Manager decision."""

    def __init__(self, quick_thinking_llm: Any = None):
        # The LLM argument is accepted for backwards compatibility but no
        # longer used: the PM's structured output guarantees the signal is
        # parseable from the rendered markdown without a second LLM call.
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """Return the final execution signal, e.g. Limit Buy or Market Sell."""
        return parse_rating(full_signal)
