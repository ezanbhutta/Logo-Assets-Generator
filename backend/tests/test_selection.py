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
