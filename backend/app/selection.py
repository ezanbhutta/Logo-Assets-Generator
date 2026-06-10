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
    icon: list[str]        # the icon set (may be a standalone mark, sitting outside the logo)
    logo: list[str]        # the logo lockup region — what the logo files render
    source: str            # 'box' | 'named-layers' | 'auto'
    overlap_warning: bool = False  # icon & wordmark bboxes overlap heavily (§9 integrated lockup)

    @property
    def full(self) -> list[str]:
        """The logo set (the lockup). The icon is delivered separately and may be
        a standalone mark that is not part of this set."""
        return self.logo

    @property
    def wordmark(self) -> list[str]:
        """The logo minus the icon — the parts that go white in the split
        treatment. Equals the whole logo when the icon is a standalone mark."""
        ic = set(self.icon)
        return [i for i in self.logo if i not in ic]


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
    return Selection(icon=icon, logo=icon + wordmark, source="box",
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
    return Selection(icon=icon_ids, logo=all_ids, source="named-layers",
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
        ids = [n.lpid for n in nodes]
        return Selection(icon=ids, logo=ids, source="auto")
    icon_group, _word, _sep = _largest_gap_split(model, nodes)
    icon = [n.lpid for n in icon_group]
    icon_set = set(icon)
    all_ids = [n.lpid for n in model.ink_nodes]
    wordmark = [i for i in all_ids if i not in icon_set]
    return Selection(icon=icon, logo=all_ids, source="auto",
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


def _covered(node, box) -> bool:
    """Is ``node`` part of the marked region? A glyph counts when its centroid is
    inside the box OR most of it is covered — the box spans ≥60% of its width and
    ≥30% of its height. The forgiving height keeps descenders/ascenders (a 'y',
    'g', 'p') whose centroid dips below the others from being dropped when the CSR
    draws a box near the baseline; the width test still rejects neighbors that the
    box only clips, and a mark on another line (≈0 vertical overlap) stays out."""
    if box is None or node.bbox is None or node.centroid is None:
        return False
    x, y, w, h = box
    cx, cy = node.centroid
    if x <= cx <= x + w and y <= cy <= y + h:
        return True
    bx0, by0, bx1, by1 = node.bbox
    nw, nh = bx1 - bx0, by1 - by0
    if nw <= 0 or nh <= 0:
        return False
    ox = max(0.0, min(bx1, x + w) - max(bx0, x))
    oy = max(0.0, min(by1, y + h) - max(by0, y))
    return ox / nw >= 0.6 and oy / nh >= 0.3


def _overlaps_box(node, box, frac: float = 0.3) -> bool:
    """A looser test than ``_covered``: True when ``box`` covers at least ``frac``
    of the node's area. Used only as a near-miss retry for an explicit icon box,
    so a rectangle that clips most of a small standalone mark still selects it —
    while a box drawn on empty space (overlapping nothing) still selects nothing."""
    if box is None or node.bbox is None:
        return False
    x, y, w, h = box
    bx0, by0, bx1, by1 = node.bbox
    ox = max(0.0, min(bx1, x + w) - max(bx0, x))
    oy = max(0.0, min(by1, y + h) - max(by0, y))
    narea = max(1e-6, (bx1 - bx0) * (by1 - by0))
    return (ox * oy) / narea >= frac


def _attach_punct(pool: list, ids: list[str]) -> list[str]:
    """Pull a small, detached punctuation-like mark — a period, a sparkle-dot, an
    accent — into a box selection when it floats right against the selected glyphs
    on the same line. A CSR drawing the logo box around ``tays`` stops at the
    ``s``; the period just past it is a *separate* path with a kerning gap before
    it, so it would otherwise be dropped — losing the ``.`` that is part of the
    wordmark. Only marks clearly smaller than the glyphs, sitting on the same
    line and within ~one glyph of the run, are pulled in; neighbours, body copy,
    and a mark on another line stay out."""
    have = set(ids)
    chosen = [n for n in pool if n.lpid in have and n.bbox]
    if not chosen:
        return ids
    sb = _bbox_of(chosen)
    mh = _median_height(chosen)
    if mh <= 0:
        return ids
    extra: list[str] = []
    for n in pool:
        if n.lpid in have or not n.bbox:
            continue
        if max(n.bbox[2] - n.bbox[0], n.bbox[3] - n.bbox[1]) > 0.7 * mh:
            continue                                   # bigger than punctuation -> a glyph
        cx, cy = n.centroid
        if not (sb[1] - 0.15 * mh <= cy <= sb[3] + 0.15 * mh):
            continue                                   # off this line
        gap = max(sb[0] - n.bbox[2], n.bbox[0] - sb[2], 0.0)
        if gap <= 0.8 * mh:                            # snug against the run, left or right
            extra.append(n.lpid)
    return ids + extra


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
    # Drop presentation panels — repeated large rectangles that merely back the
    # artwork (the cream/dark tiles on a brand sheet). They are scaffolding, not
    # logo ink, so a logo box drawn over a tile yields the lockup, not the tile.
    panels = _panel_ids(ink, model.viewbox)
    pool = [n for n in ink if n.lpid not in panels] or ink
    logo_ids = [n.lpid for n in pool
                if logo_box is None or _covered(n, logo_box)]
    if not logo_ids:                       # box missed everything -> whole artwork
        logo_ids = [n.lpid for n in pool]
    elif logo_box is not None:             # keep a trailing period/sparkle on the wordmark
        logo_ids = _attach_punct(pool, logo_ids)
    logo_set = set(logo_ids)

    icon_ids: list[str] = []
    source = "none"
    if icon_box is not None:
        # The icon box is independent of the logo box: it may mark a sub-region
        # of the lockup OR a standalone mark elsewhere on the sheet (an icon
        # derived from the wordmark, shown on its own tile). Either way the icon
        # files come from exactly what the box covers.
        icon_ids = [n.lpid for n in pool if _covered(n, icon_box)]
        if not icon_ids:
            # Forgiving near-miss: a box that still overlaps a mark grabs it, so a
            # slightly-loose rectangle around a small standalone icon selects it
            # rather than nothing.
            icon_ids = [n.lpid for n in pool if _overlaps_box(n, icon_box)]
        source = "box"
        # An explicit icon box that lands on no artwork yields NO icon. We never
        # silently auto-carve one from the wordmark on a miss — that shipped a
        # mark the CSR never chose (the standalone icon they boxed was discarded
        # in favour of letters sliced out of the wordmark). An empty result is the
        # honest signal to redraw the box.
    else:
        cand = _named_in(model, logo_set)
        if cand:
            icon_ids, source = cand, "named-layers"

    wordmark = [i for i in logo_ids if i not in set(icon_ids)]
    sel = Selection(icon=icon_ids, logo=logo_ids, source=source,
                    overlap_warning=_overlap_warning(model, icon_ids, wordmark))
    return sel, bool(icon_ids)


def _named_in(model: WorkingSVG, logo_set: set[str]) -> list[str]:
    named = detect_named_layers(model)
    if named is not None and named.icon:
        return [i for i in named.icon if i in logo_set]
    return []


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
SEG_MAX_NODES = 2000         # above this, skip auto-segment (O(n²)); manual still works
SEG_GAP_K = 1.5              # cluster gap as a multiple of the median element size
SEG_REACH_K = 3.0            # how far an aligned piece can sit and still be lockup
_MIN_SWATCH_FRAC = 0.06      # a color chip's min side, as a fraction of min(viewbox)
PANEL_MIN_FRAC = 0.08        # a panel's area, as a fraction of the whole artboard


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
    if len(nodes) < 2 or len(nodes) > SEG_MAX_NODES:
        return None                                  # too few, or too many to cluster cheaply
    vb = model.viewbox
    if not vb:
        return None
    minside = min(vb[2] - vb[0], vb[3] - vb[1])
    if minside <= 0:
        return None

    # Exclude scaffolding before clustering: color swatches (palette chips) and
    # presentation panels (the repeated tiles a brand sheet lays the logo on).
    drop = _detect_swatches(nodes, minside) | _panel_ids(nodes, vb)
    body = [n for n in nodes if n.lpid not in drop]
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

    # The primary lockup is the cluster with the strongest WORDMARK — a row of
    # several similar-height marks (the brand name). Picking by wordmark, not raw
    # node count or area, ignores a big standalone icon and a block of body copy
    # (which has many but tiny glyphs). Ties (a brand sheet repeats the lockup in
    # several colorways) break toward the top-most, left-most one — reading order.
    top = max((_wordmark_score(c) for c in clusters), default=0.0)
    if top > 0:
        main = min((c for c in clusters if _wordmark_score(c) >= top - 1e-6),
                   key=lambda c: (_bbox_of(c)[1], _bbox_of(c)[0]))
    else:
        main = max(clusters, key=lambda c: (len(c), _cluster_area(c)))

    # Assemble the lockup: pull in every nearby, aligned piece (a symbol that
    # split off the wordmark, a stacked emblem). Far-off pieces on their own
    # baseline (a standalone icon, a recolored duplicate) stay out, and fine
    # print / body copy under the wordmark (much shorter than it) is never a
    # lockup member — that's what swallowed the whole brand-sheet before.
    lock_clusters = [main]
    used = {id(main)}
    reach = SEG_REACH_K * med
    min_h = 0.5 * _median_height(main)
    changed = True
    while changed:
        changed = False
        lb = _bbox_of([n for c in lock_clusters for n in c])
        for c in clusters:
            if id(c) in used or _median_height(c) < min_h:
                continue
            if _box_gap(lb, _bbox_of(c)) <= reach and _aligned(lb, _bbox_of(c)):
                lock_clusters.append(c)
                used.add(id(c))
                changed = True
    lockup = [n for c in lock_clusters for n in c]
    excluded = len(nodes) - len(lockup)              # panels, swatches, text, dups

    carved = len(lockup) < len(nodes)
    logo_box = _box_xywh(_bbox_of(lockup)) if carved else None

    # The icon: first try inside the lockup (a symbol set apart from the
    # wordmark). If the lockup is wordmark-only, look for a STANDALONE icon — a
    # compact, square-ish mark on its own elsewhere on the sheet (the brand's
    # letter-mark shown by itself, e.g. a "t." beside a "tays" wordmark).
    icon_group = _lockup_icon(model, lockup, lock_clusters)
    if icon_group:
        icon_box = _box_xywh(model.overall_bbox([n.lpid for n in icon_group]))
    else:
        lb = _bbox_of(lockup)
        max_side = 1.5 * max(lb[2] - lb[0], lb[3] - lb[1])
        icon_box = _standalone_icon(model, clusters, used, _median_height(main), max_side)

    if logo_box is None and icon_box is None:
        return None
    note = _segment_note(carved, excluded, icon_box is not None)
    return Suggestion(logo_box=logo_box, icon_box=icon_box, note=note, excluded=excluded)


def _aligned(a, b) -> bool:
    """True when two boxes share a horizontal or vertical band — i.e. they read
    as one lockup (icon beside, or stacked over, the wordmark). A duplicate off
    in its own corner shares neither and is left out."""
    return (min(a[2], b[2]) - max(a[0], b[0]) > 0) or (min(a[3], b[3]) - max(a[1], b[1]) > 0)


def _lockup_icon(model: WorkingSVG, lockup: list, lock_clusters: list):
    """Find an emblem inside the assembled lockup. If the lockup is several
    pieces, the most-square piece is the icon. If it's one fused row, the icon is
    a compact, SQUARE, full-height mark set apart at one end (a leaf before a
    wordmark) — never a slice of the letters. Returns the icon nodes, or None."""
    if len(lock_clusters) >= 2:
        icon = max(lock_clusters, key=lambda c: _squareness(model, c))
        word = [n for c in lock_clusters if c is not icon for n in c]
        if word and _is_plausible_icon(model, lockup, icon, word, float("inf")):
            return icon
        return None

    pts = sorted([n for n in lockup if n.bbox], key=lambda n: n.centroid[0])
    if len(pts) < 3:
        return None
    for from_left in (True, False):
        grp = _end_emblem(pts, from_left)
        rest = [n for n in pts if n not in grp]
        if not rest:
            continue
        gb = _bbox_of(grp)
        sq = min(gb[2] - gb[0], gb[3] - gb[1]) / max(gb[2] - gb[0], gb[3] - gb[1], 1e-6)
        letter_h = _median_height(rest)
        emblem_h = gb[3] - gb[1]
        # square, at least as tall as the wordmark (rules out a sparkle/period),
        # and parted from the letters by clearly more than the inter-letter gap.
        if sq < 0.7 or emblem_h < 0.6 * letter_h:
            continue
        gaps = _adjacent_x_gaps(rest)
        med_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
        part = (rest[0].bbox[0] - gb[2]) if from_left else (gb[0] - rest[-1].bbox[2])
        if med_gap > 0 and part < 1.3 * med_gap:
            continue
        if _is_plausible_icon(model, lockup, grp, rest, part / max(med_gap, 1e-6)):
            return grp
    return None


def _end_emblem(pts: list, from_left: bool) -> list:
    """Grow a group inward from one end of an x-sorted row while the parts keep
    overlapping in x — i.e. the stacked pieces of a single emblem — then stop at
    the first gap (the start of the wordmark)."""
    seq = pts if from_left else list(reversed(pts))
    grp = [seq[0]]
    lo, hi = seq[0].bbox[0], seq[0].bbox[2]
    for n in seq[1:]:
        if n.bbox[0] <= hi and n.bbox[2] >= lo:
            grp.append(n)
            lo, hi = min(lo, n.bbox[0]), max(hi, n.bbox[2])
        else:
            break
    return grp


def _adjacent_x_gaps(pts: list) -> list:
    """Edge-to-edge horizontal gaps between consecutive marks (not centroid
    distances) — the real whitespace between letters, so an emblem parted from
    the wordmark reads as a wider gap than the kerning between letters."""
    s = sorted((n for n in pts if n.bbox), key=lambda n: n.bbox[0])
    return [max(0.0, s[i + 1].bbox[0] - s[i].bbox[2]) for i in range(len(s) - 1)]


def _standalone_icon(model: WorkingSVG, clusters: list, used: set,
                     main_h: float, max_side: float):
    """Among the leftover clusters, find a standalone icon: a compact, square-ish
    mark on its own (not a text row, not fine print, not a bar, not a giant
    panel). Returns its box, or None. This covers the brand-sheet case where the
    icon is the brand's letter-mark shown by itself, apart from the wordmark."""
    best = None  # (squareness, cluster)
    for c in clusters:
        if id(c) in used or _wordmark_score(c) > 0:   # the lockup, a dup wordmark, body copy
            continue
        if _median_height(c) < 0.6 * main_h:           # fine print
            continue
        bb = _bbox_of(c)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        if max(w, h) > max_side:                        # bigger than the logo -> a tile, not an icon
            continue
        sq = min(w, h) / max(w, h, 1e-6)
        if sq < 0.45:                                  # a bar / underline, not an icon
            continue
        if best is None or sq > best[0]:
            best = (sq, c)
    return _box_xywh(_bbox_of(best[1])) if best else None


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


def _panel_ids(nodes: list, viewbox) -> set[str]:
    """Find presentation **panels** — the repeated tiles a brand sheet lays each
    logo variation on. A panel is a large element that (a) backs ≥1 other mark
    (its centroid sits on the tile) and (b) has a similar-size large peer
    elsewhere.

    The peer requirement is the safety catch: a *single* logo never duplicates
    its own backing shape, so a lone large shape (e.g. Orova's gear carrying its
    circuitry) is never mistaken for scaffolding — only repeated tiles are. The
    backing test only needs ≥1 mark because a standalone **icon** often sits
    alone on its own tile (the tile backs just the one mark); requiring ≥2 missed
    that tile and leaked it into the icon files as a filled rectangle."""
    if not viewbox:
        return set()
    vb_area = (viewbox[2] - viewbox[0]) * (viewbox[3] - viewbox[1])
    if vb_area <= 0:
        return set()
    large = [n for n in nodes if n.bbox and n.area >= PANEL_MIN_FRAC * vb_area]
    panels: set[str] = set()
    for n in large:
        backs = sum(1 for m in nodes if m is not n and m.bbox
                    and n.bbox[0] <= m.centroid[0] <= n.bbox[2]
                    and n.bbox[1] <= m.centroid[1] <= n.bbox[3])
        if backs < 1:
            continue
        if any(m is not n and 0.77 <= n.area / max(m.area, 1e-6) <= 1.3 for m in large):
            panels.add(n.lpid)
    return panels


def _wordmark_score(cluster: list) -> float:
    """Prominence of the strongest horizontal TEXT ROW in a cluster — the median
    height of a baseline-aligned run of ≥3 similar-height marks (the brand name).
    Scoring by height, not count, means the main wordmark beats tiny body copy
    (short) and a tall standalone icon scores 0 (only 1–2 marks, no run). Used to
    pick the primary lockup among everything on a brand sheet."""
    pts = [n for n in cluster if n.bbox]
    best = 0.0
    for a in pts:
        ah = a.bbox[3] - a.bbox[1]
        band = [m for m in pts
                if abs(m.centroid[1] - a.centroid[1]) <= 0.6 * max(ah, 1e-6)
                and 0.4 <= (m.bbox[3] - m.bbox[1]) / max(ah, 1e-6) <= 2.5]
        if len(band) >= 3:
            heights = sorted(m.bbox[3] - m.bbox[1] for m in band)
            best = max(best, heights[len(heights) // 2])
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


def _segment_note(carved: bool, excluded: int, has_icon: bool) -> str:
    parts: list[str] = []
    if carved and excluded:
        parts.append(
            f"Carved the logo out of the artboard — excluded {excluded} other "
            f"element{'s' if excluded != 1 else ''} (tiles, swatches, text, duplicates).")
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


def _median_height(nodes: list) -> float:
    hs = sorted(n.bbox[3] - n.bbox[1] for n in nodes if n.bbox)
    return hs[len(hs) // 2] if hs else 0.0
