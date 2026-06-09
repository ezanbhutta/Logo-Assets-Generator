"""FastAPI app (§2). Stateless: each job lives in a temp dir, cleaned on
completion. Endpoints: POST /ingest, POST /generate, GET /health."""
from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .config import safe_brand
from .ingest import IngestError
from .models import (ArtboardInfo, GenerateRequestBody, HealthResponse,
                     IngestResponse)
from .pipeline import (GenerateRequest, ManualFlag, run_generate, run_ingest)

WORK_ROOT = Path(os.environ.get("LOGO_WORK_ROOT", "/tmp/logo_jobs"))
WORK_ROOT.mkdir(parents=True, exist_ok=True)
JOB_TTL_SECONDS = int(os.environ.get("LOGO_JOB_TTL", "3600"))

app = FastAPI(title="Logo Package Engine", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # headless internal tool; tighten for prod
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sweep_old_jobs() -> None:
    """Best-effort cleanup of abandoned job dirs (no persistence — §2)."""
    cutoff = time.time() - JOB_TTL_SECONDS
    for d in WORK_ROOT.glob("*"):
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _job_dir(job_id: str) -> Path:
    # job_id is a server-minted uuid; reject anything else (path-traversal safe).
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid job id")
    d = WORK_ROOT / job_id
    if not d.is_dir():
        raise HTTPException(status_code=404, detail="job not found or expired")
    return d


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", toolchain={
        "pdf2svg": bool(shutil.which("pdf2svg")),
        "pdftocairo": bool(shutil.which("pdftocairo")),
        "rsvg_convert": bool(shutil.which("rsvg-convert")),
    })


@app.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint(
    ai: UploadFile = File(...),
    eps: UploadFile | None = File(None),
    brand: str | None = Form(None),
) -> IngestResponse:
    _sweep_old_jobs()
    job_id = str(uuid.uuid4())
    job = WORK_ROOT / job_id
    job.mkdir(parents=True, exist_ok=True)

    ai_path = job / "source.ai"
    ai_path.write_bytes(await ai.read())
    if eps is not None:
        (job / "source.eps").write_bytes(await eps.read())

    # Brand defaults to the .ai filename without extension (§3.1).
    default_brand = Path(ai.filename or "Logo").stem
    brand = (brand or default_brand or "Logo").strip()

    try:
        summary = run_ingest(ai_path, job)
    except IngestError as e:
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(e))

    (job / "brand.txt").write_text(brand, encoding="utf-8")

    return IngestResponse(
        job_id=job_id,
        brand=brand,
        converter=summary.converter,
        artboard_count=summary.artboard_count,
        primary_index=summary.primary_index,
        artboards=[ArtboardInfo(**{k: v for k, v in vars(b).items()
                                   if k in ArtboardInfo.model_fields})
                   for b in summary.artboards],
    )


@app.post("/generate")
def generate_endpoint(body: GenerateRequestBody):
    job = _job_dir(body.job_id)
    # Use the CSR's chosen artboard as the primary logo.
    board = job / f"working_{body.artboard}.svg"
    if not board.is_file():
        raise HTTPException(status_code=400, detail="invalid artboard")
    working_svg = board.read_text(encoding="utf-8")
    ai_path = job / "source.ai"
    eps_path = job / "source.eps"

    box = tuple(body.selection_box) if body.selection_box else None
    logo_box = tuple(body.logo_box) if body.logo_box else None
    req = GenerateRequest(
        brand=body.brand.strip() or "Logo",
        working_svg=working_svg,
        selection_box=box,
        logo_box=logo_box,
        removed_colors=body.removed_colors,
        brand_a=body.brand_a,
        brand_b=body.brand_b,
        ai_path=ai_path if ai_path.exists() else None,
        eps_path=eps_path if eps_path.exists() else None,
    )

    try:
        result = run_generate(req, job)
    except ManualFlag as e:
        # Out-of-scope: refuse cleanly, leave no partial package (§8/6, §9).
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(status_code=422, detail={
            "error": "manual_required", "reasons": e.reasons})
    except HTTPException:
        raise
    except Exception:
        # Unexpected failure: log the traceback (visible in server logs) and
        # return a clear message instead of a bare 500.
        logging.getLogger("uvicorn.error").exception(
            "generate failed for job %s artboard %s", body.job_id, body.artboard)
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(status_code=500, detail={
            "error": "generate_failed",
            "message": "Generation hit an unexpected error on this logo. "
                       "It has been logged — please share the .ai so it can be fixed."})

    filename = f"{safe_brand(req.brand)} Files.zip"
    # Delete the whole job dir once the zip has been streamed (stateless — §2).
    cleanup = BackgroundTask(shutil.rmtree, job, ignore_errors=True)
    return FileResponse(result.zip_path, media_type="application/zip",
                        filename=filename, background=cleanup)


# Serve the built frontend if present (single-origin prod deploy).
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="ui")
