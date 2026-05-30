"""Extract the final execution signal from the Portfolio Manager's prose.

The Portfolio Manager emits readable prose with the first line constrained to
one actionable signal. The deterministic heuristic in
:mod:`tradingagents.agents.utils.rating` is sufficient to extract that signal;
no extra LLM call is needed here.

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
