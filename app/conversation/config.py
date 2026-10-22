"""Conversation manager settings, loaded from ``config.yaml`` (or ``$ACWM_CONFIG``).

Model names, backends, thresholds and prices all come from that one file. Secrets
(``ANTHROPIC_API_KEY``) are read from the environment by the Anthropic SDK and never
appear here. A missing file means the defaults below.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

from app.core.config import PROJECT_ROOT

Backend = Literal["anthropic", "ollama", "mock", "none"]


class ModelSettings(BaseModel):
    backend: Backend = "anthropic"
    model: str = "claude-opus-5-5"
    max_tokens: int = Field(1024, ge=16, le=64_000)
    timeout_seconds: float = Field(60.0, gt=0, le=600)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "low"
    refusal_fallbacks: bool = False
    json_retries: int = Field(1, ge=0, le=3)


class OllamaSettings(BaseModel):
    host: str = "http://localhost:11434"
    manager_model: str = "qwen2.5:7b"
    main_model: str = "llama3.2"
    temperature: float = Field(0.1, ge=0, le=2)


class ContextSettings(BaseModel):
    total_tokens: int = Field(8000, ge=256)
    compact_threshold: float = Field(0.75, gt=0, le=1)
    compact_target: float = Field(0.50, gt=0, le=1)
    keep_recent_turns: int = Field(4, ge=0)
    cooldown_turns: int = Field(3, ge=0)
    verbatim_min_score: int = Field(4, ge=1, le=6)
    max_summary_tokens: int = Field(600, ge=32)
    max_compaction_input_tokens: int = Field(6000, ge=256)
    per_message_overhead_tokens: int = Field(4, ge=0)

    @model_validator(mode="after")
    def _target_below_threshold(self) -> ContextSettings:
        if self.compact_target >= self.compact_threshold:
            raise ValueError("context.compact_target must be below context.compact_threshold")
        return self


class Price(BaseModel):
    input: float = Field(0.0, ge=0)
    output: float = Field(0.0, ge=0)


class BenchmarkSettings(BaseModel):
    budget_tokens: int = Field(4000, ge=256)
    judge: Literal["keyword", "llm"] = "keyword"
    output_dir: str = "demo_output/conversation"


class ConversationConfig(BaseModel):
    main_model: ModelSettings = Field(default_factory=ModelSettings)
    manager: ModelSettings = Field(
        default_factory=lambda: ModelSettings(
            model="claude-haiku-5-5", max_tokens=2048, timeout_seconds=20
        )
    )
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    pricing: dict[str, Price] = Field(
        default_factory=lambda: {
            "claude-opus-5-5": Price(input=4.0, output=20.0),
            "claude-haiku-5-5": Price(input=0.10, output=0.50),
        }
    )
    benchmark: BenchmarkSettings = Field(default_factory=BenchmarkSettings)


def config_path() -> Path:
    raw = os.getenv("ACWM_CONFIG")
    return Path(raw).expanduser().resolve() if raw else PROJECT_ROOT / "config.yaml"


def load_conversation_config(path: Path | None = None) -> ConversationConfig:
    """Read the YAML config. Also loads ``.env`` so the SDK can find ANTHROPIC_API_KEY."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    path = path or config_path()
    if not path.is_file():
        return ConversationConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ConversationConfig(**data)


@lru_cache(maxsize=1)
def get_conversation_config() -> ConversationConfig:
    return load_conversation_config()
