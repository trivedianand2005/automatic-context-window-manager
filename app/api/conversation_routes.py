"""Conversation-manager endpoints: status and the three-strategy benchmark.

Dry runs use mock models and are cached (the result is deterministic). Live runs call the
configured models, cost real money, and are only allowed when the server sets
``ACWM_CONVERSATION_LIVE=true``; one live run at a time.
"""

from __future__ import annotations

import asyncio
import threading
from functools import lru_cache, partial

from anyio import to_thread
from fastapi import APIRouter, Depends

from app.api.deps import get_public_service, get_service
from app.api.routes import ERRORS, ProcessingTimeout
from app.api.schemas import (
    ConversationBenchmarkRequest,
    ConversationModelStatus,
    ConversationStatus,
    ErrorResponse,
)
from app.context.token_counter import get_token_counter
from app.conversation.backends import backend_status
from app.conversation.config import get_conversation_config
from app.core.exceptions import NotConfiguredError, RateLimitedError
from app.evaluation.conversation_benchmark import run_benchmark
from app.evaluation.conversation_dataset import build_dataset
from app.services.acwm_service import ACWMService

router = APIRouter(prefix="/conversation", tags=["conversation"])
LIVE_TIMEOUT_SECONDS = 600
_live_lock = threading.Lock()


def _model_status(role: str) -> ConversationModelStatus:
    cfg = get_conversation_config()
    settings = getattr(cfg, role)
    real, status = backend_status(role, cfg)
    model = settings.model
    if settings.backend == "ollama":
        model = cfg.ollama.manager_model if role == "manager" else cfg.ollama.main_model
    return ConversationModelStatus(
        backend=settings.backend, model=model, real_model=real, status=status
    )


@router.get("/status", response_model=ConversationStatus)
def conversation_status(service: ACWMService = Depends(get_public_service)) -> ConversationStatus:
    cfg = get_conversation_config()
    main = _model_status("main_model")
    return ConversationStatus(
        manager=_model_status("manager"),
        main_model=main,
        live_runs_enabled=service.settings.conversation_live_enabled,
        live_available=service.settings.conversation_live_enabled and main.real_model,
        default_budget_tokens=cfg.benchmark.budget_tokens,
        context=cfg.context.model_dump(),
    )


@lru_cache(maxsize=8)
def _dry_run(budget: int, encoding: str) -> dict:
    cfg = get_conversation_config()
    return run_benchmark(cfg, build_dataset(), get_token_counter(encoding), budget, dry_run=True)


def _live_run(budget: int, encoding: str) -> dict:
    if not _live_lock.acquire(blocking=False):
        raise RateLimitedError("A live conversation benchmark is already running; try again soon.")
    try:
        cfg = get_conversation_config()
        return run_benchmark(
            cfg,
            build_dataset(),
            get_token_counter(encoding),
            budget,
            dry_run=False,
            judge_mode=cfg.benchmark.judge,
        )
    finally:
        _live_lock.release()


@router.post(
    "/benchmark",
    responses={**ERRORS, 429: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
    summary="Run the conversation benchmark (full vs truncation vs ACWM)",
)
async def conversation_benchmark(
    body: ConversationBenchmarkRequest, service: ACWMService = Depends(get_service)
) -> dict:
    """Returns ``summary`` (one row per strategy), ``per_turn`` metrics and ``answers``."""
    cfg = get_conversation_config()
    budget = body.budget_tokens or cfg.benchmark.budget_tokens
    encoding = service.settings.tokenizer_encoding
    if body.mode == "dry-run":
        func, timeout = partial(_dry_run, budget, encoding), service.settings.api_timeout_seconds
    else:
        if not service.settings.conversation_live_enabled:
            raise NotConfiguredError(
                "Live conversation benchmarks are disabled on this server "
                "(set ACWM_CONVERSATION_LIVE=true). Use dry-run mode."
            )
        if not _model_status("main_model").real_model:
            raise NotConfiguredError(
                "The main model is not available on this server (add ANTHROPIC_API_KEY)."
            )
        func, timeout = partial(_live_run, budget, encoding), LIVE_TIMEOUT_SECONDS
    try:
        return await asyncio.wait_for(to_thread.run_sync(func), timeout=timeout)
    except TimeoutError as exc:
        raise ProcessingTimeout(f"Conversation benchmark exceeded {timeout:.0f}s.") from exc
