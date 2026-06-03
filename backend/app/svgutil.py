"""Low-level SVG/lxml helpers: parsing, CSS-class fill resolution, and the
paint setter used by every treatment.

Design note: svgelements is used *only* for geometry (bbox/centroid). It
flattens gradient fills to black, so the fill model lives here, read directly
from the lxml tree + any ``<style>`` class rules.
"""
from __future__ import annotations

import re
from lxml import etree

from .config import SVG_NS

# Drawable leaf shapes we recolor / select. Containers (g, svg, defs) excluded.
LEAF_TAGS = {
    "path", "rect", "circle", "ellipse", "polygon", "polyline", "line",
}

_STYLE_RULE_RE = re.compile(r"([^{}]+)\{([^}]*)\}", re.S)


def parse_svg(data: bytes | str) -> etree._Element:
    """Parse SVG bytes/str into an lxml root element (huge_tree for big files)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    parser = etree.XMLParser(remove_blank_text=False, huge_tree=True, recover=True)
    return etree.fromstring(data, parser=parser)


def serialize(root: etree._Element) -> str:
    return etree.tostring(root, encoding="unicode")


def local_name(el: etree._Element) -> str:
    """Tag without namespace, e.g. '{...}path' -> 'path'."""
    tag = el.tag
    if not isinstance(tag, str):  # comments / PIs
        return ""
    return tag.rsplit("}", 1)[-1]


def qn(tag: str) -> str:
    """Qualified SVG tag name for element creation."""
    return f"{{{SVG_NS}}}{tag}"


def iter_leaves(root: etree._Element):
    """Yield every drawable leaf element in document order."""
    for el in root.iter():
        if local_name(el) in LEAF_TAGS:
            yield el


def parse_style_classes(root: etree._Element) -> dict[str, dict[str, str]]:
    """Collect ``.class { prop: val }`` rules from all ``<style>`` blocks.

    Returns ``{classname: {prop: value}}``. Multiple rules for the same class
    are merged (later wins), matching cascade order well enough for the simple
    stylesheets these logos use.
    """
    classes: dict[str, dict[str, str]] = {}
    for style_el in root.iter(qn("style")):
        css = style_el.text or ""
        for selectors, body in _STYLE_RULE_RE.findall(css):
            decls = _parse_decls(body)
            if not decls:
                continue
            for sel in selectors.split(","):
                sel = sel.strip()
                if sel.startswith("."):
                    classes.setdefault(sel[1:], {}).update(decls)
    return classes


def _parse_decls(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in body.split(";"):
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def style_dict(el: etree._Element) -> dict[str, str]:
    return _parse_decls(el.get("style", ""))


def _paint_for(el: etree._Element, prop: str,
               class_map: dict[str, dict[str, str]]) -> str | None:
    """Resolve a paint property ('fill'|'stroke') for a single element, without
    inheritance. Priority: inline style > presentation attr > class rule.
    Returns the authored string ('#ec1c24', 'url(#g1)', 'none', 'red') or None.
    """
    inline = style_dict(el).get(prop)
    if inline:
        return inline.strip()
    attr = el.get(prop)
    if attr:
        return attr.strip()
    cls = el.get("class")
    if cls:
        for name in cls.split():
            rule = class_map.get(name)
            if rule and prop in rule:
                return rule[prop].strip()
    return None


def effective_paint(el: etree._Element, prop: str,
                    class_map: dict[str, dict[str, str]],
                    parents: dict[etree._Element, etree._Element]) -> str | None:
    """Resolve 'fill'/'stroke' including inheritance up the ancestor chain.

    Returns the resolved authored string, or for ``fill`` the SVG default of
    black when nothing in the chain sets it (a path with no fill renders black).
    ``stroke`` defaults to None (no stroke).
    """
    node: etree._Element | None = el
    while node is not None:
        val = _paint_for(node, prop, class_map)
        if val is not None and val != "inherit":
            return val
        node = parents.get(node)
    return "#000000" if prop == "fill" else None


def build_parent_map(root: etree._Element) -> dict[etree._Element, etree._Element]:
    return {child: parent for parent in root.iter() for child in parent}


def set_paint(el: etree._Element, *, fill: str | None = None,
              stroke: str | None = None) -> None:
    """Force fill/stroke on an element via inline ``style`` (beats any class).

    ``None`` leaves a property unchanged; pass an explicit value (incl. 'none')
    to set it. Also clears a conflicting presentation attribute so the result is
    unambiguous when the SVG is opened in an editor.
    """
    decls = style_dict(el)
    if fill is not None:
        decls["fill"] = fill
        if el.get("fill") is not None:
            del el.attrib["fill"]
    if stroke is not None:
        decls["stroke"] = stroke
        if el.get("stroke") is not None:
            del el.attrib["stroke"]
    if decls:
        el.set("style", ";".join(f"{k}:{v}" for k, v in decls.items()))


def has_visible_stroke(el: etree._Element,
                       class_map: dict[str, dict[str, str]],
                       parents: dict[etree._Element, etree._Element]) -> bool:
    stroke = effective_paint(el, "stroke", class_map, parents)
    return stroke is not None and stroke.lower() != "none"
