"""Icon selection in vector space (§7.3, §8 rule 3).

A path belongs to the **icon** group iff its bounding-box center (centroid)
falls inside the selection box. Whole paths only — a path is never split at the
box edge. ``wordmark = all paths - icon paths``; ``full = all paths``.

If the source has named layers/groups (id / data-name / inkscape:label
≈ Icon / Logotype / Logo) we auto-assign and the CSR need only confirm.
"""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .config import LPID_ATTR
from .svgutil import local_name, iter_leaves
from .svg_model import WorkingSVG

INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"

_ICON_HINTS = ("icon", "mark", "symbol", "flame", "glyph", "brandmark")
_WORD_HINTS = ("logotype", "wordmark", "word", "text", "type", "name")


@dataclass
class Selection:
    icon: list[str]        # lpids in the icon group
    wordmark: list[str]    # lpids in the wordmark group (remainder)
    source: str            # 'box' | 'named-layers'
    overlap_warning: bool = False  # icon & wordmark bboxes overlap heavily (§9 integrated lockup)

    @property
    def full(self) -> list[str]:
        return self.icon + self.wordmark


# --- box selection -----------------------------------------------------------
def select_by_box(model: WorkingSVG, box: tuple[float, float, float, float]) -> Selection:
    """`box` = (x, y, w, h) in SVG user space. Icon = centroids inside the box."""
    x, y, w, h = box
    x0, y0, x1, y1 = x, y, x + w, y + h
    icon: list[str] = []
    wordmark: list[str] = []
    for n in model.ink_nodes:
        c = n.centroid
        if c is not None and x0 <= c[0] <= x1 and y0 <= c[1] <= y1:
            icon.append(n.lpid)
        else:
            wordmark.append(n.lpid)
    return Selection(icon=icon, wordmark=wordmark, source="box",
                     overlap_warning=_overlap_warning(model, icon, wordmark))


# --- named-layer auto-detection ---------------------------------------------
def _label_of(el: etree._Element) -> str:
    for attr in ("id", "data-name", INKSCAPE_LABEL, "class"):
        v = el.get(attr)
        if v:
            return v.lower()
    return ""


def _matches(label: str, hints: tuple[str, ...]) -> bool:
    return any(h in label for h in hints)


def detect_named_layers(model: WorkingSVG) -> Selection | None:
    """Auto-assign icon/wordmark from named groups, or None if not confident."""
    icon_group: etree._Element | None = None
    word_group: etree._Element | None = None
    for g in model.root.iter():
        if local_name(g) not in ("g", "layer"):
            continue
        label = _label_of(g)
        if not label:
            continue
        if icon_group is None and _matches(label, _ICON_HINTS):
            icon_group = g
        elif word_group is None and _matches(label, _WORD_HINTS):
            word_group = g

    if icon_group is None:
        return None

    ink = {n.lpid for n in model.ink_nodes}
    icon_ids = [i for i in _leaf_ids(icon_group) if i in ink]
    if not icon_ids:
        return None
    all_ids = [n.lpid for n in model.ink_nodes]
    icon_set = set(icon_ids)
    wordmark = [i for i in all_ids if i not in icon_set]
    return Selection(icon=icon_ids, wordmark=wordmark, source="named-layers",
                     overlap_warning=_overlap_warning(model, icon_ids, wordmark))


def _leaf_ids(group: etree._Element) -> list[str]:
    return [el.get(LPID_ATTR) for el in iter_leaves(group) if el.get(LPID_ATTR)]


def resolve(model: WorkingSVG,
            box: tuple[float, float, float, float] | None) -> Selection:
    """Prefer an explicit box; otherwise try named layers; else everything=icon
    is wrong, so default to all-as-wordmark with empty icon only if nothing
    else. In practice the API always supplies one of box/named-layers."""
    if box is not None:
        return select_by_box(model, box)
    named = detect_named_layers(model)
    if named is not None:
        return named
    # No box, no named layers: treat the whole artwork as a single (icon) group
    # so generation still produces a logo set; caller is expected to provide a
    # box for proper icon/wordmark separation.
    all_ids = [n.lpid for n in model.ink_nodes]
    return Selection(icon=all_ids, wordmark=[], source="box")


# --- integrated-lockup heuristic (§9) ---------------------------------------
def _overlap_warning(model: WorkingSVG, icon: list[str], wordmark: list[str]) -> bool:
    """Flag when icon & wordmark bounding boxes overlap a lot — a rectangle may
    not cleanly separate an integrated lockup (icon fused into a letter)."""
    if not icon or not wordmark:
        return False
    ib = model.overall_bbox(icon)
    wb = model.overall_bbox(wordmark)
    if not ib or not wb:
        return False
    ox = max(0.0, min(ib[2], wb[2]) - max(ib[0], wb[0]))
    oy = max(0.0, min(ib[3], wb[3]) - max(ib[1], wb[1]))
    inter = ox * oy
    icon_area = max(1e-6, (ib[2] - ib[0]) * (ib[3] - ib[1]))
    return inter / icon_area > 0.6
