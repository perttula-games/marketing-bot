"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM provider (OpenAI-compatible API).
    # Prefer LLM_* names; NVIDIA_* are kept as backwards-compatible fallbacks.
    llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY", "NVIDIA_API_KEY"))
    llm_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "NVIDIA_BASE_URL"),
    )
    llm_model: str = Field(
        default="nvidia/llama-3.3-nemotron-super-49b-v1",
        validation_alias=AliasChoices("LLM_MODEL", "NVIDIA_MODEL"),
    )

    # LinkedIn
    linkedin_access_token: str = Field(default="", alias="LINKEDIN_ACCESS_TOKEN")
    linkedin_author_urn: str = Field(default="", alias="LINKEDIN_AUTHOR_URN")

    # X / Twitter
    x_api_key: str = Field(default="", alias="X_API_KEY")
    x_api_secret: str = Field(default="", alias="X_API_SECRET")
    x_access_token: str = Field(default="", alias="X_ACCESS_TOKEN")
    x_access_token_secret: str = Field(default="", alias="X_ACCESS_TOKEN_SECRET")

    # Instagram
    ig_access_token: str = Field(default="", alias="IG_ACCESS_TOKEN")
    ig_user_id: str = Field(default="", alias="IG_USER_ID")

    # Bluesky
    bluesky_identifier: str = Field(default="", alias="BLUESKY_IDENTIFIER")
    bluesky_app_password: str = Field(default="", alias="BLUESKY_APP_PASSWORD")
    bluesky_service_url: str = Field(default="https://bsky.social", alias="BLUESKY_SERVICE_URL")
    bluesky_session_file: str = Field(default="~/.nemo-bot/bluesky-session.json", alias="BLUESKY_SESSION_FILE")

    # General
    timezone: str = Field(default="Europe/Helsinki", alias="TIMEZONE")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    marketing_system_prompt_file: str = Field(
        default="marketing-system-prompt.md",
        alias="MARKETING_SYSTEM_PROMPT_FILE",
    )

    # Comma-separated allowlist of hosts allowed to serve Instagram images
    # (e.g. your S3 / R2 / Supabase storage). Subdomains of an allowed host
    # are also accepted. Empty list => no image publishes are allowed.
    ig_image_host_allowlist: str = Field(default="", alias="IG_IMAGE_HOST_ALLOWLIST")

    # Telegram approval bot (optional)
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    # Comma-separated chat ids of approvers. Everyone else is ignored.
    telegram_approver_chat_ids: str = Field(default="", alias="TELEGRAM_APPROVER_CHAT_IDS")
    # Optional comma-separated Telegram user ids. If set, chat id AND user id must match.
    telegram_approver_user_ids: str = Field(default="", alias="TELEGRAM_APPROVER_USER_IDS")
    telegram_poll_seconds: int = Field(default=10, alias="TELEGRAM_POLL_SECONDS")

    # Discord publisher (optional)
    discord_webhook_url: str = Field(default="", alias="DISCORD_WEBHOOK_URL")


settings = Settings()


def approver_chat_ids() -> set[int]:
    raw = settings.telegram_approver_chat_ids.strip()
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


def approver_user_ids() -> set[int]:
    raw = settings.telegram_approver_user_ids.strip()
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


def ig_image_allowlist() -> frozenset[str]:
    raw = settings.ig_image_host_allowlist.strip()
    if not raw:
        return frozenset()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
