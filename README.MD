# TradingAgents Crypto Dashboard

TradingAgents is a crypto-focused multi-agent analysis dashboard.

- Frontend: plain HTML/CSS/JavaScript in [index.html](index.html) and [FE/](FE).
- Backend: FastAPI in [BE/](BE) with [app.py](app.py) as the entrypoint.
- Core orchestration: reused from [tradingagents/](tradingagents).
- Main transport: Server-Sent Events for live analysis and live chat streaming.

## Current Product Surface

- Realtime analysis dashboard via `POST /api/analyze`.
- Admin-only integrated chat page in the main dashboard via `POST /api/chat`.
- Google sign-in, backend session exchange, and role-based access.
- History/Admin APIs with optional Turso persistence.
- TradingView chart page with local watchlist support.

`llm.html` is no longer part of the main frontend flow. Chat is integrated directly into the main dashboard.

## Key Files

- [app.py](app.py): bootstrap entrypoint.
- [BE/server.py](BE/server.py): FastAPI routes.
- [BE/auth.py](BE/auth.py): Google auth and backend session handling.
- [BE/analysis.py](BE/analysis.py): analysis/chat streaming.
- [index.html](index.html): dashboard shell.
- [FE/app.js](FE/app.js): frontend state, SSE parsing, chat, history, chart, auth.
- [FE/styles.css](FE/styles.css): dashboard and integrated chat UI.
- [FE/config.js](FE/config.js): frontend defaults.

## Quick Start

```powershell
Copy-Item .env-example .env
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open: `http://127.0.0.1:8000`

## Minimum Environment

- `MINIMAX_API_KEY` or `MINIMAX_CN_API_KEY`
- `GOOGLE_CLIENT_ID`

Common optional variables:

- `CORS_ALLOW_ORIGINS`
- `ADMIN_EMAILS`
- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`

Keep all real secrets only in backend environment variables.

## Deployment Intent

- Frontend: Vercel or any static host.
- Backend: Render or another Python host.
- Database: Turso only when persistence is needed.

## Notes

- The current product is crypto-first.
- Chat and analysis both depend on Google-authenticated backend sessions.
- This project is a research assistant, not financial advice.
