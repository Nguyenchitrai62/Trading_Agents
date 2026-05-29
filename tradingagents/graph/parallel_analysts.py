from __future__ import annotations

import copy
import logging
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from time import monotonic
from typing import Callable, Dict, Optional

from langchain_core.messages import AIMessage, RemoveMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from .analyst_execution import AnalystExecutionPlan, AnalystNodeSpec


logger = logging.getLogger(__name__)


def _merge_state_update(state: dict, update: dict) -> None:
    for key, value in update.items():
        if key == "messages":
            messages = list(state.get("messages") or [])
            for message in value or []:
                if isinstance(message, RemoveMessage):
                    message_id = getattr(message, "id", None)
                    messages = [
                        existing
                        for existing in messages
                        if getattr(existing, "id", None) != message_id
                    ]
                else:
                    messages.append(message)
            state["messages"] = messages
            continue

        if isinstance(value, dict) and isinstance(state.get(key), dict):
            merged = dict(state[key])
            merged.update(value)
            state[key] = merged
            continue

        if key == "evidence_items":
            state[key] = list(state.get(key) or []) + list(value or [])
            continue

        state[key] = value


def _tool_calls(state: dict) -> list[dict]:
    messages = state.get("messages") or []
    if not messages:
        return []
    return list(getattr(messages[-1], "tool_calls", None) or [])


def _message_content(state: dict) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    content = getattr(messages[-1], "content", "") or ""
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text") or block.get("content") or "").strip()
            if isinstance(block, dict)
            else str(block).strip()
            for block in content
            if block
        ).strip()
    return str(content).strip()


def _message_content_from_message(message: object) -> str:
    content = getattr(message, "content", "") or ""
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text") or block.get("content") or "").strip()
            if isinstance(block, dict)
            else str(block).strip()
            for block in content
            if block
        ).strip()
    return str(content).strip()


def _tool_call_summary(tool_call: dict) -> str:
    name = str(tool_call.get("name") or "tool")
    args = tool_call.get("args") or {}
    if not args:
        return name
    if isinstance(args, dict):
        items = ", ".join(f"{key}={value}" for key, value in list(args.items())[:4])
        return f"{name}({items})"
    return f"{name}({args})"


def _build_local_state(state: dict) -> dict:
    local_state = dict(state)
    local_state["messages"] = list(state.get("messages") or [])
    return local_state


def _tag_trace_message(message: object, agent_name: str) -> object:
    additional_kwargs = dict(getattr(message, "additional_kwargs", {}) or {})
    additional_kwargs["agent"] = agent_name

    if hasattr(message, "model_copy"):
        return message.model_copy(update={"additional_kwargs": additional_kwargs}, deep=True)

    tagged = copy.copy(message)
    try:
        tagged.additional_kwargs = additional_kwargs
    except Exception:
        pass
    return tagged


def _check_cancel(cancel_check: Optional[Callable[[], None]]) -> None:
    if cancel_check is not None:
        cancel_check()


def _emit_trace(trace_callback: Optional[Callable[[dict], None]], payload: dict) -> None:
    if trace_callback is not None:
        trace_callback(payload)


def _emit_trace_messages(
    trace_callback: Optional[Callable[[dict], None]],
    agent_name: str,
    messages: list[object],
) -> None:
    if trace_callback is None:
        return

    for message in messages:
        if isinstance(message, ToolMessage):
            _emit_trace(
                trace_callback,
                {
                    "agent": agent_name,
                    "phase": "tool_result",
                    "title": str(getattr(message, "name", None) or getattr(message, "tool_call_id", None) or "tool"),
                    "content": _message_content_from_message(message),
                },
            )
            continue

        if isinstance(message, AIMessage):
            tool_calls = getattr(message, "tool_calls", []) or []
            if tool_calls:
                _emit_trace(
                    trace_callback,
                    {
                        "agent": agent_name,
                        "phase": "tool_call",
                        "title": agent_name,
                        "content": "\n".join(_tool_call_summary(tool_call) for tool_call in tool_calls),
                    },
                )

            content = _message_content_from_message(message)
            if content:
                _emit_trace(
                    trace_callback,
                    {
                        "agent": agent_name,
                        "phase": "analysis",
                        "title": agent_name,
                        "content": content,
                    },
                )


def _execute_tool_calls(
    tool_node: ToolNode,
    tool_calls: list[dict],
    *,
    agent_name: str = "",
    trace_callback: Optional[Callable[[dict], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None,
) -> dict:
    tools_by_name = getattr(tool_node, "tools_by_name", None) or getattr(tool_node, "_tools_by_name", {})
    tool_messages: list[ToolMessage] = []

    for call in tool_calls:
        _check_cancel(cancel_check)
        tool_name = str(call.get("name") or "")
        tool_call_id = str(call.get("id") or tool_name)
        tool = tools_by_name.get(tool_name)

        if tool is None:
            tool_messages.append(
                ToolMessage(
                    content=f"Error: {tool_name} is not a registered tool for this analyst.",
                    name=tool_name or "tool",
                    tool_call_id=tool_call_id,
                    status="error",
                )
            )
            continue

        try:
            response = tool.invoke(
                {
                    "name": tool_name,
                    "args": call.get("args") or {},
                    "id": tool_call_id,
                    "type": "tool_call",
                }
            )
            if isinstance(response, ToolMessage):
                tool_messages.append(response)
            else:
                tool_messages.append(
                    ToolMessage(
                        content=str(response),
                        name=tool_name,
                        tool_call_id=tool_call_id,
                    )
                )
        except Exception as exc:
            logger.warning("Tool %s failed in parallel analyst pool: %s", tool_name, exc)
            tool_messages.append(
                ToolMessage(
                    content=f"Error: {tool_name} failed: {exc}",
                    name=tool_name,
                    tool_call_id=tool_call_id,
                    status="error",
                )
            )

        if tool_messages:
            _emit_trace_messages(trace_callback, agent_name, [tool_messages[-1]])

    return {"messages": tool_messages}


def create_parallel_analyst_team(
    plan: AnalystExecutionPlan,
    analyst_factories: Dict[str, Callable[[], Callable[[dict], dict]]],
    tool_nodes: Dict[str, ToolNode],
    max_tool_iterations: int = 16,
    trace_callback: Optional[Callable[[dict], None]] = None,
    cancel_check: Optional[Callable[[], None]] = None,
) -> Callable[[dict], dict]:
    specs = list(plan.specs)
    max_workers = min(max(1, plan.concurrency_limit), len(specs))
    analyst_nodes = {spec.key: analyst_factories[spec.key]() for spec in specs}

    def run_analyst(spec: AnalystNodeSpec, state: dict) -> tuple[str, str, list[dict], list[object]]:
        local_state = _build_local_state(state)
        initial_message_count = len(local_state.get("messages") or [])
        analyst_node = analyst_nodes[spec.key]
        tool_node = tool_nodes[spec.key]
        started_at = monotonic()
        logger.info("%s started in parallel analyst pool.", spec.agent_node)

        for iteration in range(1, max_tool_iterations + 1):
            _check_cancel(cancel_check)
            before_count = len(local_state.get("messages") or [])
            _merge_state_update(local_state, analyst_node(local_state))
            new_messages = (local_state.get("messages") or [])[before_count:]
            _emit_trace_messages(trace_callback, spec.agent_node, new_messages)
            _check_cancel(cancel_check)
            tool_calls = _tool_calls(local_state)

            if not tool_calls:
                report = str(local_state.get(spec.report_key) or _message_content(local_state)).strip()
                elapsed = monotonic() - started_at
                logger.info(
                    "%s completed in %.2fs after %s analyst iteration(s).",
                    spec.agent_node,
                    elapsed,
                    iteration,
                )
                trace_messages = [
                    _tag_trace_message(message, spec.agent_node)
                    for message in (local_state.get("messages") or [])[initial_message_count:]
                ]
                return (
                    spec.report_key,
                    report,
                    list(local_state.get("evidence_items") or []),
                    [] if trace_callback else trace_messages,
                )

            logger.info(
                "%s requested %s tool call(s) on analyst iteration %s.",
                spec.agent_node,
                len(tool_calls),
                iteration,
            )
            _merge_state_update(
                local_state,
                _execute_tool_calls(
                    tool_node,
                    tool_calls,
                    agent_name=spec.agent_node,
                    trace_callback=trace_callback,
                    cancel_check=cancel_check,
                ),
            )

        raise RuntimeError(
            f"{spec.agent_node} exceeded {max_tool_iterations} analyst/tool iterations."
        )

    def parallel_analyst_team_node(state: dict) -> dict:
        logger.info(
            "Parallel analyst pool starting with %s worker(s): %s.",
            max_workers,
            ", ".join(spec.agent_node for spec in specs),
        )
        results: dict[str, object] = {}
        trace_messages: list[object] = []
        started_at = monotonic()

        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="analyst")
        futures = {
            executor.submit(run_analyst, spec, state): spec
            for spec in specs
        }
        pending = set(futures)
        try:
            while pending:
                _check_cancel(cancel_check)
                done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                if not done:
                    continue
                for future in done:
                    _check_cancel(cancel_check)
                    spec = futures[future]
                    report_key, report, evidence_items, analyst_trace_messages = future.result()
                    results[report_key] = report
                    if evidence_items:
                        results.setdefault("evidence_items", [])
                        results["evidence_items"].extend(evidence_items)
                    trace_messages.extend(analyst_trace_messages)
                    logger.info("%s joined parallel analyst pool.", spec.agent_node)
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

        logger.info(
            "Parallel analyst pool completed in %.2fs.",
            monotonic() - started_at,
        )
        if trace_messages:
            results["messages"] = trace_messages
        return results

    return parallel_analyst_team_node
