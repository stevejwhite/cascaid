import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None if os.environ.get("CASCAID_PRODUCTION_ACTIVE") == "1" else ROOT / ".env",
        extra="ignore",
    )

    # production-online: production-local behind Cloudflare Tunnel and Access, with every API
    # route requiring a verified Access assertion (docs/ONLINE-PILOT-PLAN.md, stage 2).
    deployment_profile: Literal["development", "production-local", "production-online"] = (
        "development"
    )
    # Online profile only. Team domain such as myteam.cloudflareaccess.com; the application's
    # Access audience (AUD) tag; the emails allowed in (owner only until stage 3); the public
    # https origin browsers use; and the supervisor's per-start secret for its own warm-up.
    access_team_domain: str | None = None
    access_audience: str | None = None
    access_allowed_emails: str | None = None
    public_origin: str | None = None
    cascaid_internal_token: SecretStr | None = None
    access_rate_limit_per_minute: int = Field(default=120, ge=1, le=10_000)

    source_registry_path: Path = ROOT / "config/sources.yaml"
    cases_path: Path = ROOT / "data/cases"
    sessions_path: Path = ROOT / "data/sessions"
    web_port: int = Field(default=3105, ge=1, le=65535)
    api_port: int = Field(default=8105, ge=1, le=65535)
    # QA_BACKEND is the pre-CASC name, still accepted so existing .env files keep working.
    model_backend: Literal["fake", "local"] = Field(
        default="fake", validation_alias=AliasChoices("model_backend", "qa_backend")
    )
    native_model_home: Path = Path.home() / ".cache/psychiatryeduai"
    model_timeout_seconds: float = Field(default=60, gt=0, le=180)
    llm_base_url: str = "http://127.0.0.1:8180/v1"
    llm_model_id: str = "Qwen/Qwen3-4B-GGUF:Q4_K_M"
    llm_model_revision: str = "bc640142c66e1fdd12af0bd68f40445458f3869b"
    # cascade: local classifiers first, Qwen when they are not confident (falls back to Qwen
    # entirely if the embedding server is down). model: the Qwen interpreter for every turn.
    interpreter: Literal["model", "cascade"] = "cascade"
    classifier_cache: Path = ROOT / "artifacts/classifier"
    # Embedding model for the classifier interpreter (served alongside the generation model).
    embedding_base_url: str = "http://127.0.0.1:8181/v1"
    embedding_model_id: str = "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"
    embedding_model_revision: str = "370f27d7550e0def9b39c1f16d3fbaa13aa67728"
    # The fine-tuned student interpreter (docs/INTERPRETER-FINETUNE-PLAN.md): with the
    # cascade, it decides topics the classifiers are unsure of, before Qwen. off: Qwen does;
    # local: the mlx_lm server started by npm run student:start.
    student_backend: Literal["off", "local"] = "off"
    student_base_url: str = "http://127.0.0.1:8184"
    student_state_file: Path = ROOT / "artifacts/m4/student-state.json"
    # Cross-check (docs/STUDENT-CROSS-CHECK-PLAN.md): Qwen decides when the student's topic
    # differs from the classifiers' best guess. fact: only when that guess is another fact;
    # all: also when the guess is "no topic". off: the student's topic stands.
    student_cross_check: Literal["off", "fact", "all"] = "off"
    # What decides topics the classifiers are unsure of, before Qwen: the fine-tuned student or
    # the topic reranker (docs/RERANKER-PLAN.md; npm run reranker:start). The reranker answers
    # no topic below the threshold and hands the line to Qwen when the top two facts are
    # within the margin; description: labels, or labels_content (labels and the fact itself).
    topic_decider: Literal["student", "reranker"] = "student"
    reranker_base_url: str = "http://127.0.0.1:8185"
    reranker_state_file: Path = ROOT / "artifacts/m4/reranker-state.json"
    reranker_threshold: float = Field(default=0.5, ge=0, le=1)
    reranker_margin: float = Field(default=0.1, ge=0, le=1)
    reranker_description: Literal["labels", "labels_content"] = "labels"
    # off: no microphone; fake: fixed transcript for development; local: whisper.cpp server.
    speech_backend: Literal["off", "fake", "local"] = "off"
    asr_base_url: str = "http://127.0.0.1:8182"
    speech_state_file: Path = ROOT / "artifacts/m4/speech-state.json"
    # The character's voice: off (browser voices only); fake: silent audio with timings for
    # development; local: the HeadTTS server (Kokoro-82M) started by npm run tts:start.
    tts_backend: Literal["off", "fake", "local"] = "off"
    tts_base_url: str = "http://127.0.0.1:8183"
    tts_state_file: Path = ROOT / "artifacts/m4/tts-state.json"
    # Phase 4 evaluation only: lets consenting speakers record prompts to data/recordings.
    recordings_enabled: bool = False
    recordings_path: Path = ROOT / "data/recordings"
    readiness_timeout_seconds: float = Field(default=1.5, gt=0, le=10)
    # Case editor (docs/CASE-EDITOR-PLAN.md): off unless explicitly enabled on a local
    # development instance; never available in a production profile. Drafts stay in
    # authoring_path, which the learner case loader never reads.
    authoring_enabled: bool = False
    authoring_path: Path = ROOT / "data/authoring"
    # Browser origins (and hosts) allowed to use the editor, comma-separated.
    authoring_origins: str = "http://127.0.0.1:3105,http://localhost:3105"

    @model_validator(mode="after")
    def production_backends(self) -> "Settings":
        if os.environ.get("CASCAID_PRODUCTION_ACTIVE") == "1" and not self.production:
            raise ValueError("Explicit production deployment profile is required")
        access = (
            self.access_team_domain,
            self.access_audience,
            self.access_allowed_emails,
            self.public_origin,
            self.cascaid_internal_token,
        )
        if self.online:
            validate_access(self)
        elif any(value is not None for value in access):
            raise ValueError("Access settings are only accepted by the production-online profile")
        if self.production:
            if (
                any(
                    backend != "local"
                    for backend in (
                        self.model_backend,
                        self.speech_backend,
                        self.tts_backend,
                        self.student_backend,
                    )
                )
                or self.interpreter != "cascade"
            ):
                raise ValueError("Production requires the complete local model and speech stack")
            if self.recordings_enabled:
                raise ValueError("Production recording is disabled")
            if self.authoring_enabled:
                raise ValueError("The case editor is not available in production")
            for endpoint in (
                self.llm_base_url,
                self.embedding_base_url,
                self.asr_base_url,
                self.tts_base_url,
                self.student_base_url,
            ):
                url = urlparse(endpoint)
                if url.scheme != "http" or url.hostname != "127.0.0.1" or url.username:
                    raise ValueError("Production model endpoints must use HTTP on 127.0.0.1")
            for location in (self.sessions_path, self.classifier_cache):
                if not location.is_absolute() or location.resolve().is_relative_to(ROOT.resolve()):
                    raise ValueError("Production data and cache paths must be outside the release")
        return self

    @property
    def production(self) -> bool:
        return self.deployment_profile in {"production-local", "production-online"}

    @property
    def online(self) -> bool:
        return self.deployment_profile == "production-online"

    @property
    def allowed_emails(self) -> frozenset[str]:
        return frozenset(
            email.strip().casefold()
            for email in (self.access_allowed_emails or "").split(",")
            if email.strip()
        )


TEAM_DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com$")
EMAIL = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")


def validate_access(settings: Settings) -> None:
    """Fail closed: an online deployment without complete Access settings does not start."""
    if not TEAM_DOMAIN.fullmatch(settings.access_team_domain or ""):
        raise ValueError("ACCESS_TEAM_DOMAIN must be <team>.cloudflareaccess.com")
    if not re.fullmatch(r"[0-9a-f]{64}", settings.access_audience or ""):
        raise ValueError("ACCESS_AUDIENCE must be the application's 64-character AUD tag")
    emails = [e.strip() for e in (settings.access_allowed_emails or "").split(",")]
    if not emails or not all(EMAIL.fullmatch(email) for email in emails):
        raise ValueError("ACCESS_ALLOWED_EMAILS must list one or more email addresses")
    origin = urlparse(settings.public_origin or "")
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.port
        or origin.username
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
        or settings.public_origin != f"https://{origin.hostname}"
    ):
        raise ValueError("PUBLIC_ORIGIN must be https://<hostname> with no port, path or slash")
    token = settings.cascaid_internal_token
    if token is None or not re.fullmatch(r"[0-9a-f]{64}", token.get_secret_value()):
        raise ValueError("The supervisor must supply a 64-character internal token")
