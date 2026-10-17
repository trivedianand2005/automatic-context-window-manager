"""Fake payment gateway client used by the checkout flow (no network access).

Retry policy: card charges are NEVER retried automatically, because a retry after a
timeout could double-charge a customer. Callers must use idempotency keys instead.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


class PaymentDeclinedError(Exception):
    """The (fake) card issuer declined the charge."""


class PaymentTimeoutError(Exception):
    """The gateway did not answer in time; the charge state is unknown - do not retry."""


@dataclass
class Charge:
    charge_id: str
    amount_cents: int
    currency: str
    idempotency_key: str
    status: str = "succeeded"


@dataclass
class FakePaymentGateway:
    """Deterministic in-memory gateway. Card numbers ending in 0002 are declined."""

    charges: dict[str, Charge] = field(default_factory=dict)
    timeout_on_keys: set[str] = field(default_factory=set)

    def charge(self, card_number: str, amount_cents: int, idempotency_key: str,
               currency: str = "USD") -> Charge:
        if idempotency_key in self.charges:
            return self.charges[idempotency_key]  # idempotent replay, not a retry
        if idempotency_key in self.timeout_on_keys:
            raise PaymentTimeoutError("gateway timeout; check charge status before retrying")
        if card_number.endswith("0002"):
            raise PaymentDeclinedError("card declined")
        charge_id = hashlib.sha256(idempotency_key.encode()).hexdigest()[:12]
        charge = Charge(charge_id, amount_cents, currency, idempotency_key)
        self.charges[idempotency_key] = charge
        return charge

    def refund(self, idempotency_key: str) -> Charge:
        charge = self.charges[idempotency_key]
        charge.status = "refunded"
        return charge

    def charge_status(self, idempotency_key: str) -> str:
        charge = self.charges.get(idempotency_key)
        return charge.status if charge else "unknown"
