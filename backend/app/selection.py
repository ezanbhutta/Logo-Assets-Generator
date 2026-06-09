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


def _squareness(model: WorkingSVG, group: list) -> float:
    b = model.overall_bbox([n.lpid for n in group])
    if not b:
        return 0.0
    w, h = b[2] - b[0], b[3] - b[1]
    return min(w, h) / max(w, h, 1e-6)       # 1.0 == perfectly square


def auto_icon(model: WorkingSVG) -> Selection:
    """Guess the icon vs wordmark with no box. Try splitting the lockup at its
    largest gap on BOTH axes (vertical for a stacked lockup, horizontal for a
    side-by-side one) and keep the split that yields the most icon-like mark:
    a compact/square cluster paired with a wide-and-short wordmark. Robust to
    the long axis being the *wordmark's* (e.g. a wide text row under a square
    emblem). The icon set is never empty.
    """
    nodes = [n for n in model.ink_nodes if n.bbox]
    if len(nodes) < 2:
        return Selection(icon=[n.lpid for n in nodes], wordmark=[], source="auto")

    best = None  # (score, icon_group)
    for axis in (0, 1):
        ordered = sorted(nodes, key=lambda n: n.centroid[axis])
        gi = max(range(len(ordered) - 1),
                 key=lambda i: ordered[i + 1].centroid[axis] - ordered[i].centroid[axis])
        a, b = ordered[:gi + 1], ordered[gi + 1:]
        icon_group = a if _squareness(model, a) >= _squareness(model, b) else b
        word_group = b if icon_group is a else a
        # reward a square icon next to a wide wordmark.
        score = _squareness(model, icon_group) - _squareness(model, word_group)
        if best is None or score > best[0]:
            best = (score, icon_group)

    icon = [n.lpid for n in best[1]]
    icon_set = set(icon)
    wordmark = [n.lpid for n in model.ink_nodes if n.lpid not in icon_set]
    return Selection(icon=icon, wordmark=wordmark, source="auto",
                     overlap_warning=_overlap_warning(model, icon, wordmark))


def resolve(model: WorkingSVG,
            box: tuple[float, float, float, float] | None) -> Selection:
    """Prefer an explicit box; if it (or the absence of one) yields no icon,
    fall back to named layers, then to auto_icon — so the icon set is never
    empty (§3.4: selection is the fallback, not the only path)."""
    if box is not None:
        sel = select_by_box(model, box)
        if sel.icon:
            return sel
        # box captured no icon paths -> auto-extract instead of shipping blanks.
    named = detect_named_layers(model)
    if named is not None and named.icon:
        return named
    return auto_icon(model)


# --- two-box selection: logo region + icon region ---------------------------
def _in_box(centroid, box) -> bool:
    if centroid is None or box is None:
        return False
    x, y, w, h = box
    return x <= centroid[0] <= x + w and y <= centroid[1] <= y + h


def select(model: WorkingSVG,
           logo_box: tuple[float, float, float, float] | None = None,
           icon_box: tuple[float, float, float, float] | None = None):
    """Resolve the logo region AND the icon region.

    * **logo** = paths inside ``logo_box`` (or all artwork if none). This lets the
      CSR carve the real logo out of a brand-sheet / bento that also contains an
      icon, color swatches, and variations — everything outside the box is
      ignored.
    * **icon** = paths inside ``icon_box`` (restricted to the logo); falls back to
      named layers, then auto-extraction, only if a box misses. Optional.

    Returns ``(Selection, include_icon)``. ``Selection.full`` (icon+wordmark) is
    the logo region, so the logo set is generated from just that.
    """
    ink = model.ink_nodes
    logo_ids = [n.lpid for n in ink
                if logo_box is None or _in_box(n.centroid, logo_box)]
    if not logo_ids:                       # box missed everything -> whole artwork
        logo_ids = [n.lpid for n in ink]
    logo_set = set(logo_ids)

    icon_ids: list[str] = []
    source = "none"
    if icon_box is not None:
        icon_ids = [n.lpid for n in ink
                    if n.lpid in logo_set and _in_box(n.centroid, icon_box)]
        source = "box"
        if not icon_ids:                   # box missed -> named/auto within the logo
            icon_ids, source = _icon_fallback(model, logo_set)
    else:
        cand = _named_in(model, logo_set)
        if cand:
            icon_ids, source = cand, "named-layers"

    wordmark = [i for i in logo_ids if i not in set(icon_ids)]
    sel = Selection(icon=icon_ids, wordmark=wordmark, source=source,
                    overlap_warning=_overlap_warning(model, icon_ids, wordmark))
    return sel, bool(icon_ids)


def _named_in(model: WorkingSVG, logo_set: set[str]) -> list[str]:
    named = detect_named_layers(model)
    if named is not None and named.icon:
        return [i for i in named.icon if i in logo_set]
    return []


def _icon_fallback(model: WorkingSVG, logo_set: set[str]):
    cand = _named_in(model, logo_set)
    if cand:
        return cand, "named-layers"
    auto = [i for i in auto_icon(model).icon if i in logo_set]
    return (auto, "auto") if auto else ([], "none")


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
