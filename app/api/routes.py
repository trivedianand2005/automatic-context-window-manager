"""REST endpoints. All business logic lives in ``ACWMService``."""

from __future__ import annotations

import asyncio
import json
from functools import partial

from anyio import to_thread
from fastapi import APIRouter, Depends, Query

from app import __version__
from app.api.deps import SESSION_HEADER, get_public_service, get_service  # noqa: F401
from app.api.schemas import (
    BenchmarkRunRequest,
    BuildRequest,
    CompareRequest,
    ConfigResponse,
    ErrorResponse,
    ExampleRepository,
    ExportRequest,
    ExportResponse,
    FileInfo,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    RepositoryResponse,
    RunInfo,
    SymbolInfo,
)
from app.context.context_exporter import EXTENSIONS, MIME_TYPES
from app.context.package_models import ContextPackage
from app.core.config import BENCHMARK_FILE, PROJECT_ROOT, SAMPLE_REPO_PATH
from app.core.exceptions import ACWMError
from app.graph.dependency_graph import serialize_graph
from app.services.acwm_service import ACWMService, BenchmarkReport, ComparisonResult
from app.services.options import MODE_LABELS, BuildOptions

router = APIRouter()
ERRORS = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    504: {"model": ErrorResponse},
}


class ProcessingTimeout(ACWMError):
    code = "processing_timeout"
    http_status = 504


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
def health(service: ACWMService = Depends(get_public_service)) -> HealthResponse:
    return HealthResponse(version=__version__, providers=service.provider_statuses())


def _example_repositories() -> list[ExampleRepository]:
    """Bundled example repositories under ``examples/`` (always inside the allowed roots)."""
    out = []
    for d in sorted((PROJECT_ROOT / "examples").iterdir()):
        readme = d / "README.md"
        if not d.is_dir() or not readme.is_file():
            continue
        lines = [ln.strip() for ln in readme.read_text(encoding="utf-8").splitlines()]
        title = next((ln.lstrip("# ") for ln in lines if ln.startswith("#")), d.name)
        body = next((ln for ln in lines if ln and not ln.startswith("#")), "")
        out.append(ExampleRepository(name=title, path=str(d), description=body))
    return out


@router.get("/config", response_model=ConfigResponse, tags=["system"])
def get_config(service: ACWMService = Depends(get_public_service)) -> ConfigResponse:
    s = service.settings
    return ConfigResponse(
        sample_repository_path=str(SAMPLE_REPO_PATH),
        example_repositories=_example_repositories(),
        budget=s.budget.model_dump(),
        weights=s.weights.model_dump(),
        expansion_depth=s.expansion_depth,
        modes=MODE_LABELS,
        tokenizer_encoding=s.tokenizer_encoding,
        providers=service.provider_statuses(),
    )


@router.get("/runs", response_model=list[RunInfo], tags=["system"])
def recent_runs(
    limit: int = Query(10, ge=1, le=50), service: ACWMService = Depends(get_service)
) -> list[RunInfo]:
    return [RunInfo(**r.model_dump()) for r in service.sessions.recent(limit)]


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
    include_files: bool = Query(False),
    service: ACWMService = Depends(get_service),
) -> RepositoryResponse:
    repo = service.store.get(repository_id)
    files = None
    if include_files:
        files = [
            FileInfo(
                path=f.path,
                file_type=f.file_type,
                language=f.language,
                tokens=f.tokens,
                line_count=f.line_count,
                symbol_count=len(repo.modules[f.path].symbols) if f.path in repo.modules else 0,
                parse_error=repo.modules[f.path].parse_error if f.path in repo.modules else None,
            )
            for f in repo.files.values()
        ]
    symbols = None
    if include_symbols:
        symbols = {
            p: [
                SymbolInfo(
                    id=s.id,
                    qualname=s.qualname,
                    kind=s.kind,
                    signature=s.signature,
                    start_line=s.start_line,
                    end_line=s.end_line,
                    docstring=s.docstring,
                )
                for s in m.symbols
            ]
            for p, m in repo.modules.items()
        }
    return RepositoryResponse(
        repository=service.repository_summary(repo),
        report=repo.report,
        files=files,
        symbols=symbols,
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
def list_benchmarks(service: ACWMService = Depends(get_public_service)) -> dict:
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
