from datetime import date

from shopapi.analytics.token_usage import (
    TokenUsageRecord,
    aggregate_token_usage,
    format_token_count,
    token_cost_cents,
)


def test_aggregate_token_usage():
    records = [
        TokenUsageRecord("p1", date(2024, 1, 1), 100, 50),
        TokenUsageRecord("p1", date(2024, 1, 1), 10, 5),
    ]
    report = aggregate_token_usage(records)["p1"]
    assert report.total_tokens == 165


def test_token_cost_and_format():
    assert token_cost_cents(1500) == 1
    assert format_token_count(1_500_000) == "1.5M tokens"
