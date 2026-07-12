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
from .config import (ICON_STEM, LOGO_STEM, WORDMARK_STEM, safe_brand,
                     variant_filename)
from .exporters import (write_svg, write_jpg, write_pdf, write_png_transparent)
from .ingest import IngestError
from .packager import PackageBuilder
from .recipes import Treatment, with_bg_recipes, transparent_recipes
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
class ExtraLockup:
    """An additional tagged artboard shipped as its own named lockup set —
    "Secondary Logo", "Horizontal Logo", "Oneline Logo", "Vertical Logo", or any
    custom name. Rendered logo-shaped (1920×1080 artboards, 60% binding side)
    with the PRIMARY logo's confirmed palette, so every lockup in the package
    shares the same backgrounds."""
    name: str
    svg: str                              # that artboard's working SVG
    box: tuple[float, float, float, float] | None = None  # crop region (None -> whole artboard)


@dataclass
class GenerateRequest:
    brand: str
    working_svg: str                      # the LOGO artboard's working SVG
    selection_box: tuple[float, float, float, float] | None = None  # icon within the logo artboard
    logo_box: tuple[float, float, float, float] | None = None
    # Text-only region within the logo artboard -> ships the "Wordmark" set
    # (typography only), the way the icon box ships the Icon set.
    wordmark_box: tuple[float, float, float, float] | None = None
    icon_svg: str | None = None           # a SEPARATE icon artboard (None -> icon within the logo)
    icon_box: tuple[float, float, float, float] | None = None       # icon within `icon_svg`
    use_named_layers: bool = False
    removed_colors: list[str] = field(default_factory=list)
    brand_a: str | None = None
    brand_b: str | None = None
    ai_path: Path | None = None
    eps_path: Path | None = None
    artboard_index: int = 0               # the LOGO artboard's page -> masters (§4)
    extras: list[ExtraLockup] = field(default_factory=list)  # additional named lockups


@dataclass
class GenerateResult:
    zip_path: Path
    manifest: list[str]
    classification: str
    is_gradient: bool
    brand_a: str
    brand_b: str
    include_icon: bool = True
    include_wordmark: bool = False


def _slide_image(svg: str):
    """A slide's small perceptual render (48px wide, RGB) for duplicate
    comparison. None when the render fails (the slide is then treated as
    unique — never block packaging on the dedupe)."""
    try:
        import io
        import cairosvg
        from PIL import Image
        png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=192)
        img = Image.open(io.BytesIO(png)).convert("RGB")
        return img.resize((48, max(1, round(img.height * 48 / img.width))))
    except Exception:
        return None


def _looks_same(a, b) -> bool:
    """Do two slides read as THE SAME slide to a designer's eye? True when no
    downsampled pixel differs by more than ~7% on any channel — catches both
    byte-identical renders and imperceptibly-different ones (a `#0a0a0a` field
    vs `#000000` is still "the black slide"; Inclement's duplicate pair). Deep
    shadows get a looser bar (the eye can't split `#000013` from `#000000`, an
    authored blue-black vs the black field) while light values stay strict, so
    a soft tint field never collapses into white. Any real difference — a white
    vs yellow wordmark — moves whole regions far past both bars."""
    if a is None or b is None or a.size != b.size:
        return False
    for x, y in zip(a.tobytes(), b.tobytes()):
        d = abs(x - y)
        if d > 18 and not (max(x, y) <= 48 and d <= 32):
            return False
    return True


def _two_tone_ctx(ctx, mark: str):
    """A context able to render the TWO-TONE dark slide — icon keeps its brand
    color, wordmark goes WHITE (black field · yellow icon · white text, the
    owner's Inclement standard).

    Uses the marked icon when the selection has one. When it doesn't (the icon
    was tagged on a SEPARATE artboard, so the logo selection carries no split —
    the flow that shipped an olive shade field instead), the split is DERIVED
    the way ``auto_icon`` does it: cut at the largest gap, most-square side is
    the icon. Returns None only when the logo genuinely has no usable split."""
    if mark != "logo":
        return None
    sel = ctx.selection
    if sel.icon and set(sel.logo) - set(sel.icon):
        return ctx
    nodes = [ctx.model.by_lpid[i] for i in sel.logo
             if i in ctx.model.by_lpid and ctx.model.by_lpid[i].bbox]
    if len(nodes) < 2:
        return None
    icon_grp, word_grp, _sep = selection._largest_gap_split(ctx.model, nodes)
    if not icon_grp or not word_grp:
        return None
    two = Selection(icon=[n.lpid for n in icon_grp], logo=list(sel.logo), source="auto")
    return treatments.build_context(ctx.model, two, ctx.report)


def _alternates(ctx, mark: str, t: Treatment) -> list[tuple[Treatment, object]]:
    """(treatment, context) replacements for a would-be DUPLICATE slide (the
    Inclement rule — a 1-color yellow brand rendered slots 02 and 04 as the same
    full-yellow-on-black).

    The ONLY replacement is the **two-tone dark slide** — the icon keeps its
    brand color, the wordmark goes WHITE (black field · yellow icon · white
    text). The icon/text split is the marked one, or derived when the icon
    lives on another artboard.

    There is deliberately NO derived-color fallback: a shade_of(brand) field
    read as olive — a color that is NOT in the logo (owner rule: substitutions
    stay in the logo's scheme; the engine never invents an outside color).
    Where no two-tone exists — a 1-color ICON set, whose yellow/black/white
    palette simply has no 6th distinct composition — the original ships."""
    tt = _two_tone_ctx(ctx, mark)
    if tt is None:
        return []
    return [(Treatment(t.index, t.background, "split"), tt)]


def _render_set(ctx, mark: str, stem: str, is_gradient: bool, builder: PackageBuilder) -> None:
    """Write the full with-background + transparent file set for one mark.

    No two with-background slides in a set may be visually identical (owner
    rule, learned from Inclement): when a recipe slot renders the same slide as
    an earlier slot (e.g. a 1-color brand's 02 dark and 04 brand-B fields both
    resolve to the same mark on black), the later slot is replaced by the
    designer alternate — the two-tone (brand icon + white text), else a deep
    in-scheme shade field. Slot numbering never changes."""
    seen: list = []
    for t in with_bg_recipes(mark, ctx.report, is_gradient):  # JPEG/PDF/SVG @ artboard size
        svg = treatments.render_variant(ctx, mark, t, with_background=True)
        img = _slide_image(svg)
        if any(_looks_same(img, s) for s in seen):
            for alt_t, alt_ctx in _alternates(ctx, mark, t):
                alt_svg = treatments.render_variant(alt_ctx, mark, alt_t, with_background=True)
                alt_img = _slide_image(alt_svg)
                if not any(_looks_same(alt_img, s) for s in seen):
                    svg, img = alt_svg, alt_img
                    break
        seen.append(img)
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


def _lockup_stem(name: str, used: set[str]) -> str:
    """A safe, unique file stem for an extra lockup's files. The CSR-supplied
    name is sanitized like the brand (it becomes filenames) and de-duped against
    the stems already in the package (`Logo`, `Icon`, other lockups) so two
    lockups can never overwrite each other's files."""
    base = safe_brand(name).strip() or "Lockup"
    stem, n = base, 2
    while stem.lower() in used:
        stem = f"{base} {n}"
        n += 1
    used.add(stem.lower())
    return stem


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

    # The WORDMARK (typography-only) set: an explicitly-marked text region within
    # the logo artboard, shipped as its own set the way the icon is. Rendered
    # logo-shaped (1920×1080, 60%) with a 3-slot transparent set (full/white/
    # black — a wordmark has no icon, so the split slot would be a duplicate).
    wordmark_ctx = None
    if req.wordmark_box is not None:
        try:
            wsel, _ = selection.select(logo_model, logo_box=req.wordmark_box, icon_box=None)
        except selection.BoxMiss as e:
            raise selection.BoxMiss("wordmark", received=e.received, artwork=e.artwork)
        if wsel.logo:
            wordmark_ctx = treatments.build_context(
                logo_model, Selection(icon=[], logo=wsel.logo, source="box"), report)

    if icon_ctx is not None:
        _render_set(icon_ctx, "icon", ICON_STEM, icon_gradient, builder)
    _render_set(logo_ctx, "logo", LOGO_STEM, report.is_gradient, builder)
    if wordmark_ctx is not None:
        _render_set(wordmark_ctx, "wordmark", WORDMARK_STEM, report.is_gradient, builder)

    # Additional named lockups (Secondary / Horizontal / Vertical / Oneline …):
    # each tagged artboard ships as its own full logo-shaped set, named after its
    # lockup. All sets use the PRIMARY logo's confirmed palette so the whole
    # package shares one family of backgrounds; gradient-ness is per-artboard
    # (a gradient secondary gets the gradient recipes, like the icon does).
    used_stems = {ICON_STEM.lower(), LOGO_STEM.lower()}
    if wordmark_ctx is not None:
        used_stems.add(WORDMARK_STEM.lower())
    for ex in req.extras:
        model = WorkingSVG.from_string(ex.svg)
        sel, _ = selection.select(model, logo_box=ex.box, icon_box=None)  # may raise BoxMiss
        if not sel.logo:
            continue                        # empty artboard — nothing to ship
        stem = _lockup_stem(ex.name, used_stems)
        ctx = treatments.build_context(model, sel, report)
        _render_set(ctx, "logo", stem, colors.detect(model).is_gradient, builder)

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
        include_wordmark=wordmark_ctx is not None,
    )
