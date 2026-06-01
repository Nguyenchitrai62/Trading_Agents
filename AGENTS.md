# TradingAgents Workspace Context

## Product Goal

Xay dung he thong multi-agent phan tich thi truong co the dung thuc te:

- FE tach rieng, deploy static tren Vercel.
- BE tach rieng, deploy FastAPI tren Render.
- DB chi dung khi can persistence that su. Repo hien co Turso history store tuy chon cho lich su phan tich, auth/access, va markdown sections.
- Telegram bot, neu them, phai la client/adaptor goi lai backend/service layer hien co, khong nhan ban logic agent.

Muc tieu khong phai giu nguyen CLI cu. Muc tieu la giu va phat trien backend agent orchestration trong `tradingagents/`, stream tien trinh theo thoi gian thuc len FE, va tao artifact co cau truc du de cac client khac co the su dung.

## Architecture Target

- FE dung HTML, CSS, JavaScript thuan. Khong tu y them React, Vue, Next.js hoac framework FE khac khi chua co yeu cau ro rang.
- BE dung FastAPI.
- Luong phan tich chinh la Server-Sent Events (SSE).
- FE phai cho phep chon cau hinh roi chay phan tich; trong khi BE xu ly, FE cap nhat lien tuc cac panel agent/team/report.
- Backend phai tai su dung core trong `tradingagents/`; khong xay pipeline agent song song moi neu khong that su can.

## Current Implementation

- `app.py` chi la wrapper khoi dong uvicorn va export `BE.server:app`.
- Backend routes nam trong `BE/server.py`.
- Orchestration/SSE runtime chinh nam trong `BE/analysis.py`.
- Frontend hien tai la `index.html`, `FE/scripts/*.js`, `FE/styles.css`, `FE/styles/*.css`.
- FE hien la dashboard nhieu window theo tinh than TradingAgents CLI:
  - Execution Board
  - Report Windows
  - Research Chamber
  - Risk Room
  - Final Decision
  - History, Chart, Admin, Chat pages
- Popup config hien ho tro:
  - symbol
  - analysis date
  - lookback window
  - output language
  - analyst selection
  - research depth
  - model
  - checkpoint toggle
- `/api/analyze` la endpoint phan tich streaming chinh.
- `/api/analyze` stream cac event nhu `analysis_meta`, `analysis_log`, `agent_trace`, `evidence_update`, `status_snapshot`, `section_update`, `debate_update`, `warning`, `complete`, `cancelled`, `error`.
- FE map cac event nay vao cac panel UI tuong ung.
- `/api/chat` van ton tai nhu backend chat page, nhung khong phai luong phan tich chinh va khong duoc xem la core agent orchestration.

## Current Analysis Flow

1. `BE.models.AnalysisRequest` normalize symbol, date, lookback, selected analysts, depth, model, checkpoint.
2. `BE.analysis.AnalysisService.run_trading_analysis()` resolve MiniMax config, reserve runtime slot, emit metadata/status ban dau.
3. Backend build graph config tu `tradingagents.agent_config.DEFAULT_CONFIG`, override model, language, analysis date, lookback, research debate rounds, and MiniMax MCP tool budget. Risk Room luon la 3 scenario memos co dinh.
4. Backend prefetch CoinGlass snapshot neu configured. Hien tai prefetch toan bo high-value endpoints roi chia thanh package context cho cac role.
5. `TradingAgentsGraph` tao quick/deep LLM clients, tool nodes, graph setup.
6. Analyst phase chay 4 branch canonical, mac dinh co the chay song song theo `analyst_concurrency_limit`:
  - Market Analyst: lay CCXT OHLCV + chi bao ky thuat bang code, sau do goi LLM 1 lan de phan tich.
  - Onchain Analyst: dung cac endpoint CoinGlass da prefetch; moi endpoint thanh cong duoc LLM phan tich 1 lan, sau do goi LLM 1 lan nua de tong hop.
  - Social Analyst: dung MiniMax MCP `web_search` lam live retrieval path.
  - News Analyst: dung MiniMax MCP `web_search` lam live retrieval path.
7. Bon report Market/Onchain/Social/News vao Bull/Bear research debate trong `max_debate_rounds`.
8. Research debate di thang vao Risk Room: Aggressive/Conservative/Neutral moi role tao 1 risk scenario memo duy nhat, khong lap debate theo depth.
9. Portfolio Manager tao markdown `final_trade_decision` voi signal dau tien la mot trong Market Buy, Limit Buy, Hold, Limit Sell, Market Sell.
10. Verifier kiem tra markdown theo deterministic order logic va semantic support, tao `verification_report` va `verification_report_structured`; neu can sua thi route lai Portfolio Manager.
11. Decision Extractor chi chay sau khi verifier chap nhan/canh bao hop le, trich `final_trade_decision_structured` de luu DB.
12. Turso history store luu `analysis_runs.signal`, markdown sections, verification, va structured decision neu DB configured.

## Accuracy And Cost Notes

- FE config hien dang mac dinh `lookbackDays: 30`, `researchDepth: deep`, va all analysts. Day la cau hinh ton LLM/API. Backend default la lookback 7 va depth medium, nhung FE default se override khi nguoi dung chay tu UI.
- Depth tac dong truc tiep den so LLM calls o research debate va MCP/live retrieval budget:
  - quick = 1 research round, risk scenarios van co dinh 3 role x 1 luot.
  - medium = 3 research rounds, risk scenarios van co dinh 3 role x 1 luot.
  - deep = 5 research rounds, risk scenarios van co dinh 3 role x 1 luot.
- Research debate moi round gom Bull/Bear. Risk Room khong con debate loop; Aggressive/Conservative/Neutral chi tao 3 scenario memos mot lan roi Portfolio Manager quyet dinh. Deep them call chu yeu o research va retrieval, nen khong nen xem la default toi uu do chinh xac.
- `mcp_max_tool_rounds` trong runtime profile chua phai hard cap chat cho analyst tool calls. Analyst loop hien duoc dat thanh `max(24, mcp_rounds * 6)`, nen cac prompt bat buoc `web_search` va cross-check trusted sources co the ton nhieu request hon mong doi.
- Nen uu tien medium/quick cho default product flow, va chi dung deep khi co ly do ro rang hoac nguoi dung chu dong chon.
- Nen tranh de moi analyst deu bi prompt "cross-check each trusted source" mot cach rieng le. Neu can tiet kiem request, nen co mot role so huu live web/source validation va chia lai structured evidence cho cac role sau.

## Data Extraction And Noise Notes

- Crypto OHLCV/indicator tools trong `tradingagents/dataflows/ccxt_crypto.py` fetch full active lookback theo timeframe agent yeu cau, co paginate khi can.
- Model khong nhin toan bo raw candles. Tool chi tra summary, window metadata, va bang recent rows compact:
  - OHLCV hien thi recent 18 candles.
  - Indicators hien thi recent 12 rows moi indicator.
- Neu nguoi dung chon lookback qua dai tren timeframe thap, vi du 180 ngay voi 1h, backend van co the fetch hang nghin candles de tinh summary/indicator. Model input khong qua lon, nhung latency/API/noise tang va summary co the pha tron nhieu regime thi truong.
- CoinGlass prefetch dung default limit 42 voi interval 4h cho cac endpoint history, xap xi 7 ngay du lieu. Payload duoc summarize/compact truoc khi dua vao prompt; package context vao agent bi gioi han boi `coinglass_prompt_char_limit` mac dinh 4800 ky tu.
- MiniMax MCP tool result mac dinh khong bi cat (`MINIMAX_MCP_TOOL_RESULT_CHAR_LIMIT=0`). Neu env nay duoc set > 0 thi tool result se bi truncate truoc khi tra ve model.
- `ANALYSIS_TRACE_CHAR_LIMIT` chi anh huong noi dung trace gui len FE, khong phai nhat thiet la prompt noi bo cua model.
- Structured evidence block moi analyst toi da 8 item; downstream evidence ledger chi dua mot so item gioi han vao prompt. Day la co chu dich de giam noise.
- `get_global_news_yfinance()` hien co future-date guard nhung lower-bound start date khong duoc enforce chat nhu Alpha Vantage. Neu can phan tich historical nghiem tuc, can fix loc date cho global news.
- Verifier hien fetch current Binance spot price tai thoi diem verify. Neu `analysis_date` la ngay qua khu, deterministic price checks co the so sanh voi gia hien tai thay vi gia tai ngay phan tich. Backtest/historical runs can sua de dung last OHLCV candle tai analysis cutoff.

## Structured Decision And DB Guidance

- Structured outputs da ton tai trong runtime state:
  - `final_trade_decision_structured`
  - `verification_report_structured`
- `final_trade_decision_structured` da co cac field can cho lenh:
  - `signal`
  - `execution_summary`
  - `market_context`
  - `investment_thesis`
  - `primary_limit_price`
  - `secondary_limit_price`
  - `stop_loss`
  - `take_profit`
  - `position_sizing`
  - `time_horizon`
- Hien DB chi luu `analysis_runs.signal` va markdown sections. Chua co bang/cot structured order plan de query truc tiep entry/SL/TP.
- Neu muc tieu la vao lenh ma khong doc markdown, buoc dung huong tiep theo la them persistence co cau truc, vi du bang `analysis_decisions` hoac JSON column, ghi truc tiep tu `final_trade_decision_structured` va `verification_report_structured`.
- Khong nen parse markdown de ghi DB. Nen ghi tu structured payload trong `final_state`.
- Schema toi thieu nen query duoc:
  - `run_id`
  - `symbol`
  - `analysis_date`
  - `signal`
  - `primary_limit_price`
  - `secondary_limit_price`
  - `stop_loss`
  - `take_profit`
  - `position_sizing`
  - `time_horizon`
  - `verification_verdict`
  - `verification_action`
  - `created_at`
- Neu sau nay cho phep nhieu entry, dung child table `analysis_order_legs` thay vi nhan them cot `entry_1`, `entry_2` qua nhieu noi.
- FE/history co the van luu markdown sections de doc chi tiet, nhung UI trading summary nen lay tu structured decision table/payload.

## Historical Decisions And Memory

- `/api/analyze` hien khong dua cac phan quyet cu trong DB vao prompt phan tich.
- Backend streaming run dang set:
  - `memory_log_path = None`
  - `persist_analysis_artifacts = False`
  - `past_context = ""`
- `TradingAgentsGraph.propagate()` legacy/CLI path van co `TradingMemoryLog`, co the luu pending decisions va inject past context, nhung `/api/analyze` khong dung path nay.
- Nen giu history injection tat mac dinh. Khong phai phan quyet nao agent dua ra nguoi dung cung vao lenh kip, nen dua moi phan quyet cu vao prompt de "hoc" co the lam roi va tao bias sai.
- Neu sau nay muon dung lich su, chi nen dua vao cac outcome da duoc xac nhan:
  - lenh that su da execute
  - entry/exit/fill time ro rang
  - PnL hoac outcome sau mot holding window
  - market regime tuong ung
  - nguon du lieu khong leak tuong lai

## Environment And Configuration

- Dung `.env` cho runtime configuration.
- Base URL FE va default analysis cua FE nam trong `FE/config.js`.
- `MINIMAX_API_KEY` hoac `MINIMAX_CN_API_KEY` phai nam trong `.env` de backend goi LLM.
- `MINIMAX_BASE_URL` tro toi anthropic-compatible MiniMax endpoint.
- `CORS_ALLOW_ORIGINS` phai cau hinh theo domain FE that khi deploy.
- CoinGlass dung `COINGLASS_API_KEY` hoac cac alias duoc ho tro trong `BE/config.py`.
- Turso history dung `TURSO_DATABASE_URL` va `TURSO_AUTH_TOKEN`.

## Dependency Policy

- Chi dung `requirements.txt` cho cai dependency.
- Khong tu y khoi phuc `pyproject.toml` hoac chuyen repo ve flow package build cu neu nguoi dung chua yeu cau.
- `requirements.txt` dang duoc giu rong de tranh thieu thu vien khi mo rong backend.

## Deployment Intent

- FE: static hosting tren Vercel.
- BE: FastAPI tren Render.
- DB: Turso history store la optional persistence hien tai. Chi mo rong schema khi co nhu cau persistence ro rang.
- Telegram bot: client/adaptor goi backend hien co, khong chen logic agent truc tiep vao bot.

## Working Priorities For Future Changes

1. Uu tien on dinh luong FE -> BE -> SSE -> UI.
2. Moi thay doi UI phai giu kha nang hien thi tien trinh agent theo thoi gian thuc.
3. Toi uu request/model budget truoc khi tang depth hoac them agent moi.
4. Neu them structured DB decision, ghi tu structured payload trong final state, khong parse markdown.
5. Khi them DB schema moi, tach persistence/service ro rang de khong pha SSE flow.
6. Khi them Telegram bot, tai su dung request models, config models va orchestration hien co.
7. Khi mo rong backend, uu tien `BE/analysis.py`, `BE/server.py`, `BE/history.py` va `tradingagents/` thay vi them entrypoint roi rac.

## Non-Goals

- Khong khoi phuc toan bo repo cu chi de giu tai lieu, CLI hoac artifact khong phuc vu muc tieu FE/BE hien tai.
- Khong bien FE hien tai thanh framework app lon neu chua co yeu cau cu the.
- Khong them DB chi vi co the can; chi them khi co nhu cau persistence ro rang.
- Khong dua phan quyet cu vao prompt phan tich neu chua co du lieu execution/outcome that su.

## Key Files

- `app.py`: wrapper export `BE.server:app` va khoi dong uvicorn khi chay truc tiep.
- `BE/server.py`: FastAPI app, routes, CORS, static mount, auth/history/admin/chat/analyze endpoints.
- `BE/analysis.py`: config bootstrap cho run, SSE streaming, CoinGlass prefetch, graph execution, event emission, history save.
- `BE/models.py`: request/response Pydantic models cho analysis, chat, auth, admin.
- `BE/history.py`: Turso schema, history save/list/detail, markdown sections.
- `BE/config.py`: backend settings tu `.env`, MiniMax, CoinGlass, Turso, CORS, runtime limits.
- `index.html`: dashboard shell va page/modal structure.
- `FE/config.js`: FE backend base URL, default analysis config, options.
- `FE/scripts/01-core-chat.js`: constants, markdown/chat helpers, state factory helpers.
- `FE/scripts/02-config-auth-trace.js`: config bootstrap, auth/session helpers, trace merge logic.
- `FE/scripts/03-dashboard-history.js`: dashboard rendering, operations/detail modal helpers, page shell rendering.
- `FE/scripts/03b-history-archive.js`: history archive rendering, pagination, detail loading, section markdown flow.
- `FE/scripts/04-chart-admin.js`: chart workspace, admin page, page switching.
- `FE/scripts/05-runtime-bootstrap.js`: state/elements bootstrap, SSE consumption, DOM listeners.
- `FE/styles.css` va `FE/styles/*.css`: stylesheet manifest va cac partial theo domain.
- `tradingagents/agent_config.py`: default graph/runtime config, depth/tool/source/data defaults.
- `tradingagents/graph/trading_graph.py`: core `TradingAgentsGraph`, LLM clients, tool nodes, graph compile.
- `tradingagents/graph/setup.py`: LangGraph node/edge flow.
- `tradingagents/graph/parallel_analysts.py`: analyst parallel execution and tool loop.
- `tradingagents/graph/analyst_execution.py`: analyst node/report mapping.
- `tradingagents/dataflows/ccxt_crypto.py`: crypto OHLCV/indicator fetching and compact output.
- `tradingagents/dataflows/coinglass_client.py`: CoinGlass endpoint prefetch, summaries, evidence items.
- `tradingagents/agents/schemas.py`: structured output schemas for debate turns, portfolio decision extraction, and verifier.
- `tradingagents/agents/managers/portfolio_manager.py`: markdown-first portfolio decision.
- `tradingagents/agents/managers/verifier.py`: deterministic and evidence verification.
- `requirements.txt`: dependency source of truth.

## Definition Of Done For Core Product Work

Mot thay doi di dung huong khi thoa cac dieu sau:

- FE co the cau hinh phien phan tich va gui request xuong backend.
- Backend stream tien trinh phan tich lien tuc thay vi chi tra ket qua cuoi.
- FE cap nhat dung panel theo tung buoc agent/team/report.
- Runtime config giu API key trong `.env`; FE base URL va default analysis nam trong `FE/config.js`.
- Neu co DB output moi, signal/entry/SL/TP/verification phai query duoc truc tiep ma khong can doc markdown.
- Thay doi van phu hop deploy FE tren Vercel va BE tren Render.

## Guidance For Coding Agents

- Luon xem repo nay la multi-agent market analysis platform, khong phai demo chat voi LLM.
- Khi danh gia do chinh xac, phai xem ca data window, freshness, tool budget, structured evidence, verifier, va persistence.
- Neu phai chon giua them tinh nang ngan han va giu dung kien truc FE/BE streaming dai han, uu tien kien truc dai han.
- Neu can them tich hop moi, noi vao backend/service layer hien tai de FE, Telegram, va tac vu sau nay dung chung mot luong phan tich.
- Khong tang depth, analyst count, hoac web-search requirement neu chua do duoc gia tri tang them so voi request/API cost.
