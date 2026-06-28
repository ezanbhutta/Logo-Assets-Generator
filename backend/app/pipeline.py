"""End-to-end orchestration (§3, §7). Two entry points mirror the API:

* ``run_ingest``   — `.ai` -> working SVG + detected layers/colors/scope.
* ``run_generate`` — selection + confirmed colors -> package zip.

Stateless: all work happens in a per-job temp dir, cleaned by the caller (§2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import colors, ingest, selection, treatments, vision
from .config import (ICON_STEM, LOGO_STEM, variant_filename)
from .exporters import (write_svg, write_jpg, write_pdf, write_png_transparent)
from .ingest import IngestError
from .packager import PackageBuilder
from .recipes import with_bg_recipes, transparent_recipes
from .selection import Selection
from .svg_model import WorkingSVG


class ManualFlag(Exception):
    """Out-of-scope input — refuse cleanly, build no partial package (§8/6, §9)."""
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


# --- ingest ------------------------------------------------------------------
@dataclass
class ArtboardSummary:
    index: int                            # GLOBAL index across all files
    label: str
    working_svg: str                      # lpid-tagged; the frontend renders this
    viewbox: list[float]
    classification: str
    supported: bool
    reasons: list[str]
    swatches: list[dict]
    brand_a: str
    brand_b: str
    is_gradient: bool
    ink_count: int
    named_selection: dict | None
    suggestion: dict | None = None         # auto-detected logo/icon boxes (editable)
    geom_sig: tuple = ()                   # geometry-only signature (de-dup key)
    file_index: int = 0                   # which uploaded file this came from
    file_name: str = ""                   # that file's name
    page: int = 1                         # 1-based page within its file

    @property
    def brand_count(self) -> int:
        return sum(1 for s in self.swatches if s.get("brand"))


@dataclass
class IngestSummary:
    converter: str
    artboards: list[ArtboardSummary]
    primary_index: int                    # engine's suggested primary logo (global)
    files: list[str] = field(default_factory=list)

    @property
    def artboard_count(self) -> int:
        return len(self.artboards)


def _ingest_file(source: Path, workdir: Path, file_index: int, file_name: str,
                 start: int) -> tuple[list[ArtboardSummary], str]:
    """Convert every artboard/page of ONE file. Working SVGs are persisted as
    ``working_{global}.svg`` (global index, unique across all uploaded files)."""
    n = ingest.page_count(source)
    converter = "pdf2svg"
    boards: list[ArtboardSummary] = []
    for page in range(n):
        gidx = start + page
        try:
            res = ingest.ingest(source, workdir, page=page + 1, out_name=f"working_{gidx}.svg")
        except IngestError:
            continue
        converter = res.converter
        model = WorkingSVG.from_string(res.svg_text)
        (workdir / f"working_{gidx}.svg").write_text(model.serialize(), encoding="utf-8")
        report = colors.detect(model)
        named = selection.detect_named_layers(model)
        seg = selection.auto_segment(model)
        vb = model.viewbox or (0.0, 0.0, 0.0, 0.0)
        geom_sig = tuple(sorted(
            tuple(round(c) for c in nd.bbox) for nd in model.ink_nodes if nd.bbox))
        label = (f"{file_name} · Artboard {page + 1}" if file_name else f"Artboard {page + 1}")
        boards.append(ArtboardSummary(
            index=gidx, label=label, working_svg=model.serialize(),
            viewbox=[round(v, 3) for v in vb],
            classification=report.classification,
            supported=report.classification in ("solid", "gradient"),
            reasons=report.reasons, swatches=report.swatches,
            brand_a=report.brand_a, brand_b=report.brand_b,
            is_gradient=report.is_gradient, ink_count=len(model.ink_nodes),
            named_selection=({"icon": named.icon, "source": named.source,
                              "overlap_warning": named.overlap_warning} if named else None),
            suggestion=seg.as_dict() if seg else None, geom_sig=geom_sig,
            file_index=file_index, file_name=file_name, page=page + 1,
        ))
    return boards, converter


def run_ingest(source: Path, workdir: Path) -> IngestSummary:
    """Single-file ingest (back-compat). Convert every artboard/page; the working
    SVG for artboard *i* is persisted as ``working_{i}.svg``."""
    return run_ingest_multi([(source, Path(source).stem)], workdir)


def run_ingest_multi(files: list[tuple[Path, str]], workdir: Path) -> IngestSummary:
    """Ingest MULTIPLE uploaded files. Every artboard of every file is converted
    and gets a GLOBAL index; the CSR sees them all and tags one Logo + one Icon
    (which may live on different artboards/files). Treatment-variant duplicates
    are collapsed *within* each file (cross-file artboards stay distinct)."""
    boards: list[ArtboardSummary] = []
    converter = "pdf2svg"
    file_names: list[str] = []
    for fi, (src, name) in enumerate(files):
        file_names.append(name)
        fb, conv = _ingest_file(src, workdir, fi, name, start=len(boards))
        # de-dup treatment variants WITHIN this file (keep cross-file distinct)
        boards.extend(_dedupe(fb))
        if fb:
            converter = conv

    if not boards:
        raise IngestError("Could not convert any artboard of the uploaded file(s).")
    primary = _suggest_primary(boards)

    # Robust icon/logo detection: when an API key is configured, ask AI vision to
    # read the PRIMARY artboard and use its boxes as the pre-filled suggestion.
    # Geometry stays the instant fallback and covers every other artboard.
    if vision.available():
        pb = next((b for b in boards if b.index == primary), None)
        if pb is not None:
            try:
                ai = vision.ai_segment(pb.working_svg, tuple(pb.viewbox))
                if ai is not None:
                    pb.suggestion = ai.as_dict()
            except Exception:
                logging.getLogger("uvicorn.error").exception("ingest: AI segment failed")

    return IngestSummary(converter=converter, artboards=boards,
                         primary_index=primary, files=file_names)


def _dedupe(boards: list[ArtboardSummary]) -> list[ArtboardSummary]:
    """Collapse artboards that are the same shape in different treatments (a
    designer file often lays out white/black/color variants of one mark across
    artboards). Keep the most full-color (most brand colors) representative of
    each geometry, so the CSR picks from distinct logos, not duplicates."""
    groups: dict[tuple, list[ArtboardSummary]] = {}
    for b in boards:
        groups.setdefault(b.geom_sig, []).append(b)
    reps = [max(g, key=lambda b: (b.brand_count, -b.index)) for g in groups.values()]
    reps.sort(key=lambda b: b.index)
    return reps


def _suggest_primary(boards: list[ArtboardSummary]) -> int:
    """Suggest the primary lockup: the most complete (most ink) supported board,
    tie-broken toward the most full-color (most brand colors)."""
    supported = [b for b in boards if b.supported] or boards
    return max(supported, key=lambda b: (b.ink_count, b.brand_count)).index


# --- generate ----------------------------------------------------------------
@dataclass
class GenerateRequest:
    brand: str
    working_svg: str                      # the LOGO artboard's working SVG
    selection_box: tuple[float, float, float, float] | None = None  # icon within the logo artboard
    logo_box: tuple[float, float, float, float] | None = None
    icon_svg: str | None = None           # a SEPARATE icon artboard (None -> icon within the logo)
    icon_box: tuple[float, float, float, float] | None = None       # icon within `icon_svg`
    use_named_layers: bool = False
    removed_colors: list[str] = field(default_factory=list)
    brand_a: str | None = None
    brand_b: str | None = None
    ai_path: Path | None = None
    eps_path: Path | None = None
    artboard_index: int = 0               # the LOGO artboard's page -> masters (§4)


@dataclass
class GenerateResult:
    zip_path: Path
    manifest: list[str]
    classification: str
    is_gradient: bool
    brand_a: str
    brand_b: str
    include_icon: bool = True


def _render_set(ctx, mark: str, stem: str, is_gradient: bool, builder: PackageBuilder) -> None:
    """Write the full with-background + transparent file set for one mark."""
    for t in with_bg_recipes(mark, ctx.report, is_gradient):  # JPEG/PDF/SVG @ artboard size
        svg = treatments.render_variant(ctx, mark, t, with_background=True)
        write_svg(svg, builder.svg / variant_filename(stem, t.index, "svg"))
        write_jpg(svg, builder.jpg / variant_filename(stem, t.index, "jpg"))
        write_pdf(svg, builder.pdf / variant_filename(stem, t.index, "pdf"))
    for t in transparent_recipes(mark):                      # PNG@1080/SVG/PDF, edge-to-edge
        svg = treatments.render_variant(ctx, mark, t, with_background=False)
        write_svg(svg, builder.t_svg / variant_filename(stem, t.index, "svg"))
        write_png_transparent(svg, builder.t_png / variant_filename(stem, t.index, "png"))
        write_pdf(svg, builder.t_pdf / variant_filename(stem, t.index, "pdf"))


def _icon_artboard_selection(model: WorkingSVG, icon_box) -> Selection:
    """The icon from a DEDICATED icon artboard: the icon_box region, or the whole
    artboard's artwork (minus presentation panels) when no box is drawn — the
    artboard itself IS the icon."""
    if icon_box is not None:
        sel, _ = selection.select(model, logo_box=None, icon_box=icon_box)  # may raise BoxMiss
        return Selection(icon=sel.icon, logo=sel.icon, source="box")
    ink = model.ink_nodes
    panels = selection._panel_ids(ink, model.viewbox)
    ids = [n.lpid for n in ink if n.lpid not in panels] or [n.lpid for n in ink]
    return Selection(icon=ids, logo=ids, source="artboard")


def run_generate(req: GenerateRequest, workdir: Path) -> GenerateResult:
    logo_model = WorkingSVG.from_string(req.working_svg)

    report = colors.detect(
        logo_model,
        exclude=set(req.removed_colors),
        brand_a_override=req.brand_a,
        brand_b_override=req.brand_b,
    )
    if not report.supported:
        raise ManualFlag(report.reasons)  # §8 rule 6: no partial package

    builder = PackageBuilder(req.brand, workdir)

    # The ICON set comes from a SEPARATE tagged artboard, or from within the logo
    # artboard. Either way it uses the LOGO's colour report, so the logo and icon
    # sets share the exact same 5 backgrounds (the reference standard).
    icon_ctx = None
    icon_gradient = report.is_gradient
    if req.icon_svg is not None:
        icon_model = WorkingSVG.from_string(req.icon_svg)
        isel = _icon_artboard_selection(icon_model, req.icon_box)
        if isel.icon:
            icon_ctx = treatments.build_context(icon_model, isel, report)
            icon_gradient = colors.detect(icon_model).is_gradient
        # the logo's OWN internal icon (drives the transparent split slot) is
        # auto-detected within the lockup since the marked icon is elsewhere.
        logo_sel, _ = selection.select(logo_model, logo_box=req.logo_box, icon_box=None)
    else:
        # Single-artboard flow: the icon is marked within the logo artboard.
        logo_sel, has_icon = selection.select(
            logo_model, logo_box=req.logo_box, icon_box=req.selection_box)
        if has_icon:
            icon_ctx = treatments.build_context(logo_model, logo_sel, report)

    logo_ctx = treatments.build_context(logo_model, logo_sel, report)

    if icon_ctx is not None:
        _render_set(icon_ctx, "icon", ICON_STEM, icon_gradient, builder)
    _render_set(logo_ctx, "logo", LOGO_STEM, report.is_gradient, builder)

    builder.passthrough(req.ai_path, req.eps_path, req.artboard_index)
    zip_path = workdir / f"{req.brand} Files.zip"
    builder.zip(zip_path)

    return GenerateResult(
        zip_path=zip_path,
        manifest=builder.manifest(),
        classification=report.classification,
        is_gradient=report.is_gradient,
        brand_a=report.brand_a,
        brand_b=report.brand_b,
        include_icon=icon_ctx is not None,
    )
