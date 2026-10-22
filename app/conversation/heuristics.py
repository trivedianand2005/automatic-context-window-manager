"""LLM-free compaction: extractive facts, importance scores and a running summary.

Used whenever the manager LLM is disabled, fails, times out or returns invalid JSON,
and as the deterministic "manager" in --dry-run benchmarks (``mock_manager_responder``).
"""

from __future__ import annotations

import json
import re

from app.context.token_counter import TokenCounter
from app.conversation.models import ManagerOutput, Message, MessageScore

SUMMARY_LINE_WORDS = 25
MAX_FACT_CHARS = 220
SHORT_MESSAGE_TOKENS = 12

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_PATH = re.compile(r"\b[\w./-]+\.(?:py|ts|tsx|js|json|ya?ml|md|toml|sql|cfg|ini|env)\b")
_URL = re.compile(r"https?://\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:dev|com|io|org|net|app)\b")
_CUES = re.compile(
    r"\b(my name is|call me|deadline|due (?:on|by)|prefer|always|never|must|decided|"
    r"we(?:'ll| will) use|switch(?:ed|ing)? (?:to|from)|instead of|port|version|budget|"
    r"limit|maximum|max|expire|lead|owner|codename|remember)\b",
    re.IGNORECASE,
)
_SECRET = re.compile(r"\b(password|passwd|api[_ ]?key|secret|token is)\b", re.IGNORECASE)
# Topic keys let a newer fact replace an older one on the same subject.
_TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("name", ("my name is", "call me")),
    ("deadline", ("deadline", "due on", "due by")),
    ("database", ("postgres", "sqlite", "mysql", "mongodb", "database")),
    ("port", (" port ",)),
    ("budget", ("budget",)),
    ("codename", ("codename",)),
    ("team lead", ("team lead", "tech lead")),
]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text.replace("\n", " ")) if s.strip()]


def _topic(sentence: str) -> str | None:
    low = f" {sentence.lower()} "
    for key, needles in _TOPICS:
        if any(n in low for n in needles):
            return key
    return None


def fact_sentences(msg: Message) -> list[str]:
    if msg.role != "user":
        return []
    out = []
    for s in _sentences(msg.content):
        if _SECRET.search(s):
            continue
        if _CUES.search(s) or _PATH.search(s) or _URL.search(s):
            out.append(s[:MAX_FACT_CHARS])
    return out


def extract_facts(messages: list[Message]) -> list[str]:
    facts: list[str] = []
    for msg in messages:
        for s in fact_sentences(msg):
            topic = _topic(s)
            fact = f"{topic}: {s}" if topic else s
            if fact not in facts:
                facts.append(fact)
    return facts


def score_message(msg: Message) -> int:
    score = 2
    if fact_sentences(msg):
        score += 2
    if "```" in msg.content:
        score += 1
    if msg.tokens < SHORT_MESSAGE_TOKENS:
        score -= 1
    return max(1, min(5, score))


def cap_summary(text: str, counter: TokenCounter, max_tokens: int) -> str:
    """Keep the newest summary lines that fit; older lines go first."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    while lines and counter.count("\n".join(lines)) > max_tokens:
        lines.pop(0)
    if not lines and text:
        return counter.truncate(text, max_tokens)
    return "\n".join(lines)


def extractive_summary(
    messages: list[Message], previous: str, counter: TokenCounter, max_tokens: int
) -> str:
    lines = [previous] if previous else []
    for msg in messages:
        first = _sentences(msg.content)[:1]
        if not first:
            continue
        words = first[0].split()
        line = " ".join(words[:SUMMARY_LINE_WORDS]) + (
            " ..." if len(words) > SUMMARY_LINE_WORDS else ""
        )
        lines.append(f"- turn {msg.turn} {msg.role}: {line}")
    return cap_summary("\n".join(lines), counter, max_tokens)


def heuristic_output(
    messages: list[Message], previous_summary: str, counter: TokenCounter, max_summary_tokens: int
) -> ManagerOutput:
    return ManagerOutput(
        summary=extractive_summary(messages, previous_summary, counter, max_summary_tokens),
        pinned_facts=extract_facts(messages),
        message_scores=[
            MessageScore(id=m.id, score=score_message(m), reason="heuristic") for m in messages
        ],
        superseded=[],
    )


_MESSAGE_TAG = re.compile(
    r'<message id="([^"]+)" role="(user|assistant)" turn="(\d+)">\n(.*?)\n</message>', re.DOTALL
)
_PREVIOUS = re.compile(r"<previous_summary>\n(.*?)\n</previous_summary>", re.DOTALL)


def mock_manager_responder(counter: TokenCounter, max_summary_tokens: int):
    """A fake manager LLM for --dry-run: reads the compaction prompt, answers with heuristics."""

    def respond(_system: str, messages: list[dict]) -> str:
        prompt = str(messages[-1]["content"])
        msgs = [
            Message(
                id=m[0],
                role=m[1],
                turn=int(m[2]),
                content=m[3],
                timestamp=0.0,
                tokens=counter.count(m[3]),
            )
            for m in _MESSAGE_TAG.findall(prompt)
        ]
        prev = _PREVIOUS.search(prompt)
        previous = prev.group(1).strip() if prev else ""
        if previous == "(none)":
            previous = ""
        out = heuristic_output(msgs, previous, counter, max_summary_tokens)
        return json.dumps(out.model_dump())

    return respond
