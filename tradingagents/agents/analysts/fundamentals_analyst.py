from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
    get_preferred_reference_sources_instruction,
)
from tradingagents.dataflows.config import get_config
from tradingagents.llm_clients.minimax_mcp import MiniMaxMCPChatModel


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "crypto")
        instrument_context = build_instrument_context(state["company_of_interest"], asset_type)
        require_companion_web_search = asset_type == "crypto" and isinstance(llm, MiniMaxMCPChatModel)

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        if require_companion_web_search:
            system_message = (
                "You are a researcher tasked with analyzing crypto fundamentals over the past week. Use the internal fundamental tools when they provide usable structured data, but do not rely on equity-style financial statement assumptions for crypto assets. Always call the exact MiniMax MCP tool `web_search` at least once in the same analysis for tokenomics, protocol upgrades, ecosystem traction, treasury or issuer developments, institutional and ETF flow commentary, staking or validator dynamics, supply unlocks, governance decisions, and other project-specific fundamental drivers. If an internal tool returns an error, rate-limit notice, or unavailable placeholder, briefly note that limitation and continue with `web_search` plus any successful tool outputs instead of stopping. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
                + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                + get_preferred_reference_sources_instruction()
                + get_language_instruction()
            )
        else:
            system_message = (
                "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
                + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
                + get_preferred_reference_sources_instruction()
                + get_language_instruction()
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " Core analysis tools include: {tool_names}. Additional MiniMax MCP tools may be available through the model runtime.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(
            tool_names=", ".join([tool.name for tool in tools])
            + (", web_search" if require_companion_web_search else "")
        )
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
