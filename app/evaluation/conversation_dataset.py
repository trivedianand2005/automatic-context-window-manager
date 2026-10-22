"""Synthetic long conversation for the conversation-manager benchmark.

A developer plans a book-lending service ("Bluejay") with an assistant over 80 turns.
Eleven facts are planted in the first 21 turns, one of them is superseded at turn 44,
and 11 recall questions about them (the last one checks two facts) are asked between
turns 68 and 80. Everything else
is realistic filler. Generation is deterministic (fixed seed), so every strategy and
every run sees exactly the same conversation.

Filler deliberately contains no digits or fact keywords, so keyword grading can only
succeed when the planted fact itself survived in the context.
"""

from __future__ import annotations

import random

from pydantic import BaseModel

SEED = 7
TOTAL_TURNS = 80


class RecallQuestion(BaseModel):
    id: str
    expected_keywords: list[str]
    fact_turn: int


class Turn(BaseModel):
    turn: int
    user: str
    assistant: str | None = None  # None: the main model answers (recall questions)
    question: RecallQuestion | None = None


SYSTEM_PROMPT = (
    "You are a senior engineering assistant helping a developer plan and build a "
    "book-lending service. Answer concisely and rely on what was said earlier in the "
    "conversation."
)

ACK = "Understood, I'll keep that in mind for the rest of the project."

# turn -> (user message, assistant reply)
PLANTED: dict[int, tuple[str, str]] = {
    1: (
        "Hi! I'm Priya Nair, and I'm leading backend work on a new project with the codename "
        "Bluejay. It is a book-lending service for small community libraries.",
        "Nice to meet you, Priya. A lending service for community libraries is a great scope "
        "for a focused backend. Tell me about the constraints and I'll help you plan it.",
    ),
    3: (
        "Hard constraint: the public beta deadline is November 14, so anything that does not "
        "fit by then gets cut.",
        ACK,
    ),
    5: ("For storage we'll use PostgreSQL 16 running in Docker.", ACK),
    7: (
        "The API service must listen on port 8081 because 8080 is taken by the legacy "
        "catalogue app.",
        ACK,
    ),
    9: ("Our main entry point lives at services/api/main.py, please keep that path stable.", ACK),
    11: ("My team lead is Ravi Menon; he signs off on any schema change.", ACK),
    13: ("Pagination rule: the maximum page size is 50 items per request.", ACK),
    15: ("Access tokens should expire after 15 minutes, refresh tokens after 7 days.", ACK),
    17: ("The staging environment is at staging.bluejay.dev for anyone who needs it.", ACK),
    19: ("Monthly cloud budget is capped at 300 dollars, so keep the infrastructure lean.", ACK),
    21: ("I prefer pytest over unittest, and please give me type-hinted code.", ACK),
    44: (
        "Change of plan: we're switching from PostgreSQL to SQLite for the beta to keep "
        "operations simple.",
        "That makes sense for a beta. I'll assume SQLite from now on and keep the data access "
        "layer thin so a later migration stays easy.",
    ),
}

# turn -> (question, expected keywords, turn the fact was planted)
QUESTIONS: dict[int, tuple[str, list[str], int]] = {
    68: (
        "Quick check before I write the README: what is the project codename again?",
        ["bluejay"],
        1,
    ),
    69: ("What is our public beta deadline?", ["november 14"], 3),
    71: ("Which database are we using for the beta now?", ["sqlite"], 44),
    72: ("Which port does the API service listen on?", ["8081"], 7),
    73: ("What is the path of the main entry point file?", ["services/api/main.py"], 9),
    74: ("Who has to sign off on schema changes?", ["ravi"], 11),
    76: ("What is the largest page size a client may request?", ["50"], 13),
    77: ("How long do access tokens stay valid?", ["15 minutes"], 15),
    78: ("What is the staging URL?", ["staging.bluejay.dev"], 17),
    79: ("How much can we spend on cloud each month?", ["300"], 19),
    80: ("Which test framework do I like to use, and what's my name?", ["pytest", "priya"], 21),
}
# Q80 checks two facts; it is graded as one question needing both.

TOPICS = [
    "the loan renewal flow",
    "overdue reminder emails",
    "the catalogue search endpoint",
    "member sign-up validation",
    "the barcode scanning screen",
    "error handling in the reservations module",
    "the structured logging format",
    "the admin dashboard filters",
    "importing existing catalogues from spreadsheets",
    "rate limiting for public endpoints",
    "accessibility of the borrower portal",
    "the hold queue ordering",
    "branch opening hours",
    "fines and fee waivers",
    "the notification preferences page",
    "librarian roles and permissions",
    "book condition tracking",
    "the returns desk workflow",
    "inter-branch transfers",
    "the public catalogue page",
]

USER_TEMPLATES = [
    "Can you help me think through {t}? I'm not sure how much detail we need for the beta.",
    "Let's look at {t} next. What edge cases should we cover?",
    "I reviewed {t} with the team and they had a few concerns about complexity.",
    "How would you structure the code for {t} so it stays easy to test?",
    "Any quick wins for {t} before the demo?",
    "What would a minimal but solid version of {t} look like?",
    "I'm worried {t} will turn into a rabbit hole. How do we keep it small?",
]

ADVICE = [
    "For {t}, start with the simplest version that covers the main path and grow from there.",
    "Keep the business rules in a small service layer so the HTTP handlers stay thin.",
    "Write a couple of focused tests around the tricky cases first, then fill in the rest.",
    "Log enough context to debug failures without recording personal data about borrowers.",
    "If the requirements are still moving, put the new behaviour behind a feature flag.",
    "Validate inputs at the edge and return clear, consistent error messages.",
    "Write the decision down in the project notes so the rest of the team can find it later.",
    "Avoid optimising early here; measure first and only then tune the slow parts.",
    "Model the states explicitly, because implicit status flags tend to drift over time.",
    "Ask a librarian to walk through the flow once, since they will spot awkward steps quickly.",
    "Keep the database access behind a small repository class to make tests simpler.",
    "Return predictable shapes from the API so the frontend does not need special cases.",
    "Think about what happens when two librarians edit the same record at once.",
    "Make the happy path fast and the failure path obvious in the interface.",
]


def build_dataset(seed: int = SEED) -> list[Turn]:
    rng = random.Random(seed)
    turns: list[Turn] = []
    for n in range(1, TOTAL_TURNS + 1):
        if n in PLANTED:
            user, assistant = PLANTED[n]
            turns.append(Turn(turn=n, user=user, assistant=assistant))
        elif n in QUESTIONS:
            text, keywords, fact_turn = QUESTIONS[n]
            q = RecallQuestion(id=f"q{n}", expected_keywords=keywords, fact_turn=fact_turn)
            turns.append(Turn(turn=n, user=text, question=q))
        else:
            topic = rng.choice(TOPICS)
            user = rng.choice(USER_TEMPLATES).format(t=topic)
            advice = rng.sample(ADVICE, k=rng.randint(4, 6))
            assistant = " ".join(a.format(t=topic) for a in advice)
            turns.append(Turn(turn=n, user=user, assistant=assistant))
    return turns
