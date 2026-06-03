"""The working-SVG path model (§7.3).

Every drawable leaf is tagged with a stable ``data-lpid`` so we can carry two
views of the same element in lockstep:

* **geometry** — bbox + centroid from ``svgelements`` (resolves transforms).
* **paint** — the authored fill/stroke string from the lxml tree (gradients
  survive here; svgelements would flatten them to black).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from functools import cached_property

from lxml import etree
from svgelements import SVG as SE_SVG

from . import svgutil
from .config import LPID_ATTR
from .svgutil import qn

BBox = tuple[float, float, float, float]


@dataclass
class PathNode:
    lpid: str
    tag: str
    fill: str | None            # resolved authored fill string ('#ec1c24', 'url(#g1)', 'none', ...)
    has_stroke: bool
    bbox: BBox | None           # (xmin, ymin, xmax, ymax) in user space, transforms resolved

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
        self.root = root
        self.class_map = svgutil.parse_style_classes(root)
        self.parents = svgutil.build_parent_map(root)
        self._tag_leaves()
        self.nodes: list[PathNode] = self._build_nodes()
        self.by_lpid: dict[str, PathNode] = {n.lpid: n for n in self.nodes}

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
        sel = self.nodes if lpids is None else [self.by_lpid[i] for i in lpids if i in self.by_lpid]
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
