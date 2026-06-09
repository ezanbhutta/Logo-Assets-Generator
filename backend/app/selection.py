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


def _largest_gap_split(model: WorkingSVG, nodes: list):
    """Split ``nodes`` at their largest centroid gap on BOTH axes (vertical for a
    stacked lockup, horizontal for a side-by-side one) and keep the split that
    yields the most icon-like mark: a compact/square cluster paired with a
    wide-and-short wordmark. Robust to the long axis being the *wordmark's*
    (e.g. a wide text row under a square emblem).

    Returns ``(icon_group, word_group, separation)`` where ``separation`` is the
    chosen gap divided by the median of the others — how clearly the icon is set
    apart (≈1 means evenly spaced like letters; ≫1 means a real emblem gap)."""
    pts = [n for n in nodes if n.bbox]
    if len(pts) < 2:
        return pts, [], 0.0
    best = None  # (score, icon, word, separation)
    for axis in (0, 1):
        ordered = sorted(pts, key=lambda n: n.centroid[axis])
        gaps = [ordered[i + 1].centroid[axis] - ordered[i].centroid[axis]
                for i in range(len(ordered) - 1)]
        gi = max(range(len(gaps)), key=lambda i: gaps[i])
        a, b = ordered[:gi + 1], ordered[gi + 1:]
        icon = a if _squareness(model, a) >= _squareness(model, b) else b
        word = b if icon is a else a
        others = gaps[:gi] + gaps[gi + 1:]
        med = sorted(others)[len(others) // 2] if others else gaps[gi]
        separation = gaps[gi] / max(med, 1e-6)
        score = _squareness(model, icon) - _squareness(model, word)
        if best is None or score > best[0]:
            best = (score, icon, word, separation)
    return best[1], best[2], best[3]


def auto_icon(model: WorkingSVG) -> Selection:
    """Guess the icon vs wordmark with no box. The icon set is never empty."""
    nodes = [n for n in model.ink_nodes if n.bbox]
    if len(nodes) < 2:
        return Selection(icon=[n.lpid for n in nodes], wordmark=[], source="auto")
    icon_group, _word, _sep = _largest_gap_split(model, nodes)
    icon = [n.lpid for n in icon_group]
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


# --- intelligent auto-segmentation: pre-fill the boxes like a designer ------
# Read the artboard the way a designer would: find the real logo lockup, set the
# icon apart, and ignore color swatches / stray duplicates. Everything here is a
# *suggestion* — the CSR reviews and adjusts the editable boxes; nothing ships
# on auto-detection alone.
SEG_GAP_K = 1.5              # cluster gap as a multiple of the median element size
SEG_REACH_K = 3.0            # how far an aligned piece can sit and still be lockup
_MIN_SWATCH_FRAC = 0.06      # a color chip's min side, as a fraction of min(viewbox)


@dataclass
class Suggestion:
    logo_box: tuple[float, float, float, float] | None  # None = whole artwork is the logo
    icon_box: tuple[float, float, float, float] | None  # None = no confident icon proposed
    note: str = ""
    excluded: int = 0          # nodes dropped as swatches / stray extras

    def as_dict(self) -> dict:
        return {
            "logo_box": list(self.logo_box) if self.logo_box else None,
            "icon_box": list(self.icon_box) if self.icon_box else None,
            "note": self.note,
            "excluded": self.excluded,
        }


def auto_segment(model: WorkingSVG) -> Suggestion | None:
    """Pre-fill the logo & icon boxes by reading the artboard like a designer.

    Handles the brand-sheet / bento case (one artboard carrying a logo lockup +
    a standalone icon + color swatches + variations) and the in-lockup case
    (icon derived from / set beside the wordmark). It proposes editable boxes:

    * **logo_box** carves the lockup out, excluding swatches and stray
      duplicates (``None`` when the whole artwork is already just the logo).
    * **icon_box** marks the icon — a square sub-region set apart inside the
      lockup, so the icon set can be generated separately (``None`` when there's
      no confident icon to propose).

    Returns ``None`` when there's nothing useful to suggest (e.g. a plain single
    wordmark), leaving the normal optional-icon flow untouched.
    """
    nodes = [n for n in model.ink_nodes if n.bbox]
    if len(nodes) < 2:
        return None
    vb = model.viewbox
    if not vb:
        return None
    minside = min(vb[2] - vb[0], vb[3] - vb[1])
    if minside <= 0:
        return None

    swatch_ids = _detect_swatches(nodes, minside)
    body = [n for n in nodes if n.lpid not in swatch_ids]
    if len(body) < 1:
        return None

    # Gap relative to the median element size — keeps a tight lockup whole while
    # separating far-apart pieces, and transfers between a small cropped lockup
    # and a sprawling brand sheet (a fixed viewbox fraction does not).
    sizes = sorted(max(n.bbox[2] - n.bbox[0], n.bbox[3] - n.bbox[1]) for n in body)
    med = sizes[len(sizes) // 2]
    if med <= 0:                                     # degenerate zero-size geometry
        return None
    clusters = _spatial_clusters(body, SEG_GAP_K * med)
    clusters.sort(key=lambda c: (len(c), _cluster_area(c)), reverse=True)

    # Assemble the lockup: start from the richest cluster (the wordmark spine —
    # most nodes) and pull in every nearby, aligned piece (a symbol that split
    # off the wordmark, a stacked emblem). Pieces that sit far away on their own
    # baseline (a duplicate icon, a stray mark on a brand sheet) stay out.
    main = clusters[0]
    lock_clusters = [main]
    used = {id(main)}
    reach = SEG_REACH_K * med
    changed = True
    while changed:
        changed = False
        lb = _bbox_of([n for c in lock_clusters for n in c])
        for c in clusters:
            if id(c) in used:
                continue
            if _box_gap(lb, _bbox_of(c)) <= reach and _aligned(lb, _bbox_of(c)):
                lock_clusters.append(c)
                used.add(id(c))
                changed = True
    lockup = [n for c in lock_clusters for n in c]
    extra_pieces = sum(len(c) for c in clusters if id(c) not in used)
    excluded = extra_pieces + len(swatch_ids)

    carved = len(lockup) < len(nodes)                # dropped swatches/extras?
    logo_box = _box_xywh(_bbox_of(lockup)) if carved else None

    icon_group = _lockup_icon(model, lockup, lock_clusters)
    icon_box = (_box_xywh(model.overall_bbox([n.lpid for n in icon_group]))
                if icon_group else None)

    if logo_box is None and icon_box is None:
        return None
    note = _segment_note(carved, len(swatch_ids), extra_pieces, icon_box is not None)
    return Suggestion(logo_box=logo_box, icon_box=icon_box, note=note, excluded=excluded)


def _aligned(a, b) -> bool:
    """True when two boxes share a horizontal or vertical band — i.e. they read
    as one lockup (icon beside, or stacked over, the wordmark). A duplicate off
    in its own corner shares neither and is left out."""
    return (min(a[2], b[2]) - max(a[0], b[0]) > 0) or (min(a[3], b[3]) - max(a[1], b[1]) > 0)


def _lockup_icon(model: WorkingSVG, lockup: list, lock_clusters: list):
    """Find the icon inside the assembled lockup. If the lockup is several
    pieces, the most-square piece is the icon; if it's one fused cluster, split
    it at the largest gap. Returns the icon nodes, or None if none is convincing."""
    if len(lock_clusters) >= 2:
        icon = max(lock_clusters, key=lambda c: _squareness(model, c))
        word = [n for c in lock_clusters if c is not icon for n in c]
        if word and _is_plausible_icon(model, lockup, icon, word, float("inf")):
            return icon
    icon_group, word_group, separation = _largest_gap_split(model, lockup)
    if _is_plausible_icon(model, lockup, icon_group, word_group, separation):
        return icon_group
    return None


def _detect_swatches(nodes: list, minside: float) -> set[str]:
    """Find color-swatch lpids: ≥3 mutually similar, blocky (square-ish),
    sizeable chips aligned in a row or column. A wordmark (varied, thin, small
    letters) and a lockup (a square icon among thin letters) both fail this —
    so the real logo is never mistaken for a palette."""
    chips = [n for n in nodes
             if _node_squareness(n) >= 0.55
             and min(n.bbox[2] - n.bbox[0], n.bbox[3] - n.bbox[1]) >= _MIN_SWATCH_FRAC * minside]
    best: set[str] = set()
    for anchor in chips:
        aw, ah = anchor.bbox[2] - anchor.bbox[0], anchor.bbox[3] - anchor.bbox[1]
        acx, acy = anchor.centroid
        peers = [m for m in chips
                 if max(anchor.area, m.area) / max(min(anchor.area, m.area), 1e-6) <= 1.8]
        row = [m for m in peers if abs(m.centroid[1] - acy) <= 0.6 * ah]
        col = [m for m in peers if abs(m.centroid[0] - acx) <= 0.6 * aw]
        for grp in (row, col):
            if len(grp) >= 3 and len(grp) > len(best):
                best = {n.lpid for n in grp}
    return best


def _spatial_clusters(nodes: list, gap: float) -> list[list]:
    """Union-find clustering: two nodes join if their bounding boxes sit within
    ``gap`` of each other. Keeps a tight lockup whole while separating far-apart
    pieces (a standalone icon, a swatch row, stray variations)."""
    parent = list(range(len(nodes)))

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if _box_gap(nodes[i].bbox, nodes[j].bbox) <= gap:
                parent[find(i)] = find(j)
    groups: dict[int, list] = {}
    for i, n in enumerate(nodes):
        groups.setdefault(find(i), []).append(n)
    return list(groups.values())


def _is_plausible_icon(model: WorkingSVG, lockup: list, icon_group: list,
                       word_group: list, separation: float) -> bool:
    """Only propose an icon when a compact, square-ish mark is genuinely set
    apart from a wordmark remainder — never carve a letter out of plain text."""
    if not icon_group or not word_group:
        return False                       # need a real wordmark left over
    lb, ib = _bbox_of(lockup), model.overall_bbox([n.lpid for n in icon_group])
    if not ib:
        return False
    lock_area = max(1e-6, (lb[2] - lb[0]) * (lb[3] - lb[1]))
    frac = ((ib[2] - ib[0]) * (ib[3] - ib[1])) / lock_area
    sq = _squareness(model, icon_group)
    if not (0.03 <= frac <= 0.85 and len(icon_group) <= len(word_group) + 1):
        return False
    # a very-square emblem qualifies on its own; a merely blocky one must be
    # clearly set apart (so evenly-spaced letters never read as an icon).
    return sq >= 0.75 or (sq >= 0.5 and separation >= 1.6)


def _segment_note(carved: bool, n_swatch: int, n_extra: int, has_icon: bool) -> str:
    parts: list[str] = []
    if carved:
        ex = []
        if n_swatch:
            ex.append(f"{n_swatch} color swatch" + ("es" if n_swatch != 1 else ""))
        if n_extra:
            ex.append(f"{n_extra} extra element" + ("s" if n_extra != 1 else ""))
        parts.append("Carved the logo out of the artboard"
                     + (f" — excluded {' and '.join(ex)}." if ex else "."))
    if has_icon:
        parts.append("Marked a likely icon inside the logo.")
    parts.append("Adjust the boxes if needed.")
    return " ".join(parts)


# -- small geometry helpers --------------------------------------------------
def _box_gap(a, b) -> float:
    """Distance between two axis-aligned boxes (0 if touching/overlapping)."""
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return max(dx, dy)


def _bbox_of(nodes: list):
    boxes = [n.bbox for n in nodes if n.bbox]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _box_xywh(bb) -> tuple[float, float, float, float]:
    return (round(bb[0], 2), round(bb[1], 2),
            round(bb[2] - bb[0], 2), round(bb[3] - bb[1], 2))


def _cluster_area(nodes: list) -> float:
    bb = _bbox_of(nodes)
    return (bb[2] - bb[0]) * (bb[3] - bb[1])


def _node_squareness(n) -> float:
    w, h = n.bbox[2] - n.bbox[0], n.bbox[3] - n.bbox[1]
    return min(w, h) / max(w, h, 1e-6)
