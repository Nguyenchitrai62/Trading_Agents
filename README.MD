# TradingAgents Crypto Dashboard

TradingAgents Crypto Dashboard is a crypto-focused multi-agent market analysis platform. The FastAPI backend reuses the core orchestration under `tradingagents/`, runs the four-branch market/onchain/social/news flow through research debate, risk debate, portfolio decision, verification, and decision extraction, then streams progress to a browser dashboard with Server-Sent Events (SSE).

This repository is no longer a CLI-first demo. The current product focus is a realtime dashboard, backend agent orchestration, and a deployable split frontend/backend architecture.

Live frontend: https://crypto.nguyenchitrai.id.vn

## Highlights

- Crypto-first analysis with BTC/USDT defaults and TradingView chart support.
- Static frontend built with plain HTML, CSS, and JavaScript, suitable for Vercel.
- FastAPI backend suitable for Render or another Python web host.
- Realtime analysis flow through `POST /api/analyze` with SSE streaming.
- MiniMax MCP `web_search` and `understand_image` support for live source cross-checking during agent analysis and chat.
- Admin-only integrated chat inside the main dashboard through `POST /api/chat`, reusing the Google-authenticated backend session flow.
- Live UI updates for agents, teams, reports, trace output, backend logs, and final decisions.
- Configurable run settings: symbol, date, lookback, language, analysts, depth, model, and checkpoint mode.
- Google sign-in with admin-managed run permissions.
- Optional Turso persistence for History and user access control.
- TradingView chart page with a browser-stored watchlist.

## Architecture

```text
Static dashboard
	-> FastAPI backend
	-> tradingagents graph/core
	-> SSE stream back to the UI
	-> optional Turso History/Admin persistence
```

Key files:

- `app.py`: uvicorn entrypoint that imports `BE.server:app`.
- `BE/`: FastAPI backend, auth, analysis streaming, history, and admin APIs.
- `index.html`, `FE/scripts/*.js`, `FE/styles.css`, `FE/styles/*.css`, `FE/config.js`: frontend dashboard shell, runtime modules, and stylesheet partials.
- `tradingagents/`: multi-agent orchestration, agents, graph logic, dataflows, and LLM clients.
- `requirements.txt`: the only dependency installation source.

## Main Analysis Flow

1. The user signs in with Google.
2. The frontend loads public configuration from `FE/config.js` and `/api/config`.
3. The user selects analysis settings and starts a run.
4. The frontend calls `POST /api/analyze` with a JSON body and auth headers.
5. The backend runs `TradingAgentsGraph`: Market collects CCXT/technical data for one LLM analysis, Onchain analyzes each CoinGlass endpoint once and then synthesizes, Social and News use MiniMax web search.
6. The four branch reports feed Bull/Bear research debate, Risk Room debate, Portfolio Manager markdown, Verifier markdown audit, and the Decision Extractor structured payload.
7. The dashboard renders progress, reports, debates, traces, logs, and the final decision in realtime.
8. If Turso is configured, completed analysis sections and structured decision fields are saved to History.

## Local Setup

Create `.env`:

```powershell
Copy-Item .env-example .env
```

Install dependencies:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the backend and bundled static frontend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open the dashboard:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

If `FE/config.js` points to a deployed backend, override it locally with:

```text
http://127.0.0.1:8000/?api_base_url=http://127.0.0.1:8000
```

## Environment

Minimum variables for a working analysis flow:

- `MINIMAX_API_KEY` or `MINIMAX_CN_API_KEY`: required for analysis.
- `GOOGLE_CLIENT_ID`: required for Google sign-in.

Common production variables:

- `CORS_ALLOW_ORIGINS`: required when the frontend and backend are deployed on different origins.
- `ADMIN_EMAILS`: optional seed admins with analysis and user-management permissions.
- `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`: optional, enables History/Admin persistence.
- `MINIMAX_MCP_*`: optional controls for the MiniMax MCP server. MCP is enabled by default for MiniMax; credentials are read from `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY`, and the MCP host is normally derived from `MINIMAX_BASE_URL`.

Trusted web sources for MCP search live in `tradingagents/default_config.py` under `preferred_reference_sources`. When MiniMax MCP web search is enabled, agents are instructed to retrieve or cross-check every configured trusted URL before final market-facing conclusions, then optionally search beyond those sources.

Most other values in `.env-example` are optional defaults or runtime tuning. Leave them unset unless you need to override the default behavior.

Do not commit real secrets in `.env`.

## Deployment

Recommended deployment stack:

- Frontend: [Vercel](https://vercel.com/) static hosting.
- Backend: [Render](https://render.com/) FastAPI service.
- Database: [Turso](https://turso.tech), only when History/Admin persistence is needed.
- LLM: MiniMax. The [MiniMax Token Plan](https://platform.minimax.io/docs/guides/pricing-token-plan) Starter tier starts at `$10/month`, which is enough to run the full analysis flow for this project.

This stack keeps the frontend, backend, and database on practical free tiers for small deployments; only the LLM usage normally needs a paid plan.

Backend start command:

```powershell
uvicorn app:app --host 0.0.0.0 --port $env:PORT
```

Deploy the frontend as static assets:

- `index.html`
- `FE/`
- `image/`

When frontend and backend use different origins:

- Set `FE/config.js` `apiBaseUrl` to the backend origin.
- Set `CORS_ALLOW_ORIGINS` to the real frontend origin for your deployment.
- Keep MiniMax, Google, and Turso secrets only in backend environment variables.

## Notes

- `asset_type` currently supports crypto only.
- History currently requires login; public history mode is not enabled in the backend.
- Standalone `llm.html` is no longer the main chat surface; chat now lives directly in the dashboard.
- Telegram bot, MongoDB, and frontend frameworks are not part of the current implementation.
- This is a research assistant, not financial advice.
