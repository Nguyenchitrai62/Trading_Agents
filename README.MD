# TradingAgents Crypto Dashboard

TradingAgents Crypto Dashboard is a crypto-focused multi-agent market analysis platform. The FastAPI backend reuses the core orchestration under `tradingagents/`, runs the four-branch market/onchain/social/news flow through research debate, risk debate, portfolio decision, verification, and decision extraction, then streams progress to a browser dashboard via Server-Sent Events (SSE).

Live frontend: https://crypto.nguyenchitrai.id.vn

## Highlights

- Crypto-first analysis with BTC/USDT defaults and TradingView chart support.
- Static frontend built with plain HTML, CSS, and JavaScript, suitable for Vercel.
- FastAPI backend suitable for Render or another Python web host.
- Realtime analysis flow through `POST /api/analyze` with SSE streaming.
- Multi-model support: MiniMax (with MCP web search) or DeepSeek (with webfetch tool).
- Admin-only integrated chat inside the dashboard through `POST /api/chat`.
- Live UI updates for agents, teams, reports, trace output, backend logs, and final decisions.
- Configurable run settings: symbol, date, lookback, language, analysts, depth, model, and checkpoint.
- Google sign-in with admin-managed run permissions.
- Optional Turso persistence for History and user access control.
- TradingView chart page with a browser-stored watchlist.

## Architecture

```
Static dashboard
  -> FastAPI backend
  -> tradingagents graph/core
  -> SSE stream back to the UI
  -> optional Turso History/Admin persistence
```

Key files:

| Path | Purpose |
|------|---------|
| `app.py` | Uvicorn entrypoint, imports `BE.server:app` |
| `BE/server.py` | FastAPI app, all routes, CORS, static mount |
| `BE/analysis/` | AnalysisService split by feature (orchestrator, chat, prefetch, emitter, formatting, graph utils) |
| `BE/history/` | TursoHistoryStore + section builders |
| `BE/config.py` | Backend settings from `.env` |
| `BE/auth.py` | Google sign-in + admin auth |
| `BE/models.py` | Pydantic request/response models |
| `index.html` | Dashboard shell + page/modal structure |
| `FE/config.js` | Frontend base URL + defaults |
| `FE/scripts/core.js` | Constants, markdown/chat helpers, state factories |
| `FE/scripts/config.js` | Config bootstrap, auth/session |
| `FE/scripts/trace.js` | Trace merge, scroll, SSE parsing |
| `FE/scripts/dashboard.js` | Dashboard panels, live flow diagram |
| `FE/scripts/history.js` | History archive, pagination, detail |
| `FE/scripts/reports.js` | Operations rail, reports, detail modals |
| `FE/scripts/chart.js` | Chart workspace, admin page |
| `FE/scripts/bootstrap.js` | State bootstrap, SSE consumer, DOM events |
| `FE/styles/` | 8 CSS partials named by feature (foundation, theme, auth, execution, history, chat, chart, live-flow) |
| `tradingagents/agents/analysts/` | Market, news, social, onchain analyst factories |
| `tradingagents/agents/researchers/` | Bull/bear researcher factories |
| `tradingagents/agents/risk_mgmt/` | Aggressive/conservative/neutral risk debators |
| `tradingagents/agents/managers/` | Portfolio manager, verifier, decision extractor |
| `tradingagents/graph/` | LangGraph orchestration + builder |
| `tradingagents/dataflows/` | CCXT, CoinGlass, endpoint summaries |
| `tradingagents/llm_clients/` | LLM provider clients (MiniMax MCP, Anthropic, OpenAI, DeepSeek, Google) |
| `requirements.txt` | Single dependency source |

## Main Analysis Flow

1. User signs in with Google.
2. Frontend loads public configuration from `FE/config.js` and `/api/config`.
3. User selects analysis settings and starts a run.
4. Frontend calls `POST /api/analyze` with auth headers.
5. Backend runs `TradingAgentsGraph`:
   - **Market Analyst**: CCXT OHLCV + technical indicators, one LLM analysis.
   - **Onchain Analyst**: CoinGlass endpoint analysis, then synthesis.
   - **Social Analyst**: Live web search (MCP web_search or webfetch).
   - **News Analyst**: Live web search (MCP web_search or webfetch).
6. Four branch reports feed Bull/Bear research debate.
7. Research debate flows into Risk Room (Aggressive/Conservative/Neutral debate).
8. Portfolio Manager produces markdown decision.
9. Verifier audits the decision; can route back for revision.
10. Decision Extractor produces structured payload.
11. Dashboard renders progress, reports, debates, traces, final decision in realtime.
12. If Turso configured, analysis sections + structured decision saved to History.

## Local Setup

### 1. Create `.env`

Copy the example file and fill in your keys:

```powershell
Copy-Item .env-example .env
```

**Minimum required:**
- `MINIMAX_API_KEY` or `DEEPSEEK_API_KEY` (LLM — pick one)
- `GOOGLE_CLIENT_ID` (frontend auth)

### 2. Install dependencies

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

### 4. Open

```
http://127.0.0.1:8000
```

Health check: `http://127.0.0.1:8000/health`

If `FE/config.js` points to a deployed backend, override it locally:

```
http://127.0.0.1:8000/?api_base_url=http://127.0.0.1:8000
```

## Environment

### Required (pick one LLM provider)

| Variable | Description |
|----------|-------------|
| `MINIMAX_API_KEY` | MiniMax API key — MCP web_search for live retrieval |
| `DEEPSEEK_API_KEY` | DeepSeek V4 Flash via OpenCode — webfetch tool, lighter option |

> **Recommendation:** DeepSeek V4 Flash through [OpenCode Go](https://opencode.ai/go) at $5/month is the simpler and more cost-effective choice. You only need `DEEPSEEK_API_KEY` and the `deepseek-v4-flash` model to run the full analysis pipeline. [MiniMax](https://platform.minimax.io/subscribe/token-plan) at $10/month is suitable when you need more cross-source web_search capability at the $10/month Starter tier.

### Required (frontend auth)

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID for sign-in |

### Optional (history persistence)

| Variable | Description |
|----------|-------------|
| `TURSO_DATABASE_URL` | Turso/LibSQL database URL |
| `TURSO_AUTH_TOKEN` | Turso auth token |

### Optional (on-chain data)

| Variable | Description |
|----------|-------------|
| `COINGLASS_API_KEY` | CoinGlass API key for onchain analysis |

### Optional (deployment)

| Variable | Description |
|----------|-------------|
| `CORS_ALLOW_ORIGINS` | Comma-separated CORS origins (required for cross-origin deploy) |
| `FRONTEND_ORIGIN` | Frontend origin added to CORS allow list |

### Optional (tuning)

| Variable | Description |
|----------|-------------|
| `ADMIN_EMAILS` | Comma-separated admin emails |
| `PORT` | Server port (default: `8000`) |
| `LOG_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

See `.env-example` for the full list with descriptions.

## Deployment

Recommended stack:

| Layer | Platform | Notes |
|-------|----------|-------|
| Frontend | [Vercel](https://vercel.com/) | Static hosting |
| Backend | [Render](https://render.com/) | FastAPI service |
| Database | [Turso](https://turso.tech) | Optional, for History/Admin |
| LLM | [MiniMax](https://platform.minimax.io/subscribe/token-plan) or [DeepSeek](https://opencode.ai/go) | Opencode Starter tier: $5/month minimum |

Backend start command on Render:

```powershell
uvicorn app:app --host 0.0.0.0 --port $env:PORT
```

Deploy the frontend as static assets: `index.html`, `FE/`, `image/`.

Cross-origin deploy checklist:
- Set `CORS_ALLOW_ORIGINS` to the real frontend origin.
- Set `FE/config.js` `apiBaseUrl` to the backend origin.
- Keep all secrets (API keys, tokens) only in backend environment variables.

## Switching Between MiniMax and DeepSeek

Both models can run the full analysis pipeline. The main difference is in the web retrieval tool:

| Model | Web Search | Endpoint | Setup |
|-------|-----------|----------|-------|
| **DeepSeek V4 Flash** (recommended) | `webfetch` via urllib | `https://opencode.ai/zen/go/v1` | `DEEPSEEK_API_KEY` in `.env` |
| MiniMax M2.5 | MCP `web_search` | `https://api.minimax.io/anthropic` | `MINIMAX_API_KEY` in `.env` |

**DeepSeek V4 Flash via OpenCode** is the recommended default: simple, lightweight, no MCP server setup required. The model is selected in the UI config as `deepseek-v4-flash`.

**MiniMax M2.5** is stronger at web search (structured results, cross-referencing multiple sources), but requires an MCP server (`minimax-coding-plan-mcp`) and a separate API key. Suitable when you need the highest accuracy from live web sources.

## Notes

- `asset_type` currently supports crypto only.
- This is a research assistant, not financial advice.
- Telegram bot, MongoDB, and frontend frameworks are not part of the current implementation.
- The Admin Chat page is planned to evolve into an Agent RAG system, enabling natural-language queries against historical analysis decisions and section data persisted in the database.
- This project is based on the original idea from [Tauric Research / tradingagents](https://github.com/tauricresearch/tradingagents).
