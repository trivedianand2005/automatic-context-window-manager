"""Customer notification e-mails (rendered only; delivery is out of scope for the demo).

Templates include login alerts and password reset e-mails, but this module does not
perform authentication: it only formats messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

LOGIN_ALERT = Template(
    "Hello $name,\n\nWe noticed a new login to your ShopAPI account from $location.\n"
    "If this was not you, reset your password immediately.\n"
)
PASSWORD_RESET = Template(
    "Hello $name,\n\nUse the following one-time link to reset your password: $link\n"
    "The link expires in $minutes minutes.\n"
)
ORDER_CONFIRMATION = Template(
    "Hello $name,\n\nThank you for your order #$order_id ($quantity x $product).\n"
)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class NotificationService:
    def __init__(self, sender: str = "no-reply@shopapi.example") -> None:
        self.sender = sender
        self.outbox: list[EmailMessage] = []

    def _queue(self, to: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage(to=to, subject=subject, body=body)
        self.outbox.append(message)
        return message

    def login_alert(self, email: str, name: str, location: str) -> EmailMessage:
        """Notify a user about a new login (does not verify credentials)."""
        body = LOGIN_ALERT.substitute(name=name, location=location)
        return self._queue(email, "New login to your account", body)

    def password_reset(self, email: str, name: str, link: str, minutes: int = 15) -> EmailMessage:
        body = PASSWORD_RESET.substitute(name=name, link=link, minutes=minutes)
        return self._queue(email, "Reset your password", body)

    def order_confirmation(self, email: str, name: str, order: dict, product: str) -> EmailMessage:
        body = ORDER_CONFIRMATION.substitute(
            name=name, order_id=order["id"], quantity=order["quantity"], product=product
        )
        return self._queue(email, f"Order #{order['id']} confirmed", body)
