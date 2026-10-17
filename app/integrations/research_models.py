"""Shared models for documentation-research providers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchFinding(BaseModel):
    title: str
    url: str
    snippet: str
    source: str


class ResearchResult(BaseModel):
    provider: str  # "tinyfish" | "mock" | "none"
    status: str
    query: str = ""
    findings: list[ResearchFinding] = Field(default_factory=list)
    error: str | None = None
