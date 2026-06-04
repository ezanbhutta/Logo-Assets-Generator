"""End-to-end orchestration (§3, §7). Two entry points mirror the API:

* ``run_ingest``   — `.ai` -> working SVG + detected layers/colors/scope.
* ``run_generate`` — selection + confirmed colors -> package zip.

Stateless: all work happens in a per-job temp dir, cleaned by the caller (§2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import colors, selection, treatments
from .config import (ICON_STEM, LOGO_STEM, variant_filename)
from .exporters import (write_svg, write_jpg, write_pdf, write_png_transparent)
from .ingest import ingest
from .packager import PackageBuilder
from .recipes import with_bg_recipes, transparent_recipes
from .svg_model import WorkingSVG


class ManualFlag(Exception):
    """Out-of-scope input — refuse cleanly, build no partial package (§8/6, §9)."""
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


# --- ingest ------------------------------------------------------------------
@dataclass
class IngestSummary:
    working_svg: str
    converter: str
    viewbox: list[float]
    classification: str
    reasons: list[str]
    swatches: list[dict]
    brand_a: str
    brand_b: str
    is_gradient: bool
    named_selection: dict | None


def run_ingest(source: Path, workdir: Path) -> IngestSummary:
    res = ingest(source, workdir)
    model = WorkingSVG.from_string(res.svg_text)
    report = colors.detect(model)
    named = selection.detect_named_layers(model)
    vb = model.viewbox or (0.0, 0.0, 0.0, 0.0)
    return IngestSummary(
        working_svg=model.serialize(),        # lpid-tagged; frontend renders this
        converter=res.converter,
        viewbox=[round(v, 3) for v in vb],
        classification=report.classification,
        reasons=report.reasons,
        swatches=report.swatches,
        brand_a=report.brand_a,
        brand_b=report.brand_b,
        is_gradient=report.is_gradient,
        named_selection=(
            {"icon": named.icon, "source": named.source,
             "overlap_warning": named.overlap_warning}
            if named else None),
    )


# --- generate ----------------------------------------------------------------
@dataclass
class GenerateRequest:
    brand: str
    working_svg: str
    selection_box: tuple[float, float, float, float] | None = None
    use_named_layers: bool = False
    removed_colors: list[str] = field(default_factory=list)
    brand_a: str | None = None
    brand_b: str | None = None
    ai_path: Path | None = None
    eps_path: Path | None = None


@dataclass
class GenerateResult:
    zip_path: Path
    manifest: list[str]
    classification: str
    is_gradient: bool
    brand_a: str
    brand_b: str
    include_icon: bool = True


def run_generate(req: GenerateRequest, workdir: Path) -> GenerateResult:
    model = WorkingSVG.from_string(req.working_svg)

    report = colors.detect(
        model,
        exclude=set(req.removed_colors),
        brand_a_override=req.brand_a,
        brand_b_override=req.brand_b,
    )
    if not report.supported:
        raise ManualFlag(report.reasons)  # §8 rule 6: no partial package

    # The icon set is OPTIONAL. Generate it only when the CSR marked the icon
    # (a box) or the file has named layers; otherwise produce just the logo
    # design files — don't force an icon (per request).
    if req.selection_box is not None:
        sel = selection.resolve(model, req.selection_box)  # box, with fallback
        include_icon = True
    else:
        named = selection.detect_named_layers(model)
        if named is not None and named.icon:
            sel = named
            include_icon = True
        else:
            sel = selection.Selection(
                icon=[], wordmark=[n.lpid for n in model.ink_nodes], source="none")
            include_icon = False

    ctx = treatments.build_context(model, sel, report)
    builder = PackageBuilder(req.brand, workdir)

    marks = ([("icon", ICON_STEM)] if include_icon else []) + [("logo", LOGO_STEM)]
    for mark, stem in marks:
        # --- with-background (JPG/PDF/SVG @ 1920x1080) ---
        for t in with_bg_recipes(mark, report.is_gradient):
            svg = treatments.render_variant(ctx, mark, t, with_background=True)
            write_svg(svg, builder.svg / variant_filename(stem, t.index, "svg"))
            write_jpg(svg, builder.jpg / variant_filename(stem, t.index, "jpg"))
            write_pdf(svg, builder.pdf / variant_filename(stem, t.index, "pdf"))
        # --- transparent (PNG@1080/SVG/PDF, edge-to-edge) ---
        for t in transparent_recipes(mark):
            svg = treatments.render_variant(ctx, mark, t, with_background=False)
            write_svg(svg, builder.t_svg / variant_filename(stem, t.index, "svg"))
            write_png_transparent(svg, builder.t_png / variant_filename(stem, t.index, "png"))
            write_pdf(svg, builder.t_pdf / variant_filename(stem, t.index, "pdf"))

    builder.passthrough(req.ai_path, req.eps_path)
    zip_path = workdir / f"{req.brand} Files.zip"
    builder.zip(zip_path)

    return GenerateResult(
        zip_path=zip_path,
        manifest=builder.manifest(),
        classification=report.classification,
        is_gradient=report.is_gradient,
        brand_a=report.brand_a,
        brand_b=report.brand_b,
        include_icon=include_icon,
    )
