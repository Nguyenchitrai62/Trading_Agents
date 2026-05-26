from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import SETTINGS


class AnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1)
    asset_type: Literal["crypto"] = SETTINGS.default_asset_type
    run_id: str | None = Field(default=None, max_length=120)
    analysis_date: str = Field(default_factory=lambda: date.today().isoformat())
    lookback_days: int = Field(default=SETTINGS.default_analysis_lookback_days, ge=1)
    output_language: str = Field(default=SETTINGS.default_output_language)
    selected_analysts: list[Literal["market", "social", "news", "fundamentals"]] = Field(
        default_factory=lambda: list(SETTINGS.default_selected_analysts),
        min_length=1,
    )
    research_depth: Literal["quick", "medium", "deep"] = SETTINGS.default_research_depth
    model: str = Field(default=SETTINGS.default_model, min_length=1)
    checkpoint_enabled: bool = SETTINGS.default_checkpoint_enabled

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().replace(" ", "")
        if not normalized:
            raise ValueError("symbol is required")
        if "/" not in normalized and "-" not in normalized:
            return f"{normalized}-USDT"
        return normalized

    @field_validator("run_id")
    @classmethod
    def normalize_run_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("analysis_date")
    @classmethod
    def validate_analysis_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("analysis_date must be in YYYY-MM-DD format") from exc
        return value

    @field_validator("output_language")
    @classmethod
    def normalize_output_language(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("output_language is required")
        return normalized

    @field_validator("selected_analysts")
    @classmethod
    def normalize_selected_analysts(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        if not seen:
            raise ValueError("at least one analyst must be selected")
        return seen


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    model: str = SETTINGS.default_model
    max_tokens: int = 128000
    temperature: float = 1
    stream: bool = True


class AuthSessionRequest(BaseModel):
    id_token: str = Field(min_length=1)

    @field_validator("id_token")
    @classmethod
    def normalize_id_token(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("id_token is required")
        return normalized


class AdminUserAccessUpdate(BaseModel):
    is_admin: bool | None = None
    can_run_analysis: bool | None = None
    history_access_days: int | None = Field(default=None, ge=1)
    history_access_unlimited: bool = False