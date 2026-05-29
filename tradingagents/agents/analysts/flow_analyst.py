from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_coinglass_context_instruction,
    get_fundamentals,
    get_income_statement,
    get_global_news,
    get_language_instruction,
    get_news,
    get_preferred_reference_sources_instruction,
)
from tradingagents.agents.utils.evidence import (
    get_structured_evidence_instruction,
    split_report_and_evidence,
)
from tradingagents.llm_clients.minimax_mcp import MiniMaxMCPChatModel, has_minimax_mcp_tool


def create_flow_analyst(llm):
    def flow_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "crypto")
        instrument_context = build_instrument_context(state["company_of_interest"], asset_type)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=(
                "exchange_reserves",
                "institutional_flow",
                "funding_pressure",
                "liquidation_risk",
                "macro_cycle_context",
            ),
        )
        require_companion_web_search = (
            asset_type == "crypto"
            and isinstance(llm, MiniMaxMCPChatModel)
            and has_minimax_mcp_tool(llm.settings, "web_search")
        )

        if asset_type == "crypto":
            tools = [
                get_news,
                get_global_news,
            ]

            if require_companion_web_search:
                system_message = (
                    "You are a crypto flow analyst focused on on-chain, derivatives, and liquidity context over the past week."
                    " Always call the exact MiniMax MCP tool `web_search` at least once in the same analysis."
                    " Use it to check live evidence around open interest, funding, liquidations, basis, ETF flows, exchange reserves, stablecoin liquidity, TVL, unlock schedules, staking or validator dynamics, treasury changes, and major ecosystem flow shifts."
                    " Use `get_news` and `get_global_news` as supporting structured inputs for macro, regulatory, exchange, and ETF developments."
                    " If one source is unavailable, briefly note the gap and continue with the remaining evidence instead of inventing facts."
                    " Explain what the current flow regime implies for positioning, conviction, and risk."
                    " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                    + coinglass_context
                    + get_preferred_reference_sources_instruction()
                    + get_language_instruction()
                    + get_structured_evidence_instruction("flow")
                )
            else:
                system_message = (
                    "You are a crypto flow analyst focused on on-chain, derivatives, and liquidity context over the past week."
                    " Use `get_news` and `get_global_news` to cover ETF flows, regulatory developments, exchange issues, stablecoin and liquidity themes, and macro conditions affecting crypto."
                    " Be explicit about what is known versus what remains uncertain when direct live browsing is unavailable."
                    " Explain what the current flow regime implies for positioning, conviction, and risk."
                    " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                    + coinglass_context
                    + get_preferred_reference_sources_instruction()
                    + get_language_instruction()
                    + get_structured_evidence_instruction("flow")
                )
        else:
            tools = [
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
            ]
            system_message = (
                "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
                + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
                + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
                + get_preferred_reference_sources_instruction()
                + get_language_instruction()
                + get_structured_evidence_instruction("flow")
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Build on earlier agent outputs when they already contain usable evidence or a completed section,"
                    " but do not restate obsolete buy/sell stop markers from older flows."
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

        evidence_items = []
        if len(result.tool_calls) == 0:
            report, evidence_items = split_report_and_evidence(
                result.content,
                agent_key="flow",
                agent_label="Flow Analyst",
                report_section="flow_report",
                analysis_date=current_date,
            )

        return {
            "messages": [result],
            "flow_report": report,
            "evidence_items": evidence_items,
        }

    return flow_analyst_node
