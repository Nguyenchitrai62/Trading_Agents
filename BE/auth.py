from __future__ import annotations

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
            response = requests.get(
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
        if email not in self.settings.google_allowed_emails:
            raise HTTPException(status_code=403, detail="This Google account is not allowed to run analysis.")

        user = {
            "email": email,
            "sub": str(payload.get("sub") or ""),
            "name": str(payload.get("name") or ""),
            "picture": str(payload.get("picture") or ""),
            "email_verified": True,
            "authorized": True,
        }
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
            "iat": issued_at,
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
        if not self.settings.google_allowed_emails:
            raise HTTPException(status_code=500, detail="GOOGLE_ALLOWED_EMAIL or GOOGLE_ALLOWED_EMAILS is not configured.")

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

        raise HTTPException(status_code=401, detail="Session has expired. Sign in with Google again.")

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
        request.state.auth_user = user
        await self._persist_user_if_possible(user)
        return user

    async def require_authorized_user(self, request: Request) -> dict:
        user = await self.attach_request_auth_context(request, required=True)
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in with Google before running analysis.")
        return user