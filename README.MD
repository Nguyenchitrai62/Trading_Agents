# Trading Agents

Multi-agent crypto market analysis platform. Four specialized analysts research independently, debate through structured rounds, and converge on a verified trading decision — streamed live to your browser.

**Live:** https://crypto.nguyenchitrai.id.vn

---

## Architecture

```
Browser (SSE)  ←  FastAPI Backend  ←  LangGraph Agent Graph
                                            │
                          ┌─────────────────┼─────────────────┐
                     CCXT (OHLCV)    CoinGlass (onchain)   Web Search
```

- **Frontend:** Vanilla HTML/CSS/JS, deploys as static site on Vercel
- **Backend:** FastAPI on Render, streams progress via `POST /api/analyze` (SSE)
- **Core:** LangGraph multi-agent pipeline under `tradingagents/`

---

## Agent Pipeline

| Stage | Agent(s) | Data |
|-------|----------|------|
| 1. Market Analysis | Market Analyst | CCXT OHLCV + technical indicators |
| 2. Onchain Analysis | Onchain Analyst | CoinGlass (reserves, liquidations, funding, OI, flows) |
| 3. Social Analysis | Social Analyst | Live web search |
| 4. News Analysis | News Analyst | Live web search |
| 5. Research Debate | Bull + Bear Researchers | Analyst reports |
| 6. Risk Debate | Aggressive + Conservative + Neutral | Research consensus |
| 7. Portfolio Decision | Portfolio Manager | Full debate history |
| 8. Verification | Verifier | Decision + live price |
| 9. Decision Extraction | Decision Extractor | Verified markdown |

**Depth options:** Quick (1 round), Medium (3 rounds), Deep (5 rounds) — affects debate call count.

---

## Quick Start

### Prerequisites

- Python 3.10+
- LLM key: [DeepSeek V4 Flash](https://opencode.ai/go) ($5/mo) or [MiniMax M2.5](https://platform.minimax.io/subscribe/token-plan) ($10/mo)
- [CoinGlass API key](https://www.coinglass.com/) ($35/mo) — required for onchain data
- [Google OAuth client ID](https://console.cloud.google.com/apis/credentials)

### Setup

```powershell
git clone <repo-url> && cd TradingAgents
Copy-Item .env-example .env
```

Fill in `.env`:

```ini
DEEPSEEK_API_KEY=sk-...        # or MINIMAX_API_KEY
COINGLASS_API_KEY=xxxx-xxxx    # required
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
```

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

---

## Environment Variables

### Required

| Variable | Purpose |
|----------|---------|
| `MINIMAX_API_KEY` *or* `DEEPSEEK_API_KEY` | LLM provider (pick one) |
| `COINGLASS_API_KEY` | On-chain data — exchange reserves, liquidations, funding rates, OI, flows |
| `GOOGLE_CLIENT_ID` | Google OAuth for dashboard sign-in |

### Optional

| Variable | Purpose | Default |
|----------|---------|:------:|
| `TURSO_DATABASE_URL` | Run history persistence | — |
| `TURSO_AUTH_TOKEN` | Turso auth | — |
| `CORS_ALLOW_ORIGINS` | Allowed origins (required for production) | — |
| `PORT` | Server port | `8000` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `ADMIN_EMAILS` | Comma-separated admin emails | — |
| `ANALYSIS_MAX_CONCURRENT_RUNS` | Max simultaneous analyses | `1` |
| `DEFAULT_RESEARCH_DEPTH` | `quick`, `medium`, `deep`, `auto` | `auto` |
| `TRADINGAGENTS_OUTPUT_LANGUAGE` | Report language | `English` |

See `.env-example` for all options.

---

## Deployment

| Layer | Platform | Cost |
|-------|----------|:----:|
| Frontend | [Vercel](https://vercel.com) | Free |
| Backend | [Render](https://render.com) | Free |
| Database | [Turso](https://turso.tech) | Free |
| LLM | [DeepSeek](https://opencode.ai/go) | $5/mo |
| | [MiniMax](https://platform.minimax.io) | $10/mo |
| On-Chain Data | [CoinGlass](https://www.coinglass.com/) | $35/mo |

**Backend start command (Render):**

```powershell
uvicorn app:app --host 0.0.0.0 --port $env:PORT
```

**Frontend:** Deploy `index.html`, `FE/`, `image/` as static assets. Update `FE/config.js` `apiBaseUrl` to your backend URL. Set `CORS_ALLOW_ORIGINS` accordingly.

---

## LLM Providers

Both run the full pipeline. Difference is in web search.

| | DeepSeek V4 Flash | MiniMax M2.5 |
|---|---|---|
| Cost | $5/mo | $10/mo |
| Web Search | `webfetch` (urllib) | MCP `web_search` (multi-source) |
| Setup | API key only | API key + MCP server |

Switch via UI config panel or environment variable.

---

## Project Structure

```
├── app.py                    # Entry point
├── index.html                # Dashboard shell
├── BE/                       # FastAPI backend
│   ├── server.py             # Routes, CORS
│   ├── config.py             # Settings from .env
│   ├── auth.py               # Google OAuth
│   ├── models.py             # Pydantic schemas
│   ├── analysis/             # SSE orchestration service
│   └── history/              # Turso persistence
├── tradingagents/            # Core library
│   ├── agents/               # Analysts, researchers, risk, managers
│   ├── graph/                # LangGraph orchestration
│   └── dataflows/            # CCXT, CoinGlass clients
├── FE/                       # Static frontend
│   ├── config.js             # API URL + defaults
│   ├── styles/               # CSS partials
│   └── scripts/              # Dashboard, history, chart, reports
└── requirements.txt
```

---

## Disclaimer

TradingAgents is a research assistant, not financial advice. Cryptocurrency trading involves substantial risk. Currently supports crypto assets only.

---

## Credits

Inspired by [Tauric Research / TradingAgents](https://github.com/tauricresearch/tradingagents).
