from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analysis import AnalysisService
from .auth import AuthService
from .config import DEFAULT_ANALYSTS, RESEARCH_DEPTH_OPTIONS, SETTINGS, logger, resolve_minimax_settings
from .history import TursoHistoryStore
from .models import AdminUserAccessUpdate, AnalysisRequest, AuthSessionRequest, ChatRequest


history_store = TursoHistoryStore(SETTINGS.turso_database_url, SETTINGS.turso_auth_token, SETTINGS.history_page_size)
auth_service = AuthService(SETTINGS, history_store)
analysis_service = AnalysisService(SETTINGS, history_store)


def create_app() -> FastAPI:
    app = FastAPI(title=SETTINGS.app_title, version=SETTINGS.app_version)

    def apply_api_response_headers(request: Request, response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")

        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if SETTINGS.allow_all_origins else list(SETTINGS.cors_allow_origins),
        allow_credentials=not SETTINGS.allow_all_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        has_auth_header = bool(request.headers.get("Authorization", "").strip() or request.headers.get("X-Google-ID-Token", "").strip())
        if request.url.path.startswith("/api/") and has_auth_header:
            try:
                await auth_service.attach_request_auth_context(request, required=False)
            except HTTPException as exc:
                response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
                return apply_api_response_headers(request, response)

        response = await call_next(request)
        return apply_api_response_headers(request, response)

    app.mount("/FE", StaticFiles(directory=str(SETTINGS.frontend_dir)), name="frontend")
    if SETTINGS.image_dir.exists():
        app.mount("/image", StaticFiles(directory=str(SETTINGS.image_dir)), name="image")

    @app.on_event("startup")
    async def initialize_history_database() -> None:
        if not history_store.configured:
            logger.warning("Turso history database is not configured; history persistence is disabled.")
            return
        try:
            await asyncio.to_thread(history_store.ensure_schema)
            logger.info("Turso history database schema is ready.")
        except Exception as exc:
            history_store._schema_error = str(exc)
            logger.exception("Turso history database bootstrap failed; history persistence will retry lazily.")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index() -> HTMLResponse:
        return HTMLResponse(SETTINGS.index_file.read_text(encoding="utf-8"))

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        logo_file = SETTINGS.image_dir / "LOGO.png"
        if logo_file.exists():
            return FileResponse(logo_file, media_type="image/png")
        return Response(status_code=204)

    @app.get("/health")
    async def health_check() -> dict:
        minimax_settings = resolve_minimax_settings(SETTINGS)
        return {
            "status": "healthy",
            "title": SETTINGS.app_title,
            "version": SETTINGS.app_version,
            "configured": minimax_settings["configured"],
            "provider": minimax_settings["provider"],
            "resource_constrained": SETTINGS.resource_constrained_mode,
            "analysis_limits": {
                "cpu_threads": SETTINGS.analysis_cpu_threads,
                "max_concurrent_runs": SETTINGS.analysis_max_concurrent_runs,
                "llm_max_tokens": SETTINGS.analysis_llm_max_tokens,
            },
            "modes": ["analysis"],
        }

    @app.get("/api/config")
    async def public_config() -> dict:
        minimax_settings = resolve_minimax_settings(SETTINGS)
        return {
            "configured": minimax_settings["configured"],
            "provider": minimax_settings["provider"] or "minimax",
            "default_model": SETTINGS.default_model,
            "chat": {
                "max_tokens": SETTINGS.analysis_llm_max_tokens,
            },
            "auth": {
                "google_client_id": SETTINGS.google_client_id,
            },
            "history": {
                "configured": history_store.configured,
                "schema_ready": history_store._schema_ready,
                "public_read": SETTINGS.history_public_read,
                "page_size": SETTINGS.history_page_size,
                "default_access_days": SETTINGS.default_history_access_days,
            },
            "trading_view": {
                "symbol": SETTINGS.trading_view_symbol,
                "interval": SETTINGS.trading_view_interval,
                "symbols": list(SETTINGS.trading_view_symbols),
            },
            "analysis_defaults": {
                "symbol": SETTINGS.trading_view_symbol.split(":")[-1].replace("USDT", "-USDT"),
                "asset_type": SETTINGS.default_asset_type,
                "lookback_days": SETTINGS.default_analysis_lookback_days,
                "output_language": SETTINGS.default_output_language,
                "selected_analysts": list(SETTINGS.default_selected_analysts),
                "research_depth": SETTINGS.default_research_depth,
                "model": SETTINGS.default_model,
                "checkpoint_enabled": SETTINGS.default_checkpoint_enabled,
            },
            "analysis_options": {
                "analysts": [
                    {"value": value, "label": f"{value.title()} Analyst"}
                    for value in DEFAULT_ANALYSTS
                ],
                "research_depths": [
                    {"value": value, **meta}
                    for value, meta in RESEARCH_DEPTH_OPTIONS.items()
                ],
            },
        }

    @app.get("/api/auth/me")
    async def auth_me(http_request: Request) -> dict:
        return await auth_service.require_authorized_user(http_request)

    @app.post("/api/auth/session")
    async def create_auth_session(payload: AuthSessionRequest) -> dict:
        return await auth_service.create_session(payload.id_token)

    @app.get("/api/history")
    async def list_analysis_history(http_request: Request, page: int = 1, limit: int = SETTINGS.history_page_size) -> dict:
        if not history_store.configured:
            raise HTTPException(status_code=503, detail="Turso history database is not configured.")
        safe_page = max(1, int(page or 1))
        safe_limit = max(1, min(int(limit or SETTINGS.history_page_size), SETTINGS.history_page_size))
        offset = (safe_page - 1) * safe_limit
        user = await auth_service.require_authorized_user(http_request)
        rows = await asyncio.to_thread(history_store.list_accessible_runs, user.get("history_access_days"), safe_limit + 1, offset)
        items = rows[:safe_limit]
        return {
            "items": items,
            "configured": True,
            "public_read": False,
            "page": safe_page,
            "limit": safe_limit,
            "has_more": len(rows) > safe_limit,
            "history_access_days": user.get("history_access_days"),
            "history_access_unlimited": user.get("history_access_unlimited", False),
        }

    @app.get("/api/history/{run_id}")
    async def get_analysis_history(run_id: str, http_request: Request) -> dict:
        if not history_store.configured:
            raise HTTPException(status_code=503, detail="Turso history database is not configured.")
        user = await auth_service.require_authorized_user(http_request)
        result = await asyncio.to_thread(history_store.list_run_section_metas, run_id, user.get("history_access_days"))
        if result is None:
            raise HTTPException(status_code=404, detail="Analysis history item was not found.")
        return result

    @app.get("/api/history/{run_id}/sections")
    async def list_analysis_history_sections(run_id: str, http_request: Request) -> dict:
        if not history_store.configured:
            raise HTTPException(status_code=503, detail="Turso history database is not configured.")
        user = await auth_service.require_authorized_user(http_request)
        result = await asyncio.to_thread(history_store.list_run_section_metas, run_id, user.get("history_access_days"))
        if result is None:
            raise HTTPException(status_code=404, detail="Analysis history item was not found.")
        return result

    @app.get("/api/history/{run_id}/sections/{section_key}")
    async def get_analysis_history_section(run_id: str, section_key: str, http_request: Request) -> dict:
        if not history_store.configured:
            raise HTTPException(status_code=503, detail="Turso history database is not configured.")
        user = await auth_service.require_authorized_user(http_request)
        result = await asyncio.to_thread(history_store.get_run_section, run_id, section_key, user.get("history_access_days"))
        if result is None:
            raise HTTPException(status_code=404, detail="Analysis history section was not found.")
        return result

    @app.get("/api/admin/users")
    async def list_admin_users(http_request: Request) -> dict:
        await auth_service.require_admin_user(http_request)
        if not history_store.configured:
            raise HTTPException(status_code=503, detail="Turso history database is not configured.")
        users = await asyncio.to_thread(
            history_store.list_users,
            SETTINGS.default_history_access_days,
            SETTINGS.admin_emails,
        )
        return {"items": users}

    @app.patch("/api/admin/users/{email}")
    async def update_admin_user(email: str, payload: AdminUserAccessUpdate, http_request: Request) -> dict:
        await auth_service.require_admin_user(http_request)
        if not history_store.configured:
            raise HTTPException(status_code=503, detail="Turso history database is not configured.")
        user = await asyncio.to_thread(
            history_store.update_user_access,
            email,
            payload.is_admin,
            payload.can_run_analysis,
            payload.history_access_days,
            payload.history_access_unlimited,
            SETTINGS.default_history_access_days,
            SETTINGS.admin_emails,
        )
        return {"item": user}

    @app.post("/api/chat")
    async def chat_completion(request: ChatRequest, http_request: Request):
        await auth_service.require_analysis_runner(http_request)
        if not request.messages:
            raise HTTPException(status_code=400, detail="Messages cannot be empty")

        if request.stream:
            return StreamingResponse(
                analysis_service.generate_chat_stream(request),
                media_type="text/event-stream",
            )

        return await analysis_service.generate_non_streaming_chat(request)

    @app.post("/api/analyze/{run_id}/cancel")
    async def cancel_trading_analysis(run_id: str, http_request: Request) -> dict:
        await auth_service.require_analysis_runner(http_request)
        return analysis_service.cancel_run(run_id)

    @app.post("/api/analyze")
    async def analyze_trading_agents(analysis_request: AnalysisRequest, http_request: Request):
        user = await auth_service.require_analysis_runner(http_request)
        if not analysis_service.try_reserve_analysis_slot():
            raise HTTPException(
                status_code=429,
                detail=(
                    "Analysis capacity is full for the current deployment size. "
                    "Wait for the active run to finish before starting another."
                ),
            )

        try:
            return StreamingResponse(
                analysis_service.generate_analysis_stream(analysis_request, http_request, user, reserved_slot=True),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except Exception:
            analysis_service.release_analysis_slot()
            raise

    return app


app = create_app()