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


def test_resolve_falls_back_when_box_misses(solid_model):
    """A box that captures no icon paths must NOT yield a blank icon — it falls
    back (named layers here; auto extraction when there are none) (§3.4)."""
    miss = selection.resolve(solid_model, (10000, 10000, 5, 5))  # off-artwork box
    assert miss.icon                       # never empty
    assert miss.source != "box"            # didn't ship the empty box result


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
