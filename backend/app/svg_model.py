"""The working-SVG path model (§7.3).

Every drawable leaf is tagged with a stable ``data-lpid`` so we can carry two
views of the same element in lockstep:

* **geometry** — bbox + centroid from ``svgelements`` (resolves transforms).
* **paint** — the authored fill/stroke string from the lxml tree (gradients
  survive here; svgelements would flatten them to black).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from functools import cached_property

from lxml import etree
from svgelements import SVG as SE_SVG

from . import svgutil
from .config import LPID_ATTR
from .svgutil import qn

BBox = tuple[float, float, float, float]

# Length with an optional CSS/SVG unit (px, pt, mm, ...). Used to derive a
# viewBox from width/height when a converter omits one. '%' is unresolvable
# here (no parent) -> None, so we fall back to the content bounds instead.
_LEN_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px|pt|pc|mm|cm|in|em|ex)?\s*$", re.I)


def _parse_length(value: str | None) -> float | None:
    if not value:
        return None
    m = _LEN_RE.match(value)
    return float(m.group(1)) if m else None


@dataclass
class PathNode:
    lpid: str
    tag: str
    fill: str | None            # resolved authored fill string ('#ec1c24', 'url(#g1)', 'none', ...)
    has_stroke: bool
    bbox: BBox | None           # (xmin, ymin, xmax, ymax) in user space, transforms resolved
    is_background: bool = False  # full-page rect from PDF/AI export — not artwork ink

    @property
    def centroid(self) -> tuple[float, float] | None:
        if not self.bbox:
            return None
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    @property
    def area(self) -> float:
        if not self.bbox:
            return 0.0
        x0, y0, x1, y1 = self.bbox
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)


class WorkingSVG:
    """Parsed working SVG: lxml tree for edits + geometry from svgelements."""

    def __init__(self, root: etree._Element):
        self.root = svgutil.flatten_uses(root)   # inline <use> text -> tagged paths
        self._ensure_viewbox()                   # guarantee a real coordinate system
        self.class_map = svgutil.parse_style_classes(self.root)
        self.parents = svgutil.build_parent_map(self.root)
        self._tag_leaves()
        self.nodes: list[PathNode] = self._build_nodes()
        self._mark_background()
        self.by_lpid: dict[str, PathNode] = {n.lpid: n for n in self.nodes}

    def _ensure_viewbox(self) -> None:
        """Lock the SVG to ONE coordinate system shared by the browser preview,
        the served ``viewbox``, and svgelements geometry.

        Two converter quirks break that otherwise:
          * some poppler builds emit width/height but **no viewBox** — geometry
            then had no frame and ``viewbox`` fell back to the ink bbox (wrong
            origin/aspect);
          * some emit ``width="880.91pt"`` alongside ``viewBox="0 0 880.91 …"``,
            and some **svgelements versions convert the ``pt`` to px** (×1.333),
            so every bbox lands 1.333× larger than the viewBox. The browser maps
            a box into viewBox units, the server then compares it to px-scaled
            geometry, and a box drawn on the mark misses it server-side.

        Fix: ensure a viewBox exists, then pin width/height to the viewBox's
        **unitless** numbers so no version can rescale the geometry by units."""
        root = self.root
        if not root.get("viewBox"):
            w = _parse_length(root.get("width"))
            h = _parse_length(root.get("height"))
            if w and h:
                root.set("viewBox", f"0 0 {w:g} {h:g}")
        vb = root.get("viewBox")
        if not vb:
            return
        try:
            parts = [float(x) for x in vb.replace(",", " ").split()]
        except ValueError:
            return
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            # unitless width/height == viewBox size -> svgelements maps 1:1, in
            # the SAME space the browser and `viewbox` use (no pt->px drift).
            root.set("width", f"{parts[2]:g}")
            root.set("height", f"{parts[3]:g}")

    @property
    def ink_nodes(self) -> list[PathNode]:
        """Artwork leaves only — page/background rects excluded."""
        return [n for n in self.nodes if not n.is_background]

    def _mark_background(self) -> None:
        """Flag leaves that span ~the whole page as background. PDF/AI exports
        (pdf2svg, Illustrator) emit a full-page rect that is not artwork; left in
        it inflates the bbox (logo renders tiny/off-center), pollutes color
        detection, and corrupts selection. Never flag everything — if dropping
        the candidates would leave no ink, keep them."""
        vb = self.viewbox
        if not vb:
            return
        vbw, vbh = vb[2] - vb[0], vb[3] - vb[1]
        if vbw <= 0 or vbh <= 0:
            return
        candidates = []
        for n in self.nodes:
            if not n.bbox:
                continue
            w, h = n.bbox[2] - n.bbox[0], n.bbox[3] - n.bbox[1]
            if w >= 0.9 * vbw and h >= 0.9 * vbh:
                candidates.append(n)
        if candidates and len(candidates) < len(self.nodes):
            for n in candidates:
                n.is_background = True

    # -- construction ---------------------------------------------------------
    @classmethod
    def from_string(cls, data: bytes | str) -> "WorkingSVG":
        return cls(svgutil.parse_svg(data))

    def _tag_leaves(self) -> None:
        counter = 0
        for el in svgutil.iter_leaves(self.root):
            if not el.get(LPID_ATTR):
                counter += 1
                el.set(LPID_ATTR, f"{counter:04d}")

    def _geometry(self) -> dict[str, BBox]:
        """Run svgelements over the (lpid-tagged) SVG and collect bboxes."""
        text = svgutil.serialize(self.root)
        boxes: dict[str, BBox] = {}
        try:
            doc = SE_SVG.parse(io.StringIO(text))
        except Exception:
            return boxes
        for el in doc.elements():
            vals = getattr(el, "values", None)
            if not vals:
                continue
            lpid = vals.get(LPID_ATTR)
            if not lpid:
                continue
            try:
                bb = el.bbox()
            except Exception:
                bb = None
            if bb:
                boxes[lpid] = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
        return boxes

    def _build_nodes(self) -> list[PathNode]:
        boxes = self._geometry()
        nodes: list[PathNode] = []
        for el in svgutil.iter_leaves(self.root):
            lpid = el.get(LPID_ATTR)
            fill = svgutil.effective_paint(el, "fill", self.class_map, self.parents)
            stroke = svgutil.has_visible_stroke(el, self.class_map, self.parents)
            nodes.append(PathNode(
                lpid=lpid,
                tag=svgutil.local_name(el),
                fill=fill,
                has_stroke=stroke,
                bbox=boxes.get(lpid),
            ))
        return nodes

    # -- geometry helpers -----------------------------------------------------
    def overall_bbox(self, lpids: list[str] | None = None) -> BBox | None:
        sel = self.ink_nodes if lpids is None else [self.by_lpid[i] for i in lpids if i in self.by_lpid]
        boxes = [n.bbox for n in sel if n.bbox]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    @cached_property
    def viewbox(self) -> BBox | None:
        vb = self.root.get("viewBox")
        if vb:
            try:
                x, y, w, h = (float(v) for v in vb.replace(",", " ").split())
                return (x, y, x + w, y + h)
            except ValueError:
                pass
        return self.overall_bbox()

    # -- defs / gradients -----------------------------------------------------
    def gradient_defs(self) -> dict[str, etree._Element]:
        """Map gradient id -> <linearGradient>/<radialGradient> element."""
        out: dict[str, etree._Element] = {}
        for tag in ("linearGradient", "radialGradient"):
            for el in self.root.iter(qn(tag)):
                gid = el.get("id")
                if gid:
                    out[gid] = el
        return out

    def serialize(self) -> str:
        return svgutil.serialize(self.root)
