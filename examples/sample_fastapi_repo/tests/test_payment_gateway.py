import pytest

from shopapi.services.payment_gateway import (
    FakePaymentGateway,
    PaymentDeclinedError,
    PaymentTimeoutError,
)


def test_charge_is_idempotent():
    gateway = FakePaymentGateway()
    first = gateway.charge("4242424242424242", 1000, "key-1")
    assert gateway.charge("4242424242424242", 1000, "key-1") is first


def test_declined_card():
    with pytest.raises(PaymentDeclinedError):
        FakePaymentGateway().charge("4000000000000002", 1000, "key-2")


def test_timeout_is_not_retried():
    gateway = FakePaymentGateway(timeout_on_keys={"key-3"})
    with pytest.raises(PaymentTimeoutError):
        gateway.charge("4242424242424242", 1000, "key-3")
    assert gateway.charge_status("key-3") == "unknown"
