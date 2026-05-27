from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic
from typing import Callable, Dict

from langchain_core.messages import RemoveMessage
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

        state[key] = value


def _tool_call_count(state: dict) -> int:
    messages = state.get("messages") or []
    if not messages:
        return 0
    return len(getattr(messages[-1], "tool_calls", None) or [])


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


def _build_local_state(state: dict) -> dict:
    local_state = dict(state)
    local_state["messages"] = list(state.get("messages") or [])
    return local_state


def create_parallel_analyst_team(
    plan: AnalystExecutionPlan,
    analyst_factories: Dict[str, Callable[[], Callable[[dict], dict]]],
    tool_nodes: Dict[str, ToolNode],
    max_tool_iterations: int = 16,
) -> Callable[[dict], dict]:
    specs = list(plan.specs)
    max_workers = min(max(1, plan.concurrency_limit), len(specs))
    analyst_nodes = {spec.key: analyst_factories[spec.key]() for spec in specs}

    def run_analyst(spec: AnalystNodeSpec, state: dict) -> tuple[str, str]:
        local_state = _build_local_state(state)
        analyst_node = analyst_nodes[spec.key]
        tool_node = tool_nodes[spec.key]
        started_at = monotonic()
        logger.info("%s started in parallel analyst pool.", spec.agent_node)

        for iteration in range(1, max_tool_iterations + 1):
            _merge_state_update(local_state, analyst_node(local_state))
            tool_calls = _tool_call_count(local_state)

            if tool_calls <= 0:
                report = str(local_state.get(spec.report_key) or _message_content(local_state)).strip()
                elapsed = monotonic() - started_at
                logger.info(
                    "%s completed in %.2fs after %s analyst iteration(s).",
                    spec.agent_node,
                    elapsed,
                    iteration,
                )
                return spec.report_key, report

            logger.info(
                "%s requested %s tool call(s) on analyst iteration %s.",
                spec.agent_node,
                tool_calls,
                iteration,
            )
            _merge_state_update(local_state, tool_node.invoke(local_state))

        raise RuntimeError(
            f"{spec.agent_node} exceeded {max_tool_iterations} analyst/tool iterations."
        )

    def parallel_analyst_team_node(state: dict) -> dict:
        logger.info(
            "Parallel analyst pool starting with %s worker(s): %s.",
            max_workers,
            ", ".join(spec.agent_node for spec in specs),
        )
        results: dict[str, str] = {}
        started_at = monotonic()

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="analyst") as executor:
            futures = {
                executor.submit(run_analyst, spec, state): spec
                for spec in specs
            }
            for future in as_completed(futures):
                report_key, report = future.result()
                results[report_key] = report

        logger.info(
            "Parallel analyst pool completed in %.2fs.",
            monotonic() - started_at,
        )
        return results

    return parallel_analyst_team_node
