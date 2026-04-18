"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # NVIDIA / Nemotron
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="nvidia/llama-3.3-nemotron-super-49b-v1", alias="NVIDIA_MODEL")

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

    # General
    timezone: str = Field(default="Europe/Helsinki", alias="TIMEZONE")
    dry_run: bool = Field(default=True, alias="DRY_RUN")


settings = Settings()
