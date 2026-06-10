"""AI artboard segmentation — the designer's eye, merged into the engine.

The geometric heuristics in ``selection.auto_segment`` approximate how a designer
reads an artboard (find the lockup, set the icon apart, ignore tiles/swatches/
copy). They are brittle: every new file finds a gap between the rules. This
module does the real thing — it renders the working SVG and asks Claude (vision)
to identify the primary logo lockup and the standalone icon, returning the same
editable boxes the CSR reviews.

It is **opt-in and graceful**: active only when ``ANTHROPIC_API_KEY`` is set;
any failure (no key, SDK missing, network, bad JSON) returns ``None`` so the
caller falls back to ``selection.auto_segment``. The CSR still reviews/adjusts
the boxes — nothing ships on detection alone (CLAUDE.md).
"""
from __future__ import annotations

import base64
import json
import logging
import os

import cairosvg

from .config import AI_SEGMENT_MAX_PX, AI_SEGMENT_MODEL
from .selection import Suggestion

log = logging.getLogger("uvicorn.error")

_SYSTEM = (
    "You are the segmentation engine inside a logo-package generator used by "
    "customer-success reps. A rep uploads a brand's vector logo source (one "
    "Illustrator artboard) and you decide what the logo is. These artboards are "
    "often 'brand sheets': they show the logo several ways (on light and dark "
    "tiles, full-color and reversed), plus a standalone icon, a row of color "
    "swatches, a tagline, and a paragraph of descriptive copy. Logos come in "
    "every archetype — plain wordmarks, lettermarks/monograms, combination "
    "marks (symbol + wordmark), emblems/badges where the name sits inside the "
    "shape, gradient marks, and mascot/character logos. Like a brand designer, "
    "find the ONE clean primary logo lockup and the standalone icon, and ignore "
    "everything that is presentation scaffolding."
)

_PROMPT = (
    "This image is one artboard, shown at its true proportions.\n\n"
    "Return a JSON object with exactly these keys:\n"
    '- "logo_box": the primary logo lockup — the main, full-color, standard '
    "logo (the wordmark plus any symbol, emblem, or mascot character that is "
    "part of it — a mascot drawn with its brand name is ONE lockup, box them "
    "together). Enclose ONE clean instance tightly, and INCLUDE any trailing "
    "period, dot, or sparkle that is part of the wordmark. Prefer the version "
    "on a plain light background. EXCLUDE background tiles/panels, color "
    "swatches, taglines, descriptive paragraphs, and duplicate or "
    "reversed/alternate-color versions. If the artboard is already just the "
    "single logo with nothing else to exclude, use null (meaning: the whole "
    "artwork is the logo).\n"
    '- "icon_box": the standalone icon / brandmark — the compact symbol, '
    "monogram, emblem, or mascot head/character shown by itself, or the symbol "
    "part of the lockup when it is clearly set apart from the words. Use null "
    "if there is no distinct icon (a plain wordmark has none).\n"
    '- "note": one short sentence on what you selected and what you excluded.\n\n'
    "Each box is [x, y, w, h] as fractions of the image in 0..1, where (x, y) is "
    "the box's TOP-LEFT corner — (0,0) is the top-left of the image and (1,1) is "
    "the bottom-right.\n\n"
    "Respond with ONLY the JSON object — no markdown fences, no commentary."
)


def available() -> bool:
    """True when an API key is configured, so AI segmentation can run."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ai_segment(working_svg: str, viewbox) -> Suggestion | None:
    """Render the artboard and ask Claude for the logo/icon boxes.

    Returns a ``Suggestion`` in SVG user-space coordinates (same shape the
    geometric path returns), or ``None`` on any failure so the caller can fall
    back to ``selection.auto_segment``.
    """
    if not available():
        return None
    vb = viewbox
    if not vb or (vb[2] - vb[0]) <= 0 or (vb[3] - vb[1]) <= 0:
        return None
    png = _render_png(working_svg, vb)
    if png is None:
        return None
    data = _ask_claude(png)
    if data is None:
        return None
    logo = _norm_to_vb(data.get("logo_box"), vb)
    icon = _norm_to_vb(data.get("icon_box"), vb)
    if logo is None and icon is None:
        return None
    note = str(data.get("note") or "").strip()[:300] or "Detected by AI."
    return Suggestion(logo_box=logo, icon_box=icon, note=note, excluded=0)


# --- internals --------------------------------------------------------------
def _render_png(working_svg: str, vb) -> bytes | None:
    """Rasterize the working SVG at its true aspect ratio (capped width) so the
    model sees exactly what the CSR sees in the preview."""
    vbw, vbh = vb[2] - vb[0], vb[3] - vb[1]
    w = min(AI_SEGMENT_MAX_PX, max(1, round(vbw))) or AI_SEGMENT_MAX_PX
    h = max(1, round(w * vbh / vbw))
    try:
        return cairosvg.svg2png(
            bytestring=working_svg.encode("utf-8"),
            output_width=w, output_height=h, background_color="white")
    except Exception:
        log.exception("ai_segment: SVG render failed")
        return None


def _ask_claude(png: bytes) -> dict | None:
    try:
        import anthropic
    except ImportError:
        log.warning("ai_segment: anthropic SDK not installed; using geometry")
        return None
    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the env
        b64 = base64.standard_b64encode(png).decode("ascii")
        resp = client.messages.create(
            model=AI_SEGMENT_MODEL,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return _extract_json(text)
    except Exception:
        log.exception("ai_segment: Claude request failed; using geometry")
        return None


def _extract_json(text: str) -> dict | None:
    """Defensively pull the JSON object out of the model's reply (tolerates a
    stray markdown fence or prose around it)."""
    if not text:
        return None
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        obj = json.loads(text[s:e + 1])
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        return None


def _norm_to_vb(norm, vb) -> tuple[float, float, float, float] | None:
    """Map a normalized [x, y, w, h] (0..1, top-left origin) to SVG user space,
    clamped to the artboard. Returns ``None`` for a missing or degenerate box."""
    if not isinstance(norm, (list, tuple)) or len(norm) != 4:
        return None
    try:
        x, y, w, h = (float(v) for v in norm)
    except (ValueError, TypeError):
        return None
    minx, miny, maxx, maxy = vb
    vbw, vbh = maxx - minx, maxy - miny
    x = min(max(x, 0.0), 1.0)
    y = min(max(y, 0.0), 1.0)
    w = min(max(w, 0.0), 1.0 - x)
    h = min(max(h, 0.0), 1.0 - y)
    if w <= 0.002 or h <= 0.002:           # nothing meaningful selected
        return None
    return (round(minx + x * vbw, 2), round(miny + y * vbh, 2),
            round(w * vbw, 2), round(h * vbh, 2))
