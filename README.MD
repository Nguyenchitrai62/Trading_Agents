# TradingAgents Crypto Dashboard

TradingAgents Crypto Dashboard is a crypto-first market analysis platform built around a multi-agent research workflow. The backend orchestrates analysts, researchers, trader, risk team, and portfolio manager agents, then streams progress to a browser dashboard through Server-Sent Events.

This project is inspired by and originally derived from [tauricresearch/tradingagents](https://github.com/tauricresearch/tradingagents). I used the original repository as a source of ideas and agent-orchestration direction, then changed many parts of the product shape, runtime, frontend, persistence, authentication, and deployment model for this repo.

## What Changed From The Original Idea

- The product direction is no longer a CLI-first research demo. It is now a FastAPI backend plus a standalone HTML/CSS/JavaScript frontend.
- The primary flow is realtime streaming analysis over SSE from `/api/analyze` into dashboard panels.
- The app is crypto-first, with BTC-style defaults, Binance/ccxt market data paths, StockTwits/Reddit/news context, and TradingView chart shortcuts.
- Google sign-in gates analysis execution, while public history can remain readable when enabled.
- Turso is used for optional persistent analysis history.
- The frontend has been rebuilt as a dashboard with Execution Board, Backend Log, Main View, Agent Trace, Event Log, History, and Chart pages.

## Architecture

- `app.py`: FastAPI app, static frontend serving, auth, history APIs, SSE analysis endpoint, MiniMax-compatible LLM integration.
- `index.html`: dashboard shell and Google Identity Services bootstrap.
- `FE/app.js`: frontend state, config modal, auth handling, SSE parsing, history and chart UI.
- `FE/config.js`: public frontend defaults and remote backend base URL.
- `FE/styles.css`: dashboard layout and interaction styling.
- `tradingagents/`: retained and heavily adapted multi-agent orchestration, analysts, dataflows, graph setup, LLM clients, and runtime config.
- `requirements.txt`: single dependency source for local and deployment installs.

## Main Features

- Realtime market analysis streaming with SSE.
- Configurable symbol, analysis date, lookback window, output language, analysts, model, research depth, and checkpoint toggle.
- Analyst reports for market, sentiment, news, and fundamentals.
- Research debate, trader plan, risk debate, and final portfolio decision panels.
- Google-authenticated analysis execution.
- Optional Turso-backed analysis history.
- TradingView chart page with favorite crypto symbols and intervals.
- Pure frontend stack, suitable for static hosting on Vercel.

## Environment

Create a local `.env` from the example file and replace placeholders with real values:

```powershell
Copy-Item .env-example .env
```

Important variables:

- `MINIMAX_API_KEY` or `MINIMAX_CN_API_KEY`: required for LLM calls.
- `MINIMAX_BASE_URL`: optional Anthropic-compatible MiniMax endpoint override.
- `GOOGLE_CLIENT_ID`: required for Google sign-in.
- `GOOGLE_ALLOWED_EMAIL` or `GOOGLE_ALLOWED_EMAILS`: controls which accounts can run analysis.
- `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`: enable persistent history.
- `HISTORY_PUBLIC_READ`: allows unauthenticated users to view public history summaries/details when `true`.
- `CORS_ALLOW_ORIGINS`: set this to the real frontend domains in production.

Do not commit real `.env` secrets. The tracked `.env-example` is intentionally placeholder-only.

## Local Development

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

Open:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

## API Surface

- `GET /`: serves the dashboard.
- `GET /health`: backend health and runtime limits.
- `GET /api/config`: public frontend runtime config.
- `GET /api/auth/me`: verifies the current Google ID token.
- `GET /api/history`: lists saved analysis runs, public or authenticated depending on config.
- `GET /api/history/{run_id}`: loads saved report sections.
- `POST /api/analyze`: starts SSE analysis stream. Requires an authorized Google ID token.
- `POST /api/analyze/{run_id}/cancel`: cancels an active analysis stream. Requires auth.

## Deployment Notes

- Backend target: Render or another Python web host running FastAPI with `uvicorn app:app`.
- Frontend target: Vercel or another static host using `index.html` and `FE/` assets.
- Set `FE/config.js` `apiBaseUrl` to the deployed backend origin when serving frontend and backend separately.
- Configure `CORS_ALLOW_ORIGINS` with the deployed frontend origin.
- Keep MiniMax, Google, and Turso secrets only in backend environment variables.

## Notes

This is an analysis assistant, not financial advice. Reports can be incomplete or wrong when upstream market, social, news, or LLM providers are unavailable or rate-limited. Use the output as research support and verify important claims independently.