import urllib.error
import urllib.request
from typing import Annotated

from langchain_core.tools import tool

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


@tool
def webfetch(
    url: Annotated[str, "The URL to fetch content from."],
    max_chars: Annotated[int, "Maximum characters to return (default 5000)."] = 5000,
) -> str:
    """Fetch content from any URL using urllib. Use this for crypto data APIs,
    news sites, RSS feeds, market data, and any web-based information source.
    The model should decide which URLs are relevant and call this tool accordingly.

    Args:
        url: URL to fetch
        max_chars: Max chars to return (default 5000)
    Returns:
        str: Fetched content (truncated to max_chars) or error message
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        if len(data) > max_chars:
            data = data[:max_chars] + "\n\n[truncated]"
        return data
    except Exception as exc:
        return f"Fetch failed for {url}: {exc}"
