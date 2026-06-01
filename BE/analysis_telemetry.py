from __future__ import annotations

import io
import logging
import threading
from collections.abc import Callable

from langchain_core.callbacks import BaseCallbackHandler

from .config import logger


def get_process_rss_mb() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        return None
    if usage <= 0:
        return None
    if usage > 10_000_000:
        return round(usage / (1024 * 1024))
    return round(usage / 1024)


class AnalysisCancelled(Exception):
    pass


class AnalysisLogStream(io.TextIOBase):
    def __init__(self, emit_log: Callable[[str, str, str], None], phase: str, level: str):
        self.emit_log = emit_log
        self.phase = phase
        self.level = level
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        if not value:
            return 0
        self._buffer += value
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.emit_log(line.strip(), self.phase, self.level)
        return len(value)

    def flush(self) -> None:
        if self._buffer.strip():
            self.emit_log(self._buffer.strip(), self.phase, self.level)
        self._buffer = ""


class AnalysisLoggingHandler(logging.Handler):
    def __init__(self, emit_log: Callable[[str, str, str], None]):
        super().__init__(level=logging.INFO)
        self.emit_log = emit_log

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == logger.name:
            return
        try:
            level = "warning" if record.levelno >= logging.WARNING else "info"
            self.emit_log(self.format(record), "backend_log", level)
        except Exception:
            self.handleError(record)


class AnalysisTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.model_calls = 0
        self.tool_calls = 0
        self.tool_results = 0
        self.web_search_calls = 0

    def record_model_call(self) -> None:
        with self._lock:
            self.model_calls += 1

    def record_tool_trace(self, phase: str, title: object) -> None:
        normalized_phase = str(phase or "").strip().lower()
        normalized_title = str(title or "").strip()
        with self._lock:
            if normalized_phase == "tool_call":
                self.tool_calls += 1
                if normalized_title == "web_search":
                    self.web_search_calls += 1
            elif normalized_phase == "tool_result":
                self.tool_results += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "model_calls": self.model_calls,
                "tool_calls": self.tool_calls,
                "tool_results": self.tool_results,
                "web_search_calls": self.web_search_calls,
            }


class AnalysisTelemetryCallback(BaseCallbackHandler):
    def __init__(self, telemetry: AnalysisTelemetry) -> None:
        super().__init__()
        self.telemetry = telemetry

    def on_llm_start(self, *args, **kwargs) -> None:
        self.telemetry.record_model_call()

    def on_chat_model_start(self, *args, **kwargs) -> None:
        self.telemetry.record_model_call()
