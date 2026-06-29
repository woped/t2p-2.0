"""Lay out a transformer-produced PNML.

The transformer returns a geometry-free PNML; :func:`assign_pnml_coordinates`
lays it out with the shared layout core (centre coordinates plus arc waypoints
for rework-loop back-edges and multi-layer arcs) and :func:`_clean_pnml` strips
the noise it leaves behind.
"""

import logging
import xml.etree.ElementTree as ET

from app.backend.layout_core import _route_edges, _sugiyama_layout

logger = logging.getLogger(__name__)

# PNML node sizes are layout-internal only (we emit no <dimension>; PNML clients
# render at their own fixed size). They mirror the rendering clients' footprint
# so our spacing matches what is drawn: place 50x50 = woped-next VISUAL.place
# (radius 25 -> 50 diameter); transition 40x30 = woped-next VISUAL.transition.
_PNML_PLACE_W, _PNML_PLACE_H = 50, 50
_PNML_TRANS_W, _PNML_TRANS_H = 40, 30

# Pessimistic glyph width (px) per label character, grounded in the PNML clients'
# label fonts: WoPeD Fat Client uses Verdana 11 (DEFAULT_LABEL_FONT), woped-next
# 12px. Labels render centred BELOW the node, so under-reserving makes adjacent
# labels overlap -- worse than a slightly loose layout. We reserve a capital's
# advance of the larger font (12px, cap ~0.72 em ~= 8.6 px) rounded up, so even
# an all-caps label does not collide; normal mixed-case text is over-reserved.
_LABEL_CHAR_PX = 9


def _set_arc_waypoints(arc_el, points, ns_prefix):
    """Write *points* as intermediate ``<graphics><position>`` bend points on an
    ``<arc>``.

    WoPeD reads each ``<position>`` as an absolute-canvas bend point between the
    arc's (implicit) source and target anchors, so only the interior points are
    written -- the endpoints are derived from the node positions by the client.
    """
    graphics = arc_el.find(f"{ns_prefix}graphics")
    if graphics is None:
        graphics = ET.SubElement(arc_el, f"{ns_prefix}graphics")
    for px, py in points:
        ET.SubElement(
            graphics,
            f"{ns_prefix}position",
            attrib={"x": str(int(round(px))), "y": str(int(round(py)))},
        )


def _label_text(elem, ns_prefix):
    """Return the node's label from ``<name><text>``, or '' if it is unnamed."""
    name = elem.find(f"{ns_prefix}name")
    text = name.find(f"{ns_prefix}text") if name is not None else None
    return text.text if (text is not None and text.text) else ""


def _extract_graph(root, ns_prefix):
    """Read the raw graph from the PNML tree -- topology only.

    Walks the whole tree (nested ``<pnml><net><page>...`` hierarchies included).
    Returns ``(nodes, edges)``: nodes as ``{id, element}``, edges as
    ``{source, target, element}``. The size inputs (kind, label) are derived from
    the element later, in :func:`_node_sizes`.
    """
    nodes: list[dict] = []
    for kind in ("place", "transition"):
        for el in root.iter(f"{ns_prefix}{kind}"):
            nid = el.get("id")
            if nid:
                nodes.append({"id": nid, "element": el})
    edges = [
        {"source": arc.get("source"), "target": arc.get("target"), "element": arc}
        for arc in root.iter(f"{ns_prefix}arc")
        if arc.get("source") and arc.get("target")
    ]
    return nodes, edges


_PNML_BASE = {
    "place": (_PNML_PLACE_W, _PNML_PLACE_H),
    "transition": (_PNML_TRANS_W, _PNML_TRANS_H),
}


def _node_sizes(nodes, ns_prefix):
    """Box ``{w, h}`` per node: base size by kind (the element's tag), widened to
    fit the label so a long name does not overlap (WoPeD draws it below the node).
    """
    sizes: dict[str, dict] = {}
    for n in nodes:
        base_w, base_h = _PNML_BASE[n["element"].tag.rpartition("}")[2]]
        label = _label_text(n["element"], ns_prefix)
        sizes[n["id"]] = {
            "w": max(base_w, len(label.strip()) * _LABEL_CHAR_PX),
            "h": base_h,
        }
    return sizes


def assign_pnml_coordinates(pnml_xml):
    """Parse a PNML XML string and assign proper layout coordinates to all
    places and transitions.

    Uses the same layered layout algorithm as the BPMN generator.  In PNML,
    ``<graphics><position>`` holds *centre* coordinates, so positions returned
    by ``_sugiyama_layout`` (top-left) are shifted by half the element size.

    Back-edges (rework loops) are routed the same way as in BPMN: each gets its
    own horizontal lane beneath the diagram, written as ``<arc>`` bend points,
    so loops do not depend on each client's own arc routing (which differs and
    would otherwise cut a straight line back across the columns).

    If *pnml_xml* is not valid XML the original string is returned unchanged.

    Args:
        pnml_xml: PNML XML string (with or without ``<?xml ...?>`` declaration).

    Returns:
        Updated PNML XML string.
    """
    if not pnml_xml or not isinstance(pnml_xml, str):
        return pnml_xml

    try:
        root = ET.fromstring(pnml_xml)
    except ET.ParseError:
        logger.warning("assign_pnml_coordinates: not valid XML – layout skipped")
        return pnml_xml

    # Detect Clark-notation namespace prefix, e.g. '{http://www.pnml.org/...}'.
    raw_tag = root.tag
    ns_prefix = (
        "{" + raw_tag[1 : raw_tag.index("}")] + "}" if raw_tag.startswith("{") else ""
    )

    # Register the namespace so ET.tostring() preserves the default namespace.
    if ns_prefix:
        ET.register_namespace("", ns_prefix[1:-1])

    nodes, edges = _extract_graph(root, ns_prefix)
    if not nodes:
        return pnml_xml  # nothing to lay out

    elements_by_id = _node_sizes(nodes, ns_prefix)
    positions, ctx = _sugiyama_layout(
        elements_by_id, edges, h_gap=80, v_gap=50, x_offset=100, y_offset=100
    )

    for node in nodes:
        elem = node["element"]
        pos = positions[node["id"]]

        # PNML <position> stores centre coordinates.
        cx = pos["x"] + pos["w"] // 2
        cy = pos["y"] + pos["h"] // 2

        graphics = elem.find(f"{ns_prefix}graphics")
        if graphics is None:
            graphics = ET.SubElement(elem, f"{ns_prefix}graphics")

        position_el = graphics.find(f"{ns_prefix}position")
        if position_el is None:
            position_el = ET.SubElement(graphics, f"{ns_prefix}position")
        position_el.set("x", str(cx))
        position_el.set("y", str(cy))

    # Route loops (own lane beneath the diagram) and multi-layer forward arcs
    # (orthogonally, so they do not cut across the columns between); adjacent-
    # layer arcs stay straight -- correct and native for PNML, and the client
    # draws that line itself. Only the interior bend points are written below.
    routes = _route_edges(positions, ctx, edges, "sparse")
    for idx, edge in enumerate(edges):
        points = routes[idx]
        if not points:
            continue
        # Drop the first/last point: those are the node anchors WoPeD derives
        # itself; only the interior U-bend points are stored as bend points.
        _set_arc_waypoints(edge["element"], points[1:-1], ns_prefix)

    # Put one token in the source place so the output is a complete workflow net
    # (van der Aalst: one token in the unique source) that WoPeD can play/analyse.
    _set_initial_marking(nodes, edges, ns_prefix)

    # Strip transformer noise (empty resource markers, id="" defaults) for a
    # cleaner standard net. Independent of layout, kept out of the steps above.
    _clean_pnml(root, ns_prefix)

    ET.indent(ET.ElementTree(root), space="  ", level=0)
    return ET.tostring(root, encoding="unicode")


def _set_initial_marking(nodes, edges, ns_prefix):
    """Put one token in the source place (no incoming arc).

    A workflow net is defined with a single token in its unique source place; a
    net without it is structurally complete but "not started", so WoPeD cannot
    play the token game or run soundness on it. Only marked when there is exactly
    one source -- a malformed multi-source net is left alone rather than guessed.
    """
    targets = {e["target"] for e in edges}
    sources = [
        n["element"]
        for n in nodes
        if n["element"].tag.rpartition("}")[2] == "place" and n["id"] not in targets
    ]
    if len(sources) != 1:
        return
    place = sources[0]
    marking = place.find(f"{ns_prefix}initialMarking")
    if marking is None:
        marking = ET.SubElement(place, f"{ns_prefix}initialMarking")
    text = marking.find(f"{ns_prefix}text")
    if text is None:
        text = ET.SubElement(marking, f"{ns_prefix}text")
    text.text = "1"


def _clean_pnml(root, ns_prefix):
    """Tidy the transformer's PNML for clients:

    * Anonymous nodes (silent places, operator helper transitions) carry no
      ``<name>``, so WoPeD's Fat Client falls back to showing the raw id
      ("SILENTFROMxTOy", "g1_op_1", ...) as a long, overlapping label. Give them
      an empty ``<name>`` so they render unlabelled instead.
    * The transformer marks every UserTask with a WoPeD
      ``<trigger>``/``<transitionResource>`` -- that marker is how the reverse
      (pnml->bpmn) direction tells a UserTask from a plain Task, so it is kept
      even with no role/orga. An EMPTY marker carries no information, so it (and
      any ``<toolspecific>`` left empty by it) is dropped.
    * pydantic-xml gives every element a default empty ``id=""``; real node/arc
      ids are never empty, so the noise ids are stripped.
    """
    nodes = list(root.iter(f"{ns_prefix}place")) + list(
        root.iter(f"{ns_prefix}transition")
    )
    for elem in nodes:
        # Empty <name> for unnamed nodes so the Fat Client renders them blank
        # instead of their raw id (the "Textbrei" overlap bug).
        if elem.find(f"{ns_prefix}name") is None:
            name_el = ET.Element(f"{ns_prefix}name")
            ET.SubElement(name_el, f"{ns_prefix}text").text = ""
            elem.insert(0, name_el)

        for ts in elem.findall(f"{ns_prefix}toolspecific"):
            trigger = ts.find(f"{ns_prefix}trigger")
            resource = ts.find(f"{ns_prefix}transitionResource")
            resource_empty = resource is not None and not (
                resource.get("roleName") or resource.get("organizationalUnitName")
            )
            if trigger is not None and trigger.get("type") == "200" and resource_empty:
                ts.remove(trigger)
                ts.remove(resource)
            if not any(
                ts.find(f"{ns_prefix}{tag}") is not None
                for tag in ("operator", "trigger", "transitionResource", "subprocess")
            ):
                elem.remove(ts)

    for el in root.iter():
        if el.get("id") == "":
            del el.attrib["id"]
