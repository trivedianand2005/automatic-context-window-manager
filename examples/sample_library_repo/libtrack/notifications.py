"""Member e-mails (rendered only; nothing is actually sent)."""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

from libtrack.config import Settings, get_settings

WELCOME = Template("Hello $name,\n\nWelcome to the library! Your member id is $member_id.\n")
RETURN_RECEIPT = Template("Hello $name,\n\nThanks for returning \"$title\".$fine_line\n")


@dataclass(frozen=True)
class Email:
    sender: str
    to: str
    subject: str
    body: str


class Notifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.outbox: list[Email] = []

    def _send(self, to: str, subject: str, body: str) -> Email:
        email = Email(self.settings.email_sender, to, subject, body)
        self.outbox.append(email)
        return email

    def welcome(self, name: str, email: str, member_id: str) -> Email:
        return self._send(email, "Welcome", WELCOME.substitute(name=name, member_id=member_id))

    def return_receipt(self, name: str, email: str, title: str, fine_cents: int) -> Email:
        fine_line = f" A late fee of ${fine_cents / 100:.2f} was charged." if fine_cents else ""
        body = RETURN_RECEIPT.substitute(name=name, title=title, fine_line=fine_line)
        return self._send(email, "Return receipt", body)
