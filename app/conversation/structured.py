"""Parse and validate the manager LLM's JSON output."""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.conversation.models import ManagerOutput


class InvalidManagerOutput(ValueError):
    """The response was not JSON or did not match ``ManagerOutput``."""


def _extract_json(text: str) -> str:
    """Tolerate code fences or stray prose around the object (common with local models)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise InvalidManagerOutput("no JSON object found in the reply")
    return text[start : end + 1]


def parse_manager_output(text: str) -> ManagerOutput:
    try:
        data = json.loads(_extract_json(text))
    except json.JSONDecodeError as exc:
        raise InvalidManagerOutput(f"invalid JSON ({exc.msg} at position {exc.pos})") from exc
    if not isinstance(data, dict):
        raise InvalidManagerOutput("the reply must be a JSON object")
    try:
        return ManagerOutput.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}"
            for err in exc.errors()[:5]
        )
        raise InvalidManagerOutput(f"schema mismatch ({problems})") from exc
