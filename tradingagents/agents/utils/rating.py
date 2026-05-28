"""Shared final-signal vocabulary and a deterministic heuristic parser.

The Portfolio Manager emits actionable execution signals such as
``Market Buy`` or ``Limit Sell``. Only that vocabulary is recognized here.

Centralising the vocabulary here avoids drift between the Portfolio Manager,
the signal processor, and the memory log.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Tuple


# Canonical, ordered actionable signals.
TRADING_SIGNALS: Tuple[str, ...] = (
    "Market Buy", "Limit Buy", "Hold", "Limit Sell", "Market Sell",
)

_SIGNAL_ALIASES = {
    "market buy": "Market Buy",
    "buy now": "Market Buy",
    "limit buy": "Limit Buy",
    "buy limit": "Limit Buy",
    "hold": "Hold",
    "limit sell": "Limit Sell",
    "sell limit": "Limit Sell",
    "market sell": "Market Sell",
    "sell now": "Market Sell",
}

_SIGNAL_ALIAS_PATTERNS = tuple(
    (
        re.compile(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", re.IGNORECASE),
        canonical,
    )
    for alias, canonical in sorted(_SIGNAL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
)

# Match explicit decision labels before falling back to generic signal phrases.
_EXPLICIT_SIGNAL_RES = (
    re.compile(
        r"(?:signal|execution\s+signal|recommendation|action|trading\s+signal)"
        r".*?[:\-][\s*_`#-]*(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:khuyen\s+nghi(?:\s+cuoi\s+cung)?|quyet\s+dinh(?:\s+giao\s+dich)?(?:\s+cuoi\s+cung)?)"
        r".*?[:\-][\s*_`#-]*(.+)",
        re.IGNORECASE,
    ),
)


def _normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _find_signal(value: str) -> str | None:
    normalized = _normalize_search_text(value)
    for pattern, canonical in _SIGNAL_ALIAS_PATTERNS:
        if pattern.search(normalized):
            return canonical
    return None


def parse_rating(text: str, default: str = "Hold") -> str:
    """Heuristically extract the final Portfolio Manager signal from prose text.

    Two-pass strategy:
    1. Look for an explicit decision label such as ``Signal: Limit Buy`` or
       ``Khuyen nghi cuoi cung: Hold``.
    2. Fall back to signal phrases found elsewhere in the text.

    Returns one of the actionable signals. Falls back to ``default`` when
    nothing is parseable.
    """
    for line in text.splitlines():
        normalized_line = _normalize_search_text(line)
        for pattern in _EXPLICIT_SIGNAL_RES:
            match = pattern.search(normalized_line)
            if not match:
                continue
            signal = _find_signal(match.group(1)) or _find_signal(normalized_line)
            if signal:
                return signal

        if any(keyword in normalized_line for keyword in (
            "khuyen nghi",
            "quyet dinh",
            "signal",
            "action",
            "trading signal",
        )):
            signal = _find_signal(normalized_line)
            if signal:
                return signal

    for line in text.splitlines():
        signal = _find_signal(line)
        if signal:
            return signal

    normalized_text = _normalize_search_text(text)
    signal = _find_signal(normalized_text)
    if signal:
        return signal

    return default
