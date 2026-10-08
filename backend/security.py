"""Browser security controls for CORS, CSRF, rate limits and response headers."""
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware


SESSION_MAX_AGE = 60 * 60 * 24 * 7
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT_PATHS = {"/api/auth/session"}
RATE_LIMITS = {
    "/api/chat": (30, 60),
    "/api/voice/tts": (20, 60),
    "/api/voice/stt": (20, 60),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https://*.googleusercontent.com; "
        "font-src 'self' data:; connect-src 'self'; media-src 'self' blob:"
    ),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=(self)",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def normalize_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Geçersiz origin yapılandırması")
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def configured_origins() -> set[str]:
    configured = [item.strip() for item in os.environ["CORS_ORIGINS"].split(",") if item.strip()]
    if not configured or "*" in configured:
        raise RuntimeError("CORS_ORIGINS açık bir allowlist olmalı; wildcard yasak")
    configured.append(os.environ["FRONTEND_URL"])
    return {normalize_origin(origin) for origin in configured}


class SlidingWindowLimiter:
    def __init__(self):
        self._requests = defaultdict(deque)

    def check(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = self._requests[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
        return True, 0


class BrowserSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, session_secret: str, allowed_origins: set[str]):
        super().__init__(app)
        self.allowed_origins = allowed_origins
        self.primary_origin = normalize_origin(os.environ["FRONTEND_URL"])
        self.session_serializer = URLSafeTimedSerializer(session_secret)
        self.csrf_serializer = URLSafeTimedSerializer(session_secret, salt="nova-csrf-v1")
        self.csrf_key = session_secret.encode()
        self.limiter = SlidingWindowLimiter()

    def _csrf_subject(self, session_id: str) -> str:
        return hmac.new(self.csrf_key, session_id.encode(), hashlib.sha256).hexdigest()

    def issue_csrf(self, cookie_value: str) -> str:
        session_id = self.session_serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
        return self.csrf_serializer.dumps(self._csrf_subject(session_id))

    def valid_csrf(self, cookie_value: str, csrf_token: str) -> bool:
        try:
            session_id = self.session_serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
            supplied = self.csrf_serializer.loads(csrf_token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        return hmac.compare_digest(str(supplied), self._csrf_subject(session_id))

    def _secure(self, response):
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Access-Control-Allow-Origin", self.primary_origin)
        response.headers.setdefault("Vary", "Origin")
        return response

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return self._secure(await call_next(request))

        origin = request.headers.get("origin")
        if origin:
            try:
                normalized_origin = normalize_origin(origin)
            except RuntimeError:
                return self._secure(JSONResponse({"detail": "Origin reddedildi"}, status_code=403))
            if normalized_origin not in self.allowed_origins:
                return self._secure(JSONResponse({"detail": "Origin reddedildi"}, status_code=403))

        if request.method in UNSAFE_METHODS:
            referer = request.headers.get("referer")
            if referer:
                try:
                    if normalize_origin(referer) not in self.allowed_origins:
                        return self._secure(JSONResponse({"detail": "Referer reddedildi"}, status_code=403))
                except RuntimeError:
                    return self._secure(JSONResponse({"detail": "Referer reddedildi"}, status_code=403))

            cookie = request.cookies.get("nova_session")
            if cookie and request.url.path not in CSRF_EXEMPT_PATHS:
                csrf_token = request.headers.get("x-csrf-token", "")
                if not csrf_token or not self.valid_csrf(cookie, csrf_token):
                    return self._secure(JSONResponse({"detail": "CSRF doğrulaması başarısız"}, status_code=403))

            rate = RATE_LIMITS.get(request.url.path)
            if cookie and rate:
                identity = hashlib.sha256(cookie.encode()).hexdigest()
                allowed, retry_after = self.limiter.check(f"{request.url.path}:{identity}", *rate)
                if not allowed:
                    response = JSONResponse({"detail": "İstek sınırı aşıldı"}, status_code=429)
                    response.headers["Retry-After"] = str(retry_after)
                    return self._secure(response)

        return self._secure(await call_next(request))


def csrf_token_for_request(request: Request) -> str:
    cookie = request.cookies.get("nova_session")
    if not cookie:
        raise BadSignature("missing session cookie")
    session_secret = os.environ["SESSION_SECRET"]
    session_id = URLSafeTimedSerializer(session_secret).loads(cookie, max_age=SESSION_MAX_AGE)
    subject = hmac.new(session_secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return URLSafeTimedSerializer(session_secret, salt="nova-csrf-v1").dumps(subject)
