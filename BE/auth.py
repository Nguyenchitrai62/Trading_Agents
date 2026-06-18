from __future__ import annotations

import atexit
import asyncio
import base64
import hashlib
import hmac
import json
import threading
import time

import requests
from fastapi import HTTPException, Request

from .config import BackendSettings, logger
from .history import TursoHistoryStore

# Module-level shared session for Google token verification.
# Single connection pool reused across all _verify_google_id_token calls.
_GOOGLE_VERIFY_SESSION: requests.Session | None = None
_GOOGLE_VERIFY_SESSION_LOCK = threading.Lock()


def _get_google_verify_session() -> requests.Session:
    """Return the module-level Google-verification session, creating it lazily."""
    global _GOOGLE_VERIFY_SESSION  # noqa: PLW0603
    if _GOOGLE_VERIFY_SESSION is not None:
        return _GOOGLE_VERIFY_SESSION
    with _GOOGLE_VERIFY_SESSION_LOCK:
        if _GOOGLE_VERIFY_SESSION is not None:
            return _GOOGLE_VERIFY_SESSION
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=2,
            pool_maxsize=4,
            max_retries=0,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _GOOGLE_VERIFY_SESSION = session
        return session


def close_google_verify_session() -> None:
    """Close the module-level Google-verification session."""
    global _GOOGLE_VERIFY_SESSION  # noqa: PLW0603
    with _GOOGLE_VERIFY_SESSION_LOCK:
        if _GOOGLE_VERIFY_SESSION is not None:
            try:
                _GOOGLE_VERIFY_SESSION.close()
            except Exception:
                pass
            _GOOGLE_VERIFY_SESSION = None


atexit.register(close_google_verify_session)

try:
    from google.auth.transport import requests as google_auth_requests
    from google.oauth2 import id_token as google_id_token
except ImportError:
    google_auth_requests = None
    google_id_token = None


class InvalidSessionToken(ValueError):
    pass


class AuthService:
    def __init__(self, settings: BackendSettings, history_store: TursoHistoryStore):
        self.settings = settings
        self.history_store = history_store
        self.cache: dict[str, tuple[float, dict]] = {}
        self.cache_lock = threading.Lock()

    def _extract_auth_token(self, request: Request) -> str:
        bearer = request.headers.get("Authorization", "").strip()
        if bearer.lower().startswith("bearer "):
            return bearer[7:].strip()
        return request.headers.get("X-Google-ID-Token", "").strip()

    @staticmethod
    def _base64url_encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")

    @staticmethod
    def _base64url_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)

    def _session_signature(self, signing_input: bytes) -> str:
        digest = hmac.new(
            self.settings.auth_session_secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        return self._base64url_encode(digest)

    def _prune_auth_cache(self, now: float) -> None:
        expired_keys = [key for key, (expires_at, _) in self.cache.items() if expires_at <= now]
        for key in expired_keys:
            self.cache.pop(key, None)
        overflow = len(self.cache) - self.settings.auth_cache_max_entries
        if overflow <= 0:
            return
        oldest_keys = [
            key
            for key, _ in sorted(self.cache.items(), key=lambda item: item[1][0])[:overflow]
        ]
        for key in oldest_keys:
            self.cache.pop(key, None)

    def _looks_like_session_token(self, token: str) -> bool:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        try:
            payload = json.loads(self._base64url_decode(parts[1]))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return False
        return payload.get("iss") == "tradingagents-session" and payload.get("kind") == "frontend_session"

    def _verify_google_id_token(self, token: str) -> dict:
        if not self.settings.google_client_id:
            raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured on the backend.")

        if google_id_token is not None and google_auth_requests is not None:
            try:
                return google_id_token.verify_oauth2_token(
                    token,
                    google_auth_requests.Request(),
                    self.settings.google_client_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=401, detail="Google sign-in token is invalid or expired.") from exc
            except Exception as exc:
                raise HTTPException(status_code=401, detail="Could not verify Google sign-in token.") from exc

        try:
            response = _get_google_verify_session().get(
                self.settings.google_tokeninfo_url,
                params={"id_token": token},
                timeout=8,
            )
        except requests.RequestException as exc:
            raise HTTPException(status_code=401, detail="Could not verify Google sign-in token.") from exc

        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Google sign-in token is invalid or expired.")

        payload = response.json()
        audience = str(payload.get("aud") or "").strip()
        if audience != self.settings.google_client_id:
            raise HTTPException(status_code=401, detail="Google sign-in token was issued for a different client.")
        return payload

    def _build_user_from_payload(self, payload: dict) -> dict:
        email = str(payload.get("email") or "").strip().lower()
        email_verified = payload.get("email_verified") is True or str(payload.get("email_verified") or "").lower() == "true"
        if not email or not email_verified:
            raise HTTPException(status_code=403, detail="Google account email is not verified.")
        if self.settings.auth_restrict_to_allowed_emails:
            allowed_emails = self.settings.google_allowed_emails | self.settings.admin_emails
            if email not in allowed_emails:
                raise HTTPException(status_code=403, detail="This Google account is not allowed to sign in.")

        user = {
            "email": email,
            "sub": str(payload.get("sub") or ""),
            "name": str(payload.get("name") or ""),
            "picture": str(payload.get("picture") or ""),
            "email_verified": True,
            "authorized": True,
        }
        return self._hydrate_user_permissions(user)

    def _history_public_read_enabled(self) -> bool:
        if not self.history_store.configured:
            return bool(self.settings.history_public_read)
        try:
            return bool(self.history_store.get_history_public_read(self.settings.history_public_read))
        except Exception:
            logger.warning("Could not load global history-read policy from history database.", exc_info=True)
            return bool(self.settings.history_public_read)

    @staticmethod
    def _has_personal_history_access(is_admin: bool, history_access_days: int | None, history_access_unlimited: bool) -> bool:
        if is_admin or history_access_unlimited:
            return True
        return history_access_days is not None and int(history_access_days) > 0

    def _hydrate_user_permissions(self, user: dict) -> dict:
        email = str(user.get("email") or "").strip().lower()
        is_admin = email in self.settings.admin_emails
        can_run_analysis = is_admin
        history_access_unlimited = is_admin
        history_access_days: int | None = None if is_admin else self.settings.default_history_access_days
        if email and self.history_store.configured:
            try:
                access = self.history_store.get_user_access(
                    email,
                    self.settings.default_history_access_days,
                    self.settings.admin_emails,
                )
                is_admin = bool(access.get("is_admin"))
                can_run_analysis = bool(access.get("can_run_analysis"))
                history_access_unlimited = bool(access.get("history_access_unlimited", False)) or is_admin
                history_access_days = access.get("history_access_days")
            except Exception:
                logger.warning("Could not load user access settings from history database.", exc_info=True)
        can_run_analysis = can_run_analysis or is_admin
        history_access_unlimited = history_access_unlimited or is_admin
        can_read_history = is_admin or (
            self._history_public_read_enabled()
            and self._has_personal_history_access(is_admin, history_access_days, history_access_unlimited)
        )
        user.update(
            {
                "email": email,
                "authorized": True,
                "is_admin": is_admin,
                "role": "admin" if is_admin else "runner" if can_run_analysis else "user",
                "can_run_analysis": can_run_analysis,
                "history_access_days": history_access_days,
                "history_access_unlimited": history_access_unlimited,
                "can_read_history": can_read_history,
            }
        )
        return user

    def _verify_session_token(self, token: str) -> dict:
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidSessionToken("Malformed session token.")

        try:
            header = json.loads(self._base64url_decode(parts[0]))
            payload = json.loads(self._base64url_decode(parts[1]))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InvalidSessionToken("Malformed session token.") from exc

        if header.get("alg") != "HS256":
            raise InvalidSessionToken("Unexpected session algorithm.")
        if payload.get("iss") != "tradingagents-session" or payload.get("kind") != "frontend_session":
            raise InvalidSessionToken("Token is not a TradingAgents session.")
        expires_at = int(payload.get("exp") or 0)
        if expires_at and expires_at <= int(time.time()):
            raise HTTPException(status_code=401, detail="Session has expired. Sign in with Google again.")

        signing_input = f"{parts[0]}.{parts[1]}".encode("utf-8")
        expected_signature = self._session_signature(signing_input)
        if not hmac.compare_digest(parts[2], expected_signature):
            raise InvalidSessionToken("Invalid session signature.")

        return self._build_user_from_payload(payload)

    def _create_session_token(self, user: dict) -> tuple[str, int]:
        issued_at = int(time.time())
        expires_at = issued_at + self.settings.auth_session_ttl_seconds
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "iss": "tradingagents-session",
            "kind": "frontend_session",
            "sub": str(user.get("sub") or ""),
            "email": str(user.get("email") or "").strip().lower(),
            "name": str(user.get("name") or ""),
            "picture": str(user.get("picture") or ""),
            "email_verified": True,
            "authorized": True,
            "is_admin": bool(user.get("is_admin", False)),
            "can_run_analysis": bool(user.get("can_run_analysis", False)),
            "can_read_history": bool(user.get("can_read_history", False)),
            "history_access_days": user.get("history_access_days"),
            "history_access_unlimited": bool(user.get("history_access_unlimited", user.get("history_access_days") is None)),
            "iat": issued_at,
            "exp": expires_at,
        }
        header_segment = self._base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_segment = self._base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
        signature_segment = self._session_signature(signing_input)
        return f"{header_segment}.{payload_segment}.{signature_segment}", expires_at

    def _cache_user(self, token: str, user: dict, expires_at: float) -> None:
        now = time.time()
        token_hash = hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()
        with self.cache_lock:
            self._prune_auth_cache(now)
            self.cache[token_hash] = (
                max(now + 30, min(expires_at, now + self.settings.auth_session_ttl_seconds)),
                user,
            )

    async def _persist_user_if_possible(self, user: dict) -> None:
        if not self.history_store.configured:
            return
        try:
            await asyncio.to_thread(self.history_store.upsert_user, user)
        except Exception:
            logger.warning("Could not persist Google user profile to history database.", exc_info=True)

    def _validate_google_id_token_uncached(self, token: str) -> tuple[dict, float]:
        if not token:
            raise HTTPException(status_code=401, detail="Sign in with Google before running analysis.")

        payload = self._verify_google_id_token(token)
        user = self._build_user_from_payload(payload)
        try:
            expires_at = float(payload.get("exp") or 0)
        except (TypeError, ValueError):
            expires_at = time.time() + 300
        return user, expires_at

    def _validate_google_id_token(self, token: str) -> dict:
        token_hash = hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()
        now = time.time()
        with self.cache_lock:
            self._prune_auth_cache(now)
            cached = self.cache.get(token_hash)
            if cached and cached[0] > now:
                return cached[1]

        user, expires_at = self._validate_google_id_token_uncached(token)
        self._cache_user(token, user, expires_at)
        return user

    def _validate_auth_token(self, token: str) -> dict:
        if not token:
            raise HTTPException(status_code=401, detail="Sign in with Google before running analysis.")

        token_hash = hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()
        now = time.time()
        cached_user = None
        extend_cached_session = False
        with self.cache_lock:
            self._prune_auth_cache(now)
            cached = self.cache.get(token_hash)
            if cached and cached[0] > now:
                cached_user = cached[1]
                extend_cached_session = self._looks_like_session_token(token)

        if cached_user is not None:
            if extend_cached_session:
                self._cache_user(token, cached_user, now + self.settings.auth_session_ttl_seconds)
            return cached_user

        try:
            user = self._verify_session_token(token)
        except InvalidSessionToken:
            user, expires_at = self._validate_google_id_token_uncached(token)
            self._cache_user(token, user, expires_at)
            return user

        self._cache_user(token, user, time.time() + self.settings.auth_session_ttl_seconds)
        return user

    async def create_session(self, google_id_token: str) -> dict:
        user = await asyncio.to_thread(self._validate_google_id_token, google_id_token)
        session_token, expires_at = await asyncio.to_thread(self._create_session_token, user)
        await self._persist_user_if_possible(user)
        self._cache_user(session_token, user, float(expires_at))
        return {
            "session_token": session_token,
            "expires_at": expires_at,
            "user": user,
        }

    async def attach_request_auth_context(self, request: Request, required: bool = False) -> dict | None:
        existing_user = getattr(request.state, "auth_user", None)
        if existing_user is not None:
            return existing_user

        token = self._extract_auth_token(request)
        if not token:
            if required:
                raise HTTPException(status_code=401, detail="Sign in with Google before running analysis.")
            return None

        user = await asyncio.to_thread(self._validate_auth_token, token)
        user = await asyncio.to_thread(self._hydrate_user_permissions, user)
        request.state.auth_user = user
        await self._persist_user_if_possible(user)
        return user

    async def require_authorized_user(self, request: Request) -> dict:
        user = await self.attach_request_auth_context(request, required=True)
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in with Google before running analysis.")
        return user

    async def require_analysis_runner(self, request: Request) -> dict:
        user = await self.require_authorized_user(request)
        if not user.get("can_run_analysis"):
            raise HTTPException(status_code=403, detail="Run analysis permission is required.")
        return user

    async def require_history_reader(self, request: Request) -> dict:
        user = await self.require_authorized_user(request)
        if not user.get("can_read_history"):
            raise HTTPException(status_code=403, detail="History access is disabled for this account.")
        return user

    async def require_admin_user(self, request: Request) -> dict:
        user = await self.require_authorized_user(request)
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Admin permission is required.")
        return user