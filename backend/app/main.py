"""FastAPI app (§2). Stateless: each job lives in a temp dir, cleaned on
completion. Endpoints: POST /ingest, POST /generate, GET /health."""
from __future__ import annotations

import json
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

from . import selection, vision
from .config import safe_brand
from .ingest import IngestError
from .models import (ArtboardInfo, GenerateRequestBody, HealthResponse,
                     IngestResponse, SegmentRequestBody, SegmentResponse)
from .pipeline import (GenerateRequest, ManualFlag, run_generate,
                       run_ingest_multi)
from .svg_model import WorkingSVG

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
    files: list[UploadFile] | None = File(None),
    ai: UploadFile | None = File(None),       # back-compat single-file field
    eps: UploadFile | None = File(None),
    brand: str | None = Form(None),
) -> IngestResponse:
    """Ingest one or MORE uploaded files. Every artboard of every file is shown on
    the next page so the CSR can tag the Logo + Icon (possibly on different
    artboards/files). `.eps` files are kept as masters, paired to their `.ai` by
    name; `.ai`/`.pdf`/`.svg` files are ingested for artboards."""
    _sweep_old_jobs()
    uploads = list(files or [])
    if ai is not None:                        # back-compat: single ai (+ eps)
        uploads.append(ai)
        if eps is not None:
            uploads.append(eps)
    if not uploads:
        raise HTTPException(status_code=422, detail="No files uploaded.")

    job_id = str(uuid.uuid4())
    job = WORK_ROOT / job_id
    job.mkdir(parents=True, exist_ok=True)

    # Save every upload; split into ingestable sources (.ai/.pdf/.svg) and the
    # .eps masters (paired to their source by file-stem).
    sources: list[tuple[Path, str]] = []      # (path, name) to ingest
    eps_by_stem: dict[str, Path] = {}
    for i, uf in enumerate(uploads):
        ext = Path(uf.filename or "").suffix.lower() or ".ai"
        stem = Path(uf.filename or f"file{i}").stem
        p = job / f"upload_{i}{ext}"
        p.write_bytes(await uf.read())
        if ext == ".eps":
            eps_by_stem[stem] = p
        else:
            sources.append((p, stem))
    if not sources:
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(status_code=422, detail="No .ai/.pdf/.svg file to convert.")

    brand = (brand or sources[0][1] or "Logo").strip()

    try:
        summary = run_ingest_multi(sources, job)
    except IngestError as e:
        shutil.rmtree(job, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(e))

    # Persist the resolution map: each file's .ai/.eps path, and each global
    # artboard's (file, page) — so /generate carves masters from the right source.
    src_files = [{"ai": str(p), "eps": str(eps_by_stem.get(name)) if name in eps_by_stem else None,
                  "name": name} for p, name in sources]
    (job / "sources.json").write_text(json.dumps({
        "files": src_files,
        "artboards": {str(b.index): {"file": b.file_index, "page": b.page}
                      for b in summary.artboards},
    }), encoding="utf-8")
    (job / "brand.txt").write_text(brand, encoding="utf-8")

    return IngestResponse(
        job_id=job_id, brand=brand, converter=summary.converter,
        artboard_count=summary.artboard_count, primary_index=summary.primary_index,
        files=summary.files,
        artboards=[ArtboardInfo(**{k: v for k, v in vars(b).items()
                                   if k in ArtboardInfo.model_fields})
                   for b in summary.artboards],
    )


@app.post("/segment", response_model=SegmentResponse)
def segment_endpoint(body: SegmentRequestBody) -> SegmentResponse:
    """Propose editable logo/icon boxes for the chosen artboard. Asks Claude to
    read the artboard (vision) when an API key is configured; otherwise — or on
    any AI failure — falls back to the geometric ``auto_segment``. A suggestion
    only: the CSR reviews and adjusts before anything ships."""
    job = _job_dir(body.job_id)
    board = job / f"working_{body.artboard}.svg"
    if not board.is_file():
        raise HTTPException(status_code=400, detail="invalid artboard")
    working_svg = board.read_text(encoding="utf-8")
    model = WorkingSVG.from_string(working_svg)
    vb = model.viewbox or (0.0, 0.0, 0.0, 0.0)

    sugg, source = None, "none"
    try:
        sugg = vision.ai_segment(working_svg, vb)
        if sugg is not None:
            source = "ai"
    except Exception:
        logging.getLogger("uvicorn.error").exception(
            "segment: AI path failed for job %s", body.job_id)
    if sugg is None:                       # no key, AI failure, or nothing found
        sugg = selection.auto_segment(model)
        source = "geometry" if sugg is not None else "none"

    if sugg is None:
        return SegmentResponse(note="Nothing to auto-detect — draw the boxes by hand.")
    d = sugg.as_dict()
    return SegmentResponse(logo_box=d["logo_box"], icon_box=d["icon_box"],
                           note=d["note"], source=source)


def _load_sources(job: Path) -> tuple[dict, list]:
    """Read the ingest resolution map written by /ingest. Returns
    (artboards{idx->{file,page}}, files[{ai,eps,name}])."""
    sp = job / "sources.json"
    if not sp.is_file():
        return {}, []
    data = json.loads(sp.read_text(encoding="utf-8"))
    return data.get("artboards", {}), data.get("files", [])


@app.post("/generate")
def generate_endpoint(body: GenerateRequestBody):
    job = _job_dir(body.job_id)
    art_map, files = _load_sources(job)

    # Resolve the LOGO artboard (back-compat: `artboard` aliases `logo_artboard`).
    logo_ab = body.artboard if body.artboard is not None else body.logo_artboard
    logo_board = job / f"working_{logo_ab}.svg"
    if not logo_board.is_file():
        raise HTTPException(status_code=400, detail="invalid logo artboard")
    working_svg = logo_board.read_text(encoding="utf-8")

    # The logo artboard's source file -> masters (.ai/.eps) + which page to carve.
    info = art_map.get(str(logo_ab), {})
    fi = info.get("file", 0)
    page = info.get("page", logo_ab + 1)
    fmeta = files[fi] if 0 <= fi < len(files) else {}
    ai_path = Path(fmeta["ai"]) if fmeta.get("ai") else None
    eps_path = Path(fmeta["eps"]) if fmeta.get("eps") else None

    # Resolve the ICON artboard when tagged on a SEPARATE artboard/file. When the
    # icon shares the logo artboard (or is None) the icon is marked within it.
    icon_svg = None
    icon_ab = body.icon_artboard
    if icon_ab is not None and icon_ab != logo_ab:
        icon_board = job / f"working_{icon_ab}.svg"
        if not icon_board.is_file():
            raise HTTPException(status_code=400, detail="invalid icon artboard")
        icon_svg = icon_board.read_text(encoding="utf-8")

    logo_box = tuple(body.logo_box) if body.logo_box else None
    icon_box = tuple(body.icon_box) if body.icon_box else None
    # Back-compat: `selection_box` marks the icon within the logo artboard.
    sel_box = tuple(body.selection_box) if body.selection_box else None

    common = dict(
        brand=body.brand.strip() or "Logo",
        working_svg=working_svg,
        logo_box=logo_box,
        removed_colors=body.removed_colors,
        brand_a=body.brand_a,
        brand_b=body.brand_b,
        ai_path=ai_path if (ai_path and ai_path.exists()) else None,
        eps_path=eps_path if (eps_path and eps_path.exists()) else None,
        artboard_index=page - 1,
    )
    if icon_svg is not None:
        # Separate icon artboard: icon_box marks the icon within icon_svg.
        req = GenerateRequest(icon_svg=icon_svg, icon_box=icon_box, **common)
    else:
        # Icon (if any) marked within the logo artboard.
        req = GenerateRequest(selection_box=icon_box or sel_box, **common)

    try:
        result = run_generate(req, job)
    except selection.BoxMiss as e:
        # A drawn box covers no artwork: tell the CSR to adjust it. The job
        # stays alive so they can fix the box and generate again. The received
        # box + artwork extent are echoed so a screenshot of the error is
        # enough to diagnose a client-side coordinate-mapping bug.
        logging.getLogger("uvicorn.error").warning(
            "box_miss job=%s artboard=%s box=%s received=%s artwork=%s",
            body.job_id, logo_ab, e.box, e.received, e.artwork)
        raise HTTPException(status_code=422, detail={
            "error": "box_miss", "box": e.box, "message": str(e),
            "received": e.received, "artwork": e.artwork})
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
            "generate failed for job %s artboard %s", body.job_id, logo_ab)
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
class _UIFiles(StaticFiles):
    """StaticFiles with deploy-safe caching: the HTML shell must revalidate on
    every load (`no-cache`) so a redeploy is picked up by a normal reload —
    otherwise a cached index.html keeps referencing the OLD hashed bundle and
    the user keeps running stale code after a fix ships. The content-hashed
    /assets/* are immutable and may cache forever."""
    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        if path.startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = "no-cache"
        return resp


_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", _UIFiles(directory=str(_DIST), html=True), name="ui")
