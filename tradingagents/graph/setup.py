# TradingAgents/graph/setup.py

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .analyst_execution import build_analyst_execution_plan
from .conditional_logic import ConditionalLogic
from .parallel_analysts import create_parallel_analyst_team


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
        analyst_max_tool_iterations: int = 16,
        analyst_trace_callback=None,
        cancel_check=None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.analyst_concurrency_limit = analyst_concurrency_limit
        self.analyst_max_tool_iterations = max(1, int(analyst_max_tool_iterations))
        self.analyst_trace_callback = analyst_trace_callback
        self.cancel_check = cancel_check

    def setup_graph(
        self, selected_analysts=["market", "onchain", "social", "news"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "onchain": Onchain analyst
                - "social": Social analyst
                - "news": News analyst
        """
        plan = build_analyst_execution_plan(
            selected_analysts,
            concurrency_limit=self.analyst_concurrency_limit,
        )

        analyst_factories = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm),
            "onchain": lambda: create_onchain_analyst(self.quick_thinking_llm),
            "social": lambda: create_sentiment_analyst(self.quick_thinking_llm),
            "news": lambda: create_news_analyst(self.quick_thinking_llm),
        }

        # Create debate and decision nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)
        verifier_node = create_verifier(self.deep_thinking_llm)
        decision_extractor_node = create_decision_extractor(self.deep_thinking_llm)

        # Create workflow
        workflow = StateGraph(AgentState)

        use_parallel_analysts = plan.concurrency_limit > 1 and len(plan.specs) > 1
        parallel_analyst_node = "Parallel Analyst Team"

        # Add analyst nodes to the graph
        if use_parallel_analysts:
            workflow.add_node(
                parallel_analyst_node,
                create_parallel_analyst_team(
                    plan,
                    analyst_factories,
                    self.tool_nodes,
                    max_tool_iterations=self.analyst_max_tool_iterations,
                    trace_callback=self.analyst_trace_callback,
                    cancel_check=self.cancel_check,
                ),
            )
        else:
            for spec in plan.specs:
                workflow.add_node(spec.agent_node, analyst_factories[spec.key]())
                workflow.add_node(spec.clear_node, create_msg_delete())
                workflow.add_node(spec.tool_node, self.tool_nodes[spec.key])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)
        workflow.add_node("Verifier", verifier_node)
        workflow.add_node("Decision Extractor", decision_extractor_node)

        # Define edges
        if use_parallel_analysts:
            workflow.add_edge(START, parallel_analyst_node)
            workflow.add_edge(parallel_analyst_node, "Bull Researcher")
        else:
            # Start with the first analyst
            workflow.add_edge(START, plan.specs[0].agent_node)

            # Connect analysts in sequence
            for i, spec in enumerate(plan.specs):
                current_analyst = spec.agent_node
                current_tools = spec.tool_node
                current_clear = spec.clear_node

                # Add conditional edges for current analyst
                workflow.add_conditional_edges(
                    current_analyst,
                    getattr(self.conditional_logic, f"should_continue_{spec.key}"),
                    [current_tools, current_clear],
                )
                workflow.add_edge(current_tools, current_analyst)

                # Connect to next analyst or to Bull Researcher if this is the last analyst
                if i < len(plan.specs) - 1:
                    workflow.add_edge(current_clear, plan.specs[i + 1].agent_node)
                else:
                    workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Risk Team": "Aggressive Analyst",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Risk Team": "Aggressive Analyst",
            },
        )
        workflow.add_edge("Aggressive Analyst", "Conservative Analyst")
        workflow.add_edge("Conservative Analyst", "Neutral Analyst")
        workflow.add_edge("Neutral Analyst", "Portfolio Manager")

        workflow.add_edge("Portfolio Manager", "Verifier")
        workflow.add_conditional_edges(
            "Verifier",
            self.conditional_logic.should_continue_portfolio_verification,
            {
                "Portfolio Manager": "Portfolio Manager",
                "Decision Extractor": "Decision Extractor",
                END: END,
            },
        )
        workflow.add_edge("Decision Extractor", END)

        return workflow
