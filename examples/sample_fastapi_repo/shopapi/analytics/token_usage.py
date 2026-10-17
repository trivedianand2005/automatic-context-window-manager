"""Token usage analytics for the partner billing dashboard.

Partners call ShopAPI through an LLM-powered assistant and are billed per token
consumed. This module aggregates token usage records; it is unrelated to user
authentication tokens, sessions or login, even though the vocabulary overlaps.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date


@dataclass
class TokenUsageRecord:
    partner_id: str
    day: date
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class TokenUsageReport:
    partner_id: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    days: dict[date, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens


def aggregate_token_usage(records: list[TokenUsageRecord]) -> dict[str, TokenUsageReport]:
    """Aggregate token usage per partner and per day."""
    reports: dict[str, TokenUsageReport] = {}
    for record in records:
        report = reports.setdefault(record.partner_id, TokenUsageReport(record.partner_id))
        report.total_prompt_tokens += record.prompt_tokens
        report.total_completion_tokens += record.completion_tokens
        report.days[record.day] = report.days.get(record.day, 0) + record.total_tokens
    return reports


def token_cost_cents(tokens: int, cents_per_thousand_tokens: float = 0.2) -> int:
    """Convert a token count into a billable amount in cents (rounded up)."""
    thousands, remainder = divmod(tokens, 1000)
    cost = thousands * cents_per_thousand_tokens
    if remainder:
        cost += cents_per_thousand_tokens
    return int(cost + 0.999)


def top_token_consumers(reports: dict[str, TokenUsageReport], limit: int = 5) -> list[str]:
    """Partners ordered by total tokens consumed (descending)."""
    ranked = sorted(reports.values(), key=lambda r: (-r.total_tokens, r.partner_id))
    return [r.partner_id for r in ranked[:limit]]


def daily_token_series(report: TokenUsageReport) -> list[tuple[date, int]]:
    """Sorted (day, tokens) series for charting token usage."""
    return sorted(report.days.items())


def token_usage_alerts(
    reports: dict[str, TokenUsageReport], daily_token_limit: int = 1_000_000
) -> dict[str, list[date]]:
    """Days on which a partner exceeded the daily token limit."""
    alerts: dict[str, list[date]] = defaultdict(list)
    for partner_id, report in reports.items():
        for day, tokens in sorted(report.days.items()):
            if tokens > daily_token_limit:
                alerts[partner_id].append(day)
    return dict(alerts)


def merge_token_reports(
    first: dict[str, TokenUsageReport], second: dict[str, TokenUsageReport]
) -> dict[str, TokenUsageReport]:
    """Merge two token usage report maps (e.g. from two billing regions)."""
    merged: dict[str, TokenUsageReport] = {}
    for source in (first, second):
        for partner_id, report in source.items():
            target = merged.setdefault(partner_id, TokenUsageReport(partner_id))
            target.total_prompt_tokens += report.total_prompt_tokens
            target.total_completion_tokens += report.total_completion_tokens
            for day, tokens in report.days.items():
                target.days[day] = target.days.get(day, 0) + tokens
    return merged


def format_token_count(tokens: int) -> str:
    """Human-readable token count, e.g. 1.2M tokens."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M tokens"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.1f}k tokens"
    return f"{tokens} tokens"
