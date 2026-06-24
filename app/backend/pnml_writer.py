"""Lay out a transformer-produced PNML and tidy it for clients.

The transformer returns a geometry-free PNML; :func:`assign_pnml_coordinates`
lays it out with the shared layout core (centre coordinates plus loop bend
points) and :func:`_clean_pnml` removes client-facing noise.
"""

import logging
import xml.etree.ElementTree as ET

from app.backend.layout_core import _route_edges, _sugiyama_layout

logger = logging.getLogger(__name__)

_PNML_PLACE_W, _PNML_PLACE_H = 50, 50
_PNML_TRANS_W, _PNML_TRANS_H = 50, 30

# Approximate glyph width (px) of WoPeD's small label font (~11px). Labels are
# drawn centred BELOW the node, so a column must reserve at least the label's
# width or adjacent labels overlap.
_LABEL_CHAR_PX = 7


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


def _label_width(elem, ns_prefix):
    """Estimate the rendered width (px) of a node's label from ``<name><text>``.

    WoPeD draws the name centred below the node, so a long name needs a wider
    column than the node box to keep it from overlapping its neighbours.
    Returns 0 for unnamed nodes (e.g. silent places).
    """
    name = elem.find(f"{ns_prefix}name")
    text = name.find(f"{ns_prefix}text") if name is not None else None
    if text is None or not text.text:
        return 0
    return len(text.text.strip()) * _LABEL_CHAR_PX


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

    # Collect all places and transitions from the entire tree (handles
    # nested <pnml><net><page>... hierarchies).
    elements_by_id: dict[str, dict] = {}
    elem_xml_map: dict[str, ET.Element] = {}

    for place in root.iter(f"{ns_prefix}place"):
        pid = place.get("id")
        if pid:
            w = max(_PNML_PLACE_W, _label_width(place, ns_prefix))
            elements_by_id[pid] = {"w": w, "h": _PNML_PLACE_H}
            elem_xml_map[pid] = place

    for trans in root.iter(f"{ns_prefix}transition"):
        tid = trans.get("id")
        if tid:
            w = max(_PNML_TRANS_W, _label_width(trans, ns_prefix))
            elements_by_id[tid] = {"w": w, "h": _PNML_TRANS_H}
            elem_xml_map[tid] = trans

    if not elements_by_id:
        return pnml_xml  # nothing to lay out

    arcs = [
        (arc, arc.get("source"), arc.get("target"))
        for arc in root.iter(f"{ns_prefix}arc")
        if arc.get("source") and arc.get("target")
    ]
    flows = [{"source": src, "target": tgt} for _, src, tgt in arcs]

    positions, ctx = _sugiyama_layout(
        elements_by_id, flows, h_gap=80, v_gap=50, x_offset=100, y_offset=100
    )

    for nid, pos in positions.items():
        elem = elem_xml_map.get(nid)
        if elem is None:
            continue

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

    # Route every back-edge (rework loop) through its own lane beneath the
    # diagram, mirroring the BPMN generator. Without explicit bend points each
    # client auto-routes the loop differently (a straight line back across the
    # columns), so the rendering is unstable across the fat client and web.
    # Forward arcs stay waypoint-free (loops_only); arcs and flows are aligned.
    routes = _route_edges(positions, ctx, flows, "loops_only")
    for idx, (arc, _src, _tgt) in enumerate(arcs):
        points = routes[idx]
        if not points:
            continue
        # Drop the first/last point: those are the node anchors WoPeD derives
        # itself; only the interior U-bend points are stored as bend points.
        _set_arc_waypoints(arc, points[1:-1], ns_prefix)

    # Tidy the PNML for clients (empty labels, empty markers, id="" noise).
    # Independent of layout, so kept out of the layout steps above.
    _clean_pnml(root, ns_prefix)

    ET.indent(ET.ElementTree(root), space="  ", level=0)
    return ET.tostring(root, encoding="unicode")


def _clean_pnml(root, ns_prefix):
    """Tidy the transformer's PNML for clients, independent of layout.

    Three client-facing fixes that are not geometry:

    * Anonymous nodes (silent/start/end places, operator helper transitions)
      carry no ``<name>``, so WoPeD would show the raw id ("SILENTFROMxTOy",
      ...) as a label. Give them an empty ``<name>`` so they render unlabelled.
    * The transformer marks every UserTask with a WoPeD
      ``<trigger>``/``<transitionResource>`` -- that marker is how the reverse
      (pnml->bpmn) direction tells a UserTask from a plain Task, so it is kept
      even with no role/orga. An EMPTY marker is meaningless to clients, so it
      (and any ``<toolspecific>`` left empty by it) is dropped.
    * pydantic-xml gives every element a default empty ``id=""``; real node/arc
      ids are never empty, so the noise ids are stripped.
    """
    nodes = list(root.iter(f"{ns_prefix}place")) + list(
        root.iter(f"{ns_prefix}transition")
    )
    for elem in nodes:
        name_el = elem.find(f"{ns_prefix}name")
        if name_el is None:
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
