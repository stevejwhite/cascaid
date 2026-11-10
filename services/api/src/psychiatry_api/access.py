"""Cloudflare Access boundary for the production-online profile (pilot plan, stage 2).

Every API request must carry a Cf-Access-Jwt-Assertion that verifies against the configured
Access team's signing keys, for this application's audience, from an allowed email. The only
exceptions are the loopback health probes (the web proxy forwards /api/* alone) and the
supervisor's own warm-up, which presents a per-start secret the web proxy refuses to forward.
Anything that cannot be verified is refused; there is no bypass setting.
"""

import asyncio
import hmac
import json
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from starlette.datastructures import Headers

from psychiatry_api.config import Settings
from psychiatry_api.speech import MAX_BYTES as MAX_AUDIO_BYTES

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

ASSERTION_HEADER = "cf-access-jwt-assertion"
INTERNAL_HEADER = "x-cascaid-internal"
PROBES = frozenset({"/health", "/ready"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_JSON_BYTES = 64 * 1024
MAX_TOKEN_BYTES = 8 * 1024
MAX_KEYS_BYTES = 64 * 1024
TRANSCRIPTION = re.compile(r"^/api/sessions/[^/]+/transcriptions$")


class AccessDenied(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class Identity:
    """Who made the request: a verified Access user, or the supervisor's own warm-up."""

    issuer: str
    subject: str
    email: str | None
    internal: bool = False

    @property
    def key(self) -> str:
        return "internal" if self.internal else f"{self.issuer}|{self.subject}"


INTERNAL = Identity(issuer="cascaid", subject="supervisor", email=None, internal=True)


class AccessVerifier:
    """Verifies Access assertions against the team's published RS256 keys.

    Keys are cached for `fresh_seconds`. An unknown key ID triggers a refresh at most once per
    `refresh_seconds`. If the key endpoint is unreachable, keys already fetched stay usable for
    `stale_seconds`; after that every request is refused with 503 until a fetch succeeds.
    """

    def __init__(
        self,
        team_domain: str,
        audience: str,
        allowed_emails: frozenset[str],
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        fresh_seconds: float = 3600,
        refresh_seconds: float = 60,
        stale_seconds: float = 6 * 3600,
        leeway_seconds: float = 30,
    ) -> None:
        self.issuer = f"https://{team_domain}"
        self.certs_url = f"{self.issuer}/cdn-cgi/access/certs"
        self.audience = audience
        self.allowed_emails = allowed_emails
        self.transport = transport
        self.clock = clock
        self.fresh_seconds = fresh_seconds
        self.refresh_seconds = refresh_seconds
        self.stale_seconds = stale_seconds
        self.leeway_seconds = leeway_seconds
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def of(cls, settings: Settings, **options: Any) -> "AccessVerifier":
        assert settings.access_team_domain and settings.access_audience
        return cls(
            settings.access_team_domain,
            settings.access_audience,
            settings.allowed_emails,
            **options,
        )

    async def verify(self, token: str) -> Identity:
        if not token or len(token.encode()) > MAX_TOKEN_BYTES:
            raise AccessDenied(401, "Sign-in is required")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as error:
            raise AccessDenied(401, "Sign-in is required") from error
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
            raise AccessDenied(401, "Sign-in is required")
        key = await self._key(kid)
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway_seconds,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as error:
            raise AccessDenied(401, "Sign-in is required") from error
        subject, email = claims.get("sub"), claims.get("email")
        if not isinstance(subject, str) or not subject:
            raise AccessDenied(401, "Sign-in is required")
        # Service tokens carry no email and are not permitted in the owner-only stage.
        if not isinstance(email, str) or email.casefold() not in self.allowed_emails:
            raise AccessDenied(403, "This account is not permitted to use CascAid")
        return Identity(issuer=self.issuer, subject=subject, email=email)

    async def _key(self, kid: str) -> jwt.PyJWK:
        async with self._lock:
            now = self.clock()
            fresh = self._fetched_at is not None and now - self._fetched_at < self.fresh_seconds
            recently = (
                self._attempted_at is not None and now - self._attempted_at < self.refresh_seconds
            )
            if not fresh or (kid not in self._keys and not recently):
                await self._refresh(now)
            usable = (
                self._fetched_at is not None
                and self.clock() - self._fetched_at < self.stale_seconds
            )
            if not usable:
                raise AccessDenied(503, "Sign-in cannot be verified at the moment; try again")
            if kid not in self._keys:
                raise AccessDenied(401, "Sign-in is required")
            return self._keys[kid]

    async def _refresh(self, now: float) -> None:
        self._attempted_at = now
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=5, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.get(self.certs_url)
            if response.status_code != 200 or len(response.content) > MAX_KEYS_BYTES:
                return
            keys = {}
            for entry in response.json().get("keys", ()):
                if entry.get("kty") == "RSA" and isinstance(entry.get("kid"), str):
                    keys[entry["kid"]] = jwt.PyJWK(entry, algorithm="RS256")
        except (httpx.HTTPError, ValueError, AttributeError, TypeError, jwt.PyJWKError):
            return
        if keys:
            self._keys, self._fetched_at = keys, self.clock()


class RateLimiter:
    """At most `limit` state-changing requests per identity in any 60-second window."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.clock = clock
        self._seen: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        seen = self._seen.setdefault(key, deque())
        while seen and now - seen[0] >= 60:
            seen.popleft()
        if len(seen) >= self.limit:
            return False
        seen.append(now)
        return True


class BodyTooLarge(Exception):
    pass


def body_limit(path: str) -> int:
    return MAX_AUDIO_BYTES if TRANSCRIPTION.fullmatch(path) else MAX_JSON_BYTES


async def refuse(send: Send, status: int, detail: str, headers: tuple = ()) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def private(send: Send) -> Send:
    """Responses may carry transcripts, feedback or a voice: never let a proxy or CDN keep them."""

    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = [
                (name, value)
                for name, value in message.get("headers", [])
                if name.lower() not in {b"cache-control", b"x-content-type-options"}
            ]
            headers += [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]
            message = {**message, "headers": headers}
        await send(message)

    return wrapped


class AccessBoundary:
    """ASGI middleware enforcing verified identity, origin, body size and rate limits."""

    def __init__(
        self, app: Callable, settings: Settings, verifier: AccessVerifier | None = None
    ) -> None:
        assert settings.online and settings.cascaid_internal_token and settings.public_origin
        self.app = app
        self.verifier = verifier or AccessVerifier.of(settings)
        self.internal_token = settings.cascaid_internal_token.get_secret_value().encode()
        self.origin = settings.public_origin
        self.limiter = RateLimiter(settings.access_rate_limit_per_minute)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            # No WebSocket routes exist; refuse rather than pass an unauthenticated upgrade.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return None
        send = private(send)
        method, path = scope["method"], scope["path"]
        headers = Headers(scope=scope)
        if path in PROBES and method in {"GET", "HEAD"} and INTERNAL_HEADER not in headers:
            return await self.app(scope, receive, send)
        try:
            identity = await self.authenticate(headers)
        except AccessDenied as error:
            return await refuse(send, error.status, error.detail)
        unsafe = method not in SAFE_METHODS
        if unsafe and not identity.internal and headers.get("origin") != self.origin:
            return await refuse(send, 403, "Cross-site request refused")
        if unsafe and not self.limiter.allow(identity.key):
            return await refuse(
                send, 429, "Too many requests; wait a minute", ((b"retry-after", b"60"),)
            )
        limit = body_limit(path)
        try:
            declared = int(headers.get("content-length") or 0)
        except ValueError:
            return await refuse(send, 400, "Invalid Content-Length")
        if declared > limit:
            return await refuse(send, 413, "Request body is too large")
        scope.setdefault("state", {})["identity"] = identity
        await self.limited(scope, receive, send, limit)

    async def authenticate(self, headers: Headers) -> Identity:
        if INTERNAL_HEADER in headers:
            supplied = headers[INTERNAL_HEADER].encode()
            if hmac.compare_digest(supplied, self.internal_token):
                return INTERNAL
            raise AccessDenied(401, "Sign-in is required")
        return await self.verifier.verify(headers.get(ASSERTION_HEADER, ""))

    async def limited(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        """Count body bytes as they arrive: Content-Length can be absent or wrong."""
        received, exceeded, started = 0, False, False

        async def counted() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise BodyTooLarge
            return message

        async def guarded(message: Message) -> None:
            nonlocal started
            if exceeded:
                # The application may have turned the failed read into its own error; the
                # client is told the actual reason instead.
                if message["type"] == "http.response.start" and not started:
                    started = True
                    await refuse(send, 413, "Request body is too large")
                return
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted, guarded)
        except BodyTooLarge:
            if not started:
                await refuse(send, 413, "Request body is too large")
