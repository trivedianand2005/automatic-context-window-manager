"""REST endpoints. All business logic lives in ``ACWMService``."""

from __future__ import annotations

import asyncio
import json
from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, Query, Request

from app import __version__
from app.api.schemas import (
    BenchmarkRunRequest,
    BuildRequest,
    CompareRequest,
    ErrorResponse,
    ExportRequest,
    ExportResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    RepositoryResponse,
)
from app.context.context_exporter import EXTENSIONS, MIME_TYPES
from app.context.package_models import ContextPackage
from app.core.config import BENCHMARK_FILE
from app.core.exceptions import ACWMError
from app.graph.dependency_graph import serialize_graph
from app.services.acwm_service import ACWMService, BenchmarkReport, ComparisonResult
from app.services.options import BuildOptions

router = APIRouter()
ERRORS = {
    400: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
}


class ProcessingTimeout(ACWMError):
    code = "processing_timeout"
    http_status = 504


def get_service(request: Request) -> ACWMService:
    return request.app.state.service


async def run_blocking(service: ACWMService, func, *args, **kwargs):
    """Run CPU/IO-bound service work off the event loop with a timeout.

    Note: on timeout the worker thread is not killed; it finishes in the background.
    """
    try:
        return await asyncio.wait_for(
            to_thread.run_sync(partial(func, *args, **kwargs)),
            timeout=service.settings.api_timeout_seconds,
        )
    except TimeoutError as exc:
        raise ProcessingTimeout(
            f"Processing exceeded {service.settings.api_timeout_seconds}s."
        ) from exc


def _options(req: BuildRequest) -> BuildOptions:
    return BuildOptions(**req.model_dump(exclude={"repository_id", "relevant_paths", "k"}))


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(service: ACWMService = Depends(get_service)) -> HealthResponse:
    return HealthResponse(version=__version__, providers=service.provider_statuses())


@router.post(
    "/repositories/index", response_model=IndexResponse, responses=ERRORS, tags=["repositories"]
)
async def index_repository(body: IndexRequest, service: ACWMService = Depends(get_service)):
    repo = await run_blocking(service, service.index_repository, body.path)
    return IndexResponse(repository=service.repository_summary(repo), report=repo.report)


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositoryResponse,
    responses=ERRORS,
    tags=["repositories"],
)
def get_repository(
    repository_id: str,
    include_graph: bool = Query(False),
    include_symbols: bool = Query(False),
    service: ACWMService = Depends(get_service),
) -> RepositoryResponse:
    repo = service.store.get(repository_id)
    return RepositoryResponse(
        repository=service.repository_summary(repo),
        report=repo.report,
        symbols={p: [s.qualname for s in m.symbols] for p, m in repo.modules.items()}
        if include_symbols
        else None,
        graph=serialize_graph(repo.graph) if include_graph else None,
    )


@router.post("/context/build", response_model=ContextPackage, responses=ERRORS, tags=["context"])
async def build_context(body: BuildRequest, service: ACWMService = Depends(get_service)):
    return await run_blocking(service, service.build_context, body.repository_id, _options(body))


@router.post(
    "/context/compare", response_model=ComparisonResult, responses=ERRORS, tags=["context"]
)
async def compare(body: CompareRequest, service: ACWMService = Depends(get_service)):
    return await run_blocking(
        service, service.compare, body.repository_id, _options(body), body.relevant_paths, body.k
    )


@router.post("/context/export", response_model=ExportResponse, responses=ERRORS, tags=["context"])
async def export_context(body: ExportRequest, service: ACWMService = Depends(get_service)):
    package = body.package
    if package is None:
        package = await run_blocking(
            service, service.build_context, body.build.repository_id, _options(body.build)
        )
    content = service.export(package, body.format)
    return ExportResponse(
        format=body.format,
        filename=f"acwm_context.{EXTENSIONS[body.format]}",
        mime_type=MIME_TYPES[body.format],
        content=content,
    )


@router.get("/benchmarks", tags=["benchmarks"])
def list_benchmarks(service: ACWMService = Depends(get_service)) -> dict:
    data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    return {
        "repository": data["repository"],
        "tasks": data["tasks"],
        "labeling_notes": data.get("labeling_notes", ""),
    }


@router.post(
    "/benchmarks/run", response_model=BenchmarkReport, responses=ERRORS, tags=["benchmarks"]
)
async def run_benchmarks(
    body: BenchmarkRunRequest | None = None, service: ACWMService = Depends(get_service)
):
    body = body or BenchmarkRunRequest()
    return await run_blocking(service, service.run_benchmarks, body.token_budget, body.k)
