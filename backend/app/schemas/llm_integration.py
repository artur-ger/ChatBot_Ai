from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

LlmProviderType = Literal["openai_compatible", "rule_based", "gigachat"]


class LlmIntegrationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider: LlmProviderType
    model: str = Field(min_length=1, max_length=128)
    base_url: HttpUrl | None = None
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True
    activate: bool = False

    @field_validator("base_url", mode="before")
    @classmethod
    def empty_base_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class LlmIntegrationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: LlmProviderType | None = None
    model: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: HttpUrl | None = None
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None

    @field_validator("base_url", mode="before")
    @classmethod
    def empty_base_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class LlmIntegrationResponse(BaseModel):
    id: str
    name: str
    provider: LlmProviderType
    model: str
    base_url: str | None
    api_key_masked: str | None
    is_active: bool
    enabled: bool
    created_at: str
    updated_at: str


class LlmIntegrationListResponse(BaseModel):
    items: list[LlmIntegrationResponse]
    active_integration_id: str | None = None


class LlmIntegrationTestResponse(BaseModel):
    integration_id: str
    ok: bool
    message: str
    latency_ms: int | None = None


class LlmModelsLookupRequest(BaseModel):
    provider: LlmProviderType
    base_url: HttpUrl | None = None
    api_key: str | None = Field(default=None, max_length=4096)

    @field_validator("base_url", mode="before")
    @classmethod
    def empty_base_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class LlmModelsLookupResponse(BaseModel):
    provider: LlmProviderType
    models: list[str]


class LlmProviderSpecResponse(BaseModel):
    id: LlmProviderType
    label: str
    requires_base_url: bool
    requires_api_key: bool
    api_key_optional: bool
    base_url_placeholder: str
    api_key_placeholder: str
    models_source: Literal["static", "remote"]
    description: str


class LlmProvidersListResponse(BaseModel):
    items: list[LlmProviderSpecResponse]
