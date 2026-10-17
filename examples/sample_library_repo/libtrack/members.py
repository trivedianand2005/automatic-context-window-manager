"""Member registry."""

from __future__ import annotations

import re

from libtrack.models import Member

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


class MemberRegistry:
    def __init__(self) -> None:
        self.members: dict[str, Member] = {}

    def register(self, member_id: str, name: str, email: str) -> Member:
        if not EMAIL.match(email):
            raise ValueError(f"invalid email address: {email}")
        if member_id in self.members:
            raise ValueError(f"member {member_id} already exists")
        member = Member(member_id, name, email)
        self.members[member_id] = member
        return member

    def get(self, member_id: str) -> Member:
        try:
            return self.members[member_id]
        except KeyError:
            raise KeyError(f"unknown member {member_id}") from None

    def suspend(self, member_id: str) -> None:
        self.get(member_id).suspended = True
