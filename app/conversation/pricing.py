"""Cost estimates from the per-model prices in config.yaml (USD per 1M tokens)."""

from __future__ import annotations

from app.conversation.config import Price
from app.core.logging_config import get_logger

log = get_logger("conversation.pricing")


class PriceTable:
    def __init__(self, prices: dict[str, Price]) -> None:
        self.prices = prices
        self._warned: set[str] = set()

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = self.prices.get(model)
        if price is None:
            if model not in self._warned:
                log.warning("No price configured for model '%s'; counting its cost as 0.", model)
                self._warned.add(model)
            return 0.0
        return (input_tokens * price.input + output_tokens * price.output) / 1_000_000
