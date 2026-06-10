"""§7.3 / §8 rule 3 — centroid-in-box selection, whole-path snapping."""
from app import selection


def test_box_selects_icon_only(solid_model):
    sel = selection.select_by_box(solid_model, (10, 5, 150, 150))
    assert len(sel.icon) == 1           # the flame path
    assert len(sel.wordmark) == 10      # remainder = every other path
    assert set(sel.full) == {n.lpid for n in solid_model.nodes}


def test_wordmark_is_remainder_no_second_drag(solid_model):
    sel = selection.select_by_box(solid_model, (10, 5, 150, 150))
    assert set(sel.icon).isdisjoint(sel.wordmark)
    assert len(sel.icon) + len(sel.wordmark) == len(solid_model.nodes)


def test_whole_path_snapping_partial_box(solid_model):
    """A box that only partially overlaps a path still snaps by centroid — the
    path is never split (§8 rule 3)."""
    # Tiny box near the flame's top; the flame centroid (~85,70) is outside it,
    # so the flame is NOT selected — proving membership is centroid-based,
    # not geometric clipping.
    sel = selection.select_by_box(solid_model, (60, 10, 20, 10))
    for lpid in sel.icon:
        c = solid_model.by_lpid[lpid].centroid
        assert 60 <= c[0] <= 80 and 10 <= c[1] <= 20


def test_named_layer_autodetect(solid_model):
    named = selection.detect_named_layers(solid_model)
    assert named is not None
    assert named.source == "named-layers"
    assert len(named.icon) == 1 and len(named.wordmark) == 10


def test_box_and_named_layers_agree(solid_model):
    box = selection.select_by_box(solid_model, (10, 5, 150, 150))
    named = selection.detect_named_layers(solid_model)
    assert set(box.icon) == set(named.icon)


def test_auto_icon_extracts_the_mark(solid_model):
    """No box: spatial clustering picks the (square-ish) flame as the icon."""
    auto = selection.auto_icon(solid_model)
    assert auto.source == "auto"
    assert len(auto.icon) == 1            # the flame
    assert len(auto.wordmark) == 10       # the wordmark rects


def test_auto_icon_stacked_lockup_picks_top_emblem():
    """Stacked lockup (square emblem ON TOP of a WIDE text row): the overall
    artwork is wider than tall, so a naive long-axis split fails — the emblem
    must still win (the Ironclad case)."""
    from app.svg_model import WorkingSVG
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 300">']
    parts.append('<circle cx="300" cy="80" r="44" fill="#333"/>')        # emblem (top)
    for i, x in enumerate(range(60, 541, 60)):                            # wide text row
        parts.append(f'<rect x="{x}" y="232" width="34" height="34" fill="#333"/>')
    parts.append('</svg>')
    m = WorkingSVG.from_string("".join(parts))
    auto = selection.auto_icon(m)
    ib = m.overall_bbox(auto.icon)
    assert len(auto.icon) == 1            # just the emblem
    assert ib[3] < 150                    # icon lives in the TOP half, not the text row


def test_resolve_falls_back_when_box_misses(solid_model):
    """A box that captures no icon paths must NOT yield a blank icon — it falls
    back (named layers here; auto extraction when there are none) (§3.4)."""
    miss = selection.resolve(solid_model, (10000, 10000, 5, 5))  # off-artwork box
    assert miss.icon                       # never empty
    assert miss.source != "box"            # didn't ship the empty box result


def test_two_box_carves_bento():
    """A brand-sheet / bento (logo + standalone icon + color swatches): the logo
    box carves the real logo (swatches excluded) and the icon box marks the icon."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">'
           '<path d="M120,70 L150,140 L100,160 Z" fill="#ec1c24"/>'       # logo flame
           '<rect x="180" y="90" width="60" height="20" fill="#112630"/>'  # wordmark
           '<rect x="260" y="90" width="60" height="20" fill="#112630"/>'
           '<path d="M740,70 L770,140 L720,160 Z" fill="#ec1c24"/>'       # standalone icon
           '<rect x="60" y="420" width="120" height="120" fill="#ec1c24"/>'   # swatches
           '<rect x="220" y="420" width="120" height="120" fill="#112630"/>'
           '<rect x="380" y="420" width="120" height="120" fill="#000000"/></svg>')
    m = WorkingSVG.from_string(svg)
    assert len(m.ink_nodes) == 7
    sel, include_icon = selection.select(m, logo_box=(50, 50, 330, 170),
                                         icon_box=(90, 55, 80, 120))
    assert len(sel.full) == 3          # logo lockup only (3 swatches + extra icon excluded)
    assert len(sel.icon) == 1          # the flame in the lockup
    assert len(sel.wordmark) == 2
    assert include_icon is True


def test_select_no_boxes_is_whole_artwork():
    sel, include_icon = selection.select(WorkingSVG_for(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="10" y="10" width="30" height="30" fill="#ec1c24"/>'
        '<rect x="60" y="60" width="30" height="30" fill="#112630"/></svg>'))
    assert len(sel.full) == 2 and include_icon is False   # logo-only, whole artwork


def WorkingSVG_for(svg):
    from app.svg_model import WorkingSVG
    return WorkingSVG.from_string(svg)


def test_resolve_auto_when_no_named_layers():
    """With neither a usable box nor named layers, auto extraction kicks in."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120">'
           '<circle cx="60" cy="60" r="34" fill="#c8a04a"/>'         # icon (left)
           '<rect x="150" y="50" width="40" height="20" fill="#111"/>'  # word (right)
           '<rect x="200" y="50" width="40" height="20" fill="#111"/>'
           '<rect x="250" y="50" width="40" height="20" fill="#111"/></svg>')
    sel = selection.resolve(WorkingSVG.from_string(svg), (9999, 9999, 1, 1))
    assert sel.source == "auto" and sel.icon


def test_resolve_uses_valid_box(solid_model):
    sel = selection.resolve(solid_model, (10, 5, 150, 150))
    assert sel.source == "box" and len(sel.icon) == 1


# --- intelligent auto-segmentation ------------------------------------------
def _bento_svg():
    """A brand sheet: a logo lockup (emblem + 5 wordmark letters) top-left, a
    standalone duplicate icon top-right, and a 4-chip color palette at the
    bottom. A pro should carve the lockup out and mark the emblem."""
    from app.svg_model import WorkingSVG
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">']
    parts.append('<circle cx="90" cy="110" r="40" fill="#7229ff"/>')        # emblem
    for i, x in enumerate(range(170, 291, 30)):                              # wordmark (5)
        parts.append(f'<rect x="{x}" y="95" width="24" height="30" fill="#160a33"/>')
    parts.append('<circle cx="700" cy="110" r="40" fill="#7229ff"/>')       # standalone dup
    for x in (60, 180, 300, 420):                                           # color swatches
        parts.append(f'<rect x="{x}" y="460" width="80" height="80" fill="#160a33"/>')
    parts.append('</svg>')
    return WorkingSVG.from_string("".join(parts))


def test_auto_segment_carves_bento_and_marks_icon():
    m = _bento_svg()
    assert len(m.ink_nodes) == 11
    seg = selection.auto_segment(m)
    assert seg is not None
    assert seg.logo_box is not None and seg.icon_box is not None
    assert seg.excluded == 5                      # 4 swatches + 1 standalone dup
    # The suggested boxes, fed back through select(), isolate the lockup + emblem.
    sel, include_icon = selection.select(m, logo_box=tuple(seg.logo_box),
                                         icon_box=tuple(seg.icon_box))
    assert include_icon is True
    assert len(sel.full) == 6                     # emblem + 5 letters, no swatches/dup
    assert len(sel.icon) == 1                     # the emblem
    assert len(sel.wordmark) == 5


def test_auto_segment_single_lockup_marks_icon_no_carve():
    """A plain icon+wordmark lockup (no bento): nothing to carve, but the emblem
    is set apart so it's pre-marked as the icon (the 'check them separately'
    case)."""
    from app.svg_model import WorkingSVG
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 160">']
    parts.append('<circle cx="40" cy="80" r="30" fill="#7229ff"/>')         # emblem
    for x in (90, 114, 138, 162):                                           # wordmark
        parts.append(f'<rect x="{x}" y="60" width="18" height="40" fill="#160a33"/>')
    parts.append('</svg>')
    m = WorkingSVG.from_string("".join(parts))
    seg = selection.auto_segment(m)
    assert seg is not None
    assert seg.logo_box is None                   # nothing extra to exclude
    assert seg.icon_box is not None
    sel, include_icon = selection.select(m, logo_box=None, icon_box=tuple(seg.icon_box))
    assert include_icon is True
    assert len(sel.icon) == 1 and len(sel.wordmark) == 4


def test_logo_box_keeps_descender_letters():
    """A box drawn near the x-height baseline must still keep a 'y'/'g'/'p' whose
    descender pulls its centroid below the other letters — the Tays 'y' bug,
    where a hand-drawn logo box dropped the y and shipped 'ta s'."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
           '<rect x="40" y="70" width="20" height="30" fill="#111"/>'    # t  c=(50,85)
           '<rect x="70" y="70" width="20" height="30" fill="#111"/>'    # a  c=(80,85)
           '<rect x="100" y="70" width="20" height="55" fill="#111"/>'   # y  c=(110,97.5) descender
           '<rect x="130" y="70" width="20" height="30" fill="#111"/></svg>')  # s  c=(140,85)
    m = WorkingSVG.from_string(svg)
    # box hugging the x-height (y 68..92): the y's centroid (97.5) sits below it
    sel, _ = selection.select(m, logo_box=(30, 68, 120, 24), icon_box=None)
    assert len(sel.full) == 4                     # all four, incl. the descender 'y'


def test_logo_box_keeps_detached_trailing_period():
    """A wordmark's trailing period/sparkle is a SEPARATE path sitting in a gap
    after the last letter. A CSR draws the logo box around the visible letters
    and stops at the 's'; the floating '.' lands just outside. It must still be
    kept — the Tays 'tays.' bug, where the period (a star-dot) was dropped and
    'tays' shipped without it."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
           '<rect x="40"  y="70" width="22" height="40" fill="#111"/>'   # t
           '<rect x="72"  y="70" width="22" height="40" fill="#111"/>'   # a
           '<rect x="104" y="70" width="22" height="40" fill="#111"/>'   # y
           '<rect x="136" y="70" width="22" height="40" fill="#111"/>'   # s  right edge = 158
           '<rect x="170" y="100" width="9" height="9" fill="#111"/></svg>')  # period c=(174.5,104.5)
    m = WorkingSVG.from_string(svg)
    # box ends at x=160, just past the 's' — the period (centroid 174.5) is outside
    sel, _ = selection.select(m, logo_box=(30, 60, 130, 60), icon_box=None)
    assert len(sel.full) == 5                     # the detached period is reattached
    # the smallest node (the period) is the one that was rescued
    period = min(m.ink_nodes, key=lambda n: n.area)
    assert period.lpid in set(sel.full)


def test_icon_box_excludes_backing_tile():
    """A standalone icon often sits alone on its own presentation tile. That tile
    backs only the one mark, so the old 'panel backs >=2' rule let it slip through
    and the icon box captured the whole tile — shipping a filled rectangle instead
    of a clean mark (the Tays 't' icon came out as a black box). The tile has a
    same-size peer (the wordmark's tile), which is the real giveaway, so it must
    be dropped from the icon."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">'
           '<rect x="40"  y="40" width="400" height="300" fill="#fdf6ec"/>'   # wordmark tile
           '<rect x="100" y="160" width="40" height="60" fill="#111"/>'       # wordmark (3)
           '<rect x="160" y="160" width="40" height="60" fill="#111"/>'
           '<rect x="220" y="160" width="40" height="60" fill="#111"/>'
           '<rect x="560" y="40" width="400" height="300" fill="#fdf6ec"/>'   # icon tile (backs 1)
           '<rect x="720" y="140" width="80" height="120" fill="#111"/></svg>')  # the icon mark
    m = WorkingSVG.from_string(svg)
    sel, include_icon = selection.select(m, logo_box=(40, 40, 420, 310),
                                         icon_box=(580, 60, 360, 260))
    assert include_icon is True
    assert len(sel.icon) == 1                     # just the mark, not the tile behind it
    assert len(sel.full) == 3                     # wordmark lockup; the icon is a standalone mark
    vb_area = 1000 * 600
    assert all(n.area < 0.08 * vb_area            # nothing tile-sized leaked into the icon
               for n in m.ink_nodes if n.lpid in set(sel.icon))


def test_use_text_is_flattened_and_excludable():
    """pdf2svg renders text as <use> of glyph defs. Those must be inlined so the
    text is tracked geometry that a logo box can exclude — otherwise a brand
    sheet's body copy leaks into every export (the Tays bug)."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
           'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 400 200">'
           '<defs><path id="g" d="M0,0 H8 V10 H0 Z"/></defs>'
           '<rect x="20" y="20" width="40" height="40" fill="#7229ff"/>'   # the logo
           '<use xlink:href="#g" x="20" y="160"/>'                         # body text (bottom)
           '<use xlink:href="#g" x="40" y="160"/>'
           '<use xlink:href="#g" x="60" y="160"/></svg>')
    m = WorkingSVG.from_string(svg)
    assert "<use" not in m.serialize()              # flattened away
    assert len(m.ink_nodes) == 4                     # square + 3 inlined glyph paths
    sel, _ = selection.select(m, logo_box=(10, 10, 60, 60), icon_box=None)
    assert len(sel.full) == 1                        # only the square; the text is excluded


def test_repeated_tiles_are_excluded_as_panels():
    """A brand sheet lays the logo on repeated tiles. Those panels are scaffolding
    — a logo box over a tile must yield the lockup, never the tile rectangle."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">'
           '<rect x="40" y="40" width="400" height="300" fill="#f0ece0"/>'     # tile A
           '<rect x="540" y="40" width="400" height="300" fill="#f0ece0"/>'    # tile B (peer)
           '<rect x="120" y="150" width="60" height="60" fill="#7229ff"/>'     # icon on A
           '<rect x="200" y="165" width="30" height="30" fill="#160a33"/>'     # wordmark on A
           '<rect x="260" y="165" width="30" height="30" fill="#160a33"/>'
           '<rect x="620" y="150" width="60" height="60" fill="#7229ff"/>'        # dup icon on B
           '<rect x="700" y="165" width="28" height="30" fill="#160a33"/></svg>')  # + its mark
    m = WorkingSVG.from_string(svg)
    panels = selection._panel_ids(m.ink_nodes, m.viewbox)
    assert len(panels) == 2                           # both tiles flagged
    sel, _ = selection.select(m, logo_box=(100, 140, 200, 80), icon_box=None)
    assert all(p not in sel.full for p in panels)     # no tile rectangle in the logo
    assert len(sel.full) == 3                          # icon + 2 wordmark marks


def _bento_with_standalone_icon():
    """Brand-sheet: wordmark on its tile (left) + a standalone icon on its own
    tile (right) — the Tays layout."""
    from app.svg_model import WorkingSVG
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">'
           '<rect x="40"  y="40" width="400" height="300" fill="#fdf6ec"/>'   # wordmark tile
           '<rect x="100" y="160" width="40" height="60" fill="#111"/>'       # wordmark (3)
           '<rect x="160" y="160" width="40" height="60" fill="#111"/>'
           '<rect x="220" y="160" width="40" height="60" fill="#111"/>'
           '<rect x="560" y="40" width="400" height="300" fill="#fdf6ec"/>'   # icon tile
           '<rect x="720" y="140" width="80" height="120" fill="#111"/></svg>')  # standalone icon
    return WorkingSVG.from_string(svg)


def test_missed_icon_box_yields_no_icon_not_a_wordmark_slice():
    """An explicit icon box that lands on empty space must produce NO icon — it
    must never silently carve a mark out of the wordmark. That was the Tays bug:
    the CSR boxed the standalone 't.' but a near/total miss made the engine ship
    letters sliced from 'tays' as the icon instead of the icon they chose."""
    m = _bento_with_standalone_icon()
    wordmark_ids = {n.lpid for n in m.ink_nodes
                    if n.bbox and n.bbox[0] < 300 and n.area < 0.08 * 1000 * 600}
    sel, include_icon = selection.select(
        m, logo_box=(40, 40, 420, 310), icon_box=(450, 450, 100, 100))  # empty corner
    assert include_icon is False                  # no icon, not a wrong one
    assert sel.icon == []
    assert wordmark_ids.isdisjoint(sel.icon)      # the wordmark was NOT carved up
    assert len(sel.full) == 3                     # logo set intact


def test_near_miss_icon_box_still_grabs_standalone_mark():
    """A loosely-drawn icon box whose centre falls just off the small standalone
    mark still selects it (forgiving overlap retry), rather than dropping to no
    icon — so a slightly-imprecise drag around the 't.' still ships the icon."""
    m = _bento_with_standalone_icon()
    # box clips the left ~44% of the icon (720..800); its centre (≈760) sits
    # outside the box, so plain centroid/coverage misses but overlap catches it.
    sel, include_icon = selection.select(
        m, logo_box=(40, 40, 420, 310), icon_box=(700, 140, 55, 120))
    assert include_icon is True
    assert len(sel.icon) == 1
    icon_node = m.by_lpid[sel.icon[0]]
    assert icon_node.bbox[0] >= 700             # it's the right-hand standalone mark


def test_auto_segment_plain_wordmark_suggests_nothing():
    """Evenly-spaced letters with no emblem: never carve a letter out as a fake
    icon — return None and leave the normal flow alone."""
    from app.svg_model import WorkingSVG
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 80">']
    for x in (20, 50, 80, 110, 140):
        parts.append(f'<rect x="{x}" y="20" width="18" height="40" fill="#160a33"/>')
    parts.append('</svg>')
    m = WorkingSVG.from_string("".join(parts))
    assert selection.auto_segment(m) is None
