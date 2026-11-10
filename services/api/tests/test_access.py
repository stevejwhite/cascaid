"""The production-online Access boundary: every way in except a verified owner is refused."""

import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from psychiatry_api.access import MAX_JSON_BYTES, AccessVerifier
from psychiatry_api.config import Settings
from psychiatry_api.main import create_app

TEAM = "cascaid-test.cloudflareaccess.com"
ISSUER = f"https://{TEAM}"
AUDIENCE = "a" * 64
ORIGIN = "https://cascaid.example.org"
OWNER = "owner@example.org"
INTERNAL = "b" * 64
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk(key, kid="key-1"):
    return {
        **jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True),
        "kid": kid,
        "alg": "RS256",
    }


def token(key=KEY, kid="key-1", **claims):
    now = int(time.time())
    body = {
        "iss": ISSUER,
        "aud": [AUDIENCE],
        "sub": "user-123",
        "email": OWNER,
        "iat": now,
        "nbf": now,
        "exp": now + 600,
        "type": "app",
        **claims,
    }
    return jwt.encode(
        {k: v for k, v in body.items() if v is not None}, key, "RS256", headers={"kid": kid}
    )


class Keys:
    """A stand-in for the team's certs endpoint that counts fetches and can go down."""

    def __init__(self):
        self.fetches = 0
        self.down = False
        self.keys = [jwk(KEY)]

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{ISSUER}/cdn-cgi/access/certs"
        self.fetches += 1
        if self.down:
            return httpx.Response(500)
        return httpx.Response(200, json={"keys": self.keys})


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def online(tmp_path, **overrides):
    return Settings(
        _env_file=None,
        **{
            "deployment_profile": "production-online",
            "model_backend": "local",
            "speech_backend": "local",
            "tts_backend": "local",
            "student_backend": "local",
            "sessions_path": tmp_path / "sessions",
            "classifier_cache": tmp_path / "cache",
            "access_team_domain": TEAM,
            "access_audience": AUDIENCE,
            "access_allowed_emails": f"{OWNER}, second@example.org",
            "public_origin": ORIGIN,
            "cascaid_internal_token": INTERNAL,
            **overrides,
        },
    )


@pytest.fixture
def keys():
    return Keys()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def make_client(tmp_path, keys, clock):
    def make(**overrides):
        settings = online(tmp_path, **overrides)
        verifier = AccessVerifier.of(
            settings, transport=httpx.MockTransport(keys.handler), clock=clock
        )
        return TestClient(create_app(settings, verifier))

    return make


@pytest.fixture
def client(make_client):
    return make_client()


def signed(value=None):
    return {"Cf-Access-Jwt-Assertion": value or token()}


def test_verified_owner_is_admitted_and_responses_are_not_cacheable(client):
    response = client.get("/api/cases", headers=signed())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_email_comparison_ignores_case(client):
    assert (
        client.get("/api/cases", headers=signed(token(email="Owner@Example.ORG"))).status_code
        == 200
    )


@pytest.mark.parametrize(
    "assertion",
    [
        None,
        "not-a-token",
        token(key=OTHER_KEY),  # forged: right key ID, wrong signature
        token(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200),  # expired
        token(nbf=int(time.time()) + 3600),  # not yet valid
        token(aud=["c" * 64]),  # another Access application
        token(iss="https://attacker.cloudflareaccess.com"),
        token(sub=None),
        token(exp=None),
        token(kid="unknown"),
    ],
)
def test_unverifiable_assertions_are_refused(client, assertion):
    headers = {} if assertion is None else {"Cf-Access-Jwt-Assertion": assertion}
    response = client.get("/api/cases", headers=headers)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_other_algorithms_are_refused(client):
    public = jwk(KEY)["n"]
    hmac_token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "email": OWNER},
        public,
        "HS256",
        headers={"kid": "key-1"},
    )
    unsigned = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "email": OWNER},
        None,
        "none",
        headers={"kid": "key-1"},
    )
    for value in (hmac_token, unsigned):
        assert client.get("/api/cases", headers=signed(value)).status_code == 401


def test_bare_email_headers_are_not_trusted(client):
    headers = {"Cf-Access-Authenticated-User-Email": OWNER}
    assert client.get("/api/cases", headers=headers).status_code == 401


@pytest.mark.parametrize("claims", [{"email": "stranger@example.org"}, {"email": None}])
def test_verified_but_unlisted_identities_are_forbidden(client, claims):
    # A service token has no email; it is not permitted in the owner-only stage.
    assert client.get("/api/cases", headers=signed(token(**claims))).status_code == 403


def test_unreachable_keys_fail_closed(client, keys):
    keys.down = True
    response = client.get("/api/cases", headers=signed())
    assert response.status_code == 503


def test_cached_keys_survive_a_short_outage_but_not_a_long_one(client, keys, clock):
    assert client.get("/api/cases", headers=signed()).status_code == 200
    keys.down = True
    clock.now += 2 * 3600  # past freshness: refresh fails, cached keys still usable
    assert client.get("/api/cases", headers=signed()).status_code == 200
    clock.now += 5 * 3600  # past the stale limit
    assert client.get("/api/cases", headers=signed()).status_code == 503
    keys.down = False
    clock.now += 61
    assert client.get("/api/cases", headers=signed()).status_code == 200


def test_unknown_key_ids_refresh_at_most_once_a_minute(client, keys, clock):
    assert client.get("/api/cases", headers=signed()).status_code == 200
    assert keys.fetches == 1
    clock.now += 61
    for _ in range(3):
        client.get("/api/cases", headers=signed(token(kid="rotated")))
    assert keys.fetches == 2
    keys.keys.append(jwk(OTHER_KEY, "rotated"))
    clock.now += 61
    assert client.get("/api/cases", headers=signed(token(OTHER_KEY, "rotated"))).status_code == 200
    assert keys.fetches == 3


def test_loopback_probes_need_no_assertion_but_status_does(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/status").status_code == 401
    # A wrong internal secret on a probe is still refused rather than ignored.
    assert client.get("/health", headers={"X-CascAid-Internal": "c" * 64}).status_code == 401


def test_supervisor_secret_admits_warm_up_and_a_wrong_one_does_not(client):
    internal = {"X-CascAid-Internal": INTERNAL}
    # No such case: reaching 404 shows the request passed the boundary.
    assert (
        client.post("/api/sessions", json={"case_id": "none"}, headers=internal).status_code == 404
    )
    wrong = {"X-CascAid-Internal": "c" * 64, **signed()}
    assert client.post("/api/sessions", json={"case_id": "none"}, headers=wrong).status_code == 401


@pytest.mark.parametrize("origin", [None, "https://evil.example", "http://cascaid.example.org"])
def test_state_changes_need_the_public_origin(client, origin):
    headers = signed() | ({"Origin": origin} if origin else {})
    assert (
        client.post("/api/sessions", json={"case_id": "none"}, headers=headers).status_code == 403
    )


def test_state_changes_from_the_public_origin_pass(client):
    headers = signed() | {"Origin": ORIGIN}
    assert (
        client.post("/api/sessions", json={"case_id": "none"}, headers=headers).status_code == 404
    )


def test_bodies_are_bounded_whether_declared_or_streamed(client):
    headers = signed() | {"Origin": ORIGIN, "Content-Type": "application/json"}
    large = b'{"case_id": "' + b"x" * MAX_JSON_BYTES + b'"}'
    assert client.post("/api/sessions", content=large, headers=headers).status_code == 413

    def chunks():
        yield large[: len(large) // 2]
        yield large[len(large) // 2 :]

    response = client.post("/api/sessions", content=chunks(), headers=headers)
    assert response.status_code == 413
    assert "content-length" not in response.request.headers


def test_audio_uploads_have_their_own_larger_limit(client):
    headers = signed() | {"Origin": ORIGIN, "Content-Type": "audio/wav"}
    response = client.post(
        "/api/sessions/none/transcriptions", content=b"x" * (MAX_JSON_BYTES * 2), headers=headers
    )
    assert response.status_code == 422  # not a WAV; the size alone was accepted


def test_state_changes_are_rate_limited_per_identity(make_client):
    client = make_client(access_rate_limit_per_minute=2)
    headers = signed() | {"Origin": ORIGIN}
    statuses = [
        client.post("/api/sessions", json={"case_id": "none"}, headers=headers).status_code
        for _ in range(3)
    ]
    assert statuses == [404, 404, 429]
    assert client.get("/api/cases", headers=signed()).status_code == 200


def test_documentation_and_recordings_are_not_published(client):
    for path in ("/docs", "/redoc", "/openapi.json", "/api/recordings/prompts"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=signed()).status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"access_team_domain": None},
        {"access_team_domain": "evil.example.com"},
        {"access_audience": None},
        {"access_audience": "short"},
        {"access_allowed_emails": None},
        {"access_allowed_emails": "not-an-email"},
        {"public_origin": None},
        {"public_origin": "http://cascaid.example.org"},
        {"public_origin": "https://cascaid.example.org/"},
        {"public_origin": "https://cascaid.example.org:8443"},
        {"cascaid_internal_token": None},
        {"cascaid_internal_token": "short"},
        {"model_backend": "fake"},
        {"llm_base_url": "https://example.org/v1"},
    ],
)
def test_online_settings_fail_closed(tmp_path, overrides):
    with pytest.raises(ValidationError):
        online(tmp_path, **overrides)


def test_access_settings_are_refused_outside_the_online_profile(tmp_path):
    with pytest.raises(ValidationError):
        online(tmp_path, deployment_profile="production-local")
