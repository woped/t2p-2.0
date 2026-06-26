import xml.etree.ElementTree as ET

import pytest
from app.backend.xml_parser import (
    assign_pnml_coordinates,
    json_to_bpmn,
    PnmlStructureError,
    repair_pnml_connectivity_from_bpmn,
    sanitize_bpmn_for_transform,
    validate_pnml_connectivity,
)

_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"


def _parse(result):
    """Parse the generated BPMN, asserting it is well-formed, and return root."""
    return ET.fromstring(result)


def _local_counts(root):
    """Count elements by their namespace-stripped local tag name."""
    counts = {}
    for el in root.iter():
        local = el.tag.split("}")[-1]
        counts[local] = counts.get(local, 0) + 1
    return counts


@pytest.fixture
def example_data():
    return {
        "events": [
            {"id": "startEvent1", "type": "Start", "name": "Process Start"},
            {"id": "endEvent1", "type": "End", "name": "Process End"},
        ],
        "tasks": [
            {"id": "task1", "name": "Check for Known Outages", "type": "ServiceTask"}
        ],
        "gateways": [],
        "flows": [
            {
                "id": "flow1",
                "source": "startEvent1",
                "target": "task1",
                "type": "SequenceFlow",
            },
            {
                "id": "flow2",
                "source": "task1",
                "target": "endEvent1",
                "type": "SequenceFlow",
            },
        ],
        "participants": [],
    }


def test_json_to_bpmn_generates_xml(example_data):
    result = json_to_bpmn(example_data)

    # Prüfen, ob der Output ein gültiger XML-String ist
    assert isinstance(result, str)
    assert "<?xml" in result
    assert "<definitions" in result  # nicht mehr '<bpmn:definitions'
    assert "startEvent1" in result
    assert "task1" in result
    assert "endEvent1" in result


def test_json_to_bpmn_accepts_connector_event_type_names(example_data):
    example_data["events"][0]["type"] = "startEvent"
    example_data["events"][1]["type"] = "endEvent"

    result = json_to_bpmn(example_data)

    assert "<startEvent" in result
    assert "<endEvent" in result
    assert "intermediateCatchEvent" not in result


def test_json_to_bpmn_with_gateways():
    """Test BPMN generation with gateways"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"},
        ],
        "tasks": [{"id": "task1", "name": "Task 1", "type": "UserTask"}],
        "gateways": [
            {"id": "gateway1", "type": "ExclusiveGateway", "name": "Decision"}
        ],
        "flows": [
            {
                "id": "flow1",
                "source": "start1",
                "target": "task1",
                "type": "SequenceFlow",
            },
            {
                "id": "flow2",
                "source": "task1",
                "target": "gateway1",
                "type": "SequenceFlow",
            },
            {
                "id": "flow3",
                "source": "gateway1",
                "target": "end1",
                "type": "SequenceFlow",
            },
        ],
    }

    result = json_to_bpmn(data)

    assert "gateway1" in result
    assert "ExclusiveGateway" in result or "exclusiveGateway" in result


def test_json_to_bpmn_with_multiple_tasks():
    """Test BPMN generation with multiple tasks"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"},
        ],
        "tasks": [
            {"id": "task1", "name": "Task 1", "type": "ServiceTask"},
            {"id": "task2", "name": "Task 2", "type": "UserTask"},
            {"id": "task3", "name": "Task 3", "type": "ManualTask"},
        ],
        "gateways": [],
        "flows": [
            {
                "id": "flow1",
                "source": "start1",
                "target": "task1",
                "type": "SequenceFlow",
            },
            {
                "id": "flow2",
                "source": "task1",
                "target": "task2",
                "type": "SequenceFlow",
            },
            {
                "id": "flow3",
                "source": "task2",
                "target": "task3",
                "type": "SequenceFlow",
            },
            {
                "id": "flow4",
                "source": "task3",
                "target": "end1",
                "type": "SequenceFlow",
            },
        ],
    }

    result = json_to_bpmn(data)

    assert "task1" in result
    assert "task2" in result
    assert "task3" in result
    assert "Task 1" in result
    assert "Task 2" in result
    assert "Task 3" in result


def test_json_to_bpmn_with_parallel_gateway():
    """Test BPMN generation with parallel gateway"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"},
        ],
        "tasks": [{"id": "task1", "name": "Task 1", "type": "UserTask"}],
        "gateways": [{"id": "gateway1", "type": "ParallelGateway", "name": "Split"}],
        "flows": [
            {
                "id": "flow1",
                "source": "start1",
                "target": "gateway1",
                "type": "SequenceFlow",
            },
            {
                "id": "flow2",
                "source": "gateway1",
                "target": "task1",
                "type": "SequenceFlow",
            },
            {
                "id": "flow3",
                "source": "task1",
                "target": "end1",
                "type": "SequenceFlow",
            },
        ],
    }

    result = json_to_bpmn(data)

    assert "gateway1" in result
    assert "ParallelGateway" in result or "parallelGateway" in result


def test_json_to_bpmn_empty_arrays():
    """Test BPMN generation with minimal data"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": ""},
            {"id": "end1", "type": "End", "name": ""},
        ],
        "tasks": [],
        "gateways": [],
        "flows": [
            {
                "id": "flow1",
                "source": "start1",
                "target": "end1",
                "type": "SequenceFlow",
            }
        ],
    }

    result = json_to_bpmn(data)

    assert isinstance(result, str)
    assert "<?xml" in result
    assert "start1" in result
    assert "end1" in result


def test_cyclic_process_lays_out_every_node_and_flow():
    """A process containing a rework loop must still produce a complete diagram.

    The layout does a topological sort; nodes inside a cycle never reach
    in-degree zero, so they exit the sort unplaced. The fallback must still
    assign them positions, otherwise the diagram step looks up a missing
    position and the whole conversion crashes. Expected behaviour: every node
    gets a shape and every flow gets an edge, regardless of cycles.
    """
    data = {
        "events": [
            {"id": "start", "type": "Start", "name": "Start"},
            {"id": "end", "type": "End", "name": "End"},
        ],
        "tasks": [
            {"id": "review", "name": "Review", "type": "UserTask"},
            {"id": "rework", "name": "Rework", "type": "UserTask"},
        ],
        "gateways": [],
        "flows": [
            {"id": "f1", "source": "start", "target": "review"},
            {"id": "f2", "source": "review", "target": "rework"},
            {"id": "f3", "source": "rework", "target": "review"},  # back-edge (loop)
            {"id": "f4", "source": "review", "target": "end"},
        ],
    }

    root = _parse(json_to_bpmn(data))
    counts = _local_counts(root)

    # One shape per node (2 events + 2 tasks) and one edge per flow (4).
    assert counts.get("BPMNShape") == 4
    assert counts.get("BPMNEdge") == 4
    assert counts.get("sequenceFlow") == 4
    for node_id in ("start", "end", "review", "rework"):
        assert node_id in json_to_bpmn(data)


def test_empty_model_produces_wellformed_empty_diagram():
    """A model with no nodes or flows is degenerate but must not crash.

    Expected behaviour: a parseable document with an empty process and no
    shapes or edges, rather than an exception from the layout's empty case.
    """
    data = {"events": [], "tasks": [], "gateways": [], "flows": []}

    root = _parse(json_to_bpmn(data))
    counts = _local_counts(root)

    assert counts.get("process") == 1
    assert counts.get("BPMNShape", 0) == 0
    assert counts.get("BPMNEdge", 0) == 0


def test_special_characters_in_names_produce_wellformed_xml():
    """Element names come from an LLM and may contain XML metacharacters.

    Expected behaviour: the output is always well-formed XML with the name
    correctly escaped/round-tripped, never a broken document that splices the
    raw '&' or '<' into the markup.
    """
    data = {
        "events": [
            {"id": "start", "type": "Start", "name": "Start"},
            {"id": "end", "type": "End", "name": "End"},
        ],
        "tasks": [{"id": "t1", "name": 'R&D <review> "now"', "type": "UserTask"}],
        "gateways": [],
        "flows": [
            {"id": "f1", "source": "start", "target": "t1"},
            {"id": "f2", "source": "t1", "target": "end"},
        ],
    }

    root = _parse(json_to_bpmn(data))

    names = {el.get("name") for el in root.iter() if el.get("name") is not None}
    assert 'R&D <review> "now"' in names


def test_unknown_event_type_maps_to_intermediate_catch_event():
    """Any event type that is not a start/end variant falls back to an
    intermediate catch event rather than producing an invalid tag."""
    data = {
        "events": [
            {"id": "start", "type": "Start", "name": "Start"},
            {"id": "timer", "type": "TimerEvent", "name": "Wait"},
            {"id": "end", "type": "End", "name": "End"},
        ],
        "tasks": [],
        "gateways": [],
        "flows": [
            {"id": "f1", "source": "start", "target": "timer"},
            {"id": "f2", "source": "timer", "target": "end"},
        ],
    }

    counts = _local_counts(_parse(json_to_bpmn(data)))
    assert counts.get("intermediateCatchEvent") == 1
    assert counts.get("startEvent") == 1
    assert counts.get("endEvent") == 1


def test_assign_pnml_coordinates_lays_out_each_node():
    """The transformer returns PNML with placeholder coordinates; the post-step
    must lay the net out so every place/transition gets its own
    <graphics><position> rather than all overlapping at one point."""
    pnml = (
        "<pnml><net id='n1' type='http://www.pnml.org/version-2009/grammar/pnmlcoremodel'>"
        "<place id='p1'/>"
        "<transition id='t1'/>"
        "<place id='p2'/>"
        "<arc id='a1' source='p1' target='t1'/>"
        "<arc id='a2' source='t1' target='p2'/>"
        "</net></pnml>"
    )

    root = ET.fromstring(assign_pnml_coordinates(pnml))

    coords = {}
    for node in root.iter():
        if node.tag.split("}")[-1] in ("place", "transition"):
            position = node.find("graphics/position")
            assert position is not None, f"{node.get('id')} got no position"
            coords[node.get("id")] = (position.get("x"), position.get("y"))

    # Every node is positioned, and the layered layout spreads them out
    # (not all stacked on the same placeholder coordinate).
    assert set(coords) == {"P1", "t1", "P2"}
    assert len(set(coords.values())) == 3


def test_assign_pnml_coordinates_passes_through_non_xml():
    """A non-XML payload (e.g. a transformer error string) is returned as-is."""
    assert assign_pnml_coordinates("not xml") == "not xml"


def test_assign_pnml_coordinates_renames_places_and_normalizes_transition_labels():
    """PNML post-processing renames places to Pn and strips task-type label
    prefixes from transitions."""
    pnml = (
        "<pnml><net id='n1'>"
        "<place id='startEvent1'/>"
        "<transition id='task1'><name><text>[UserTask] Receive Bike and Deposit</text></name></transition>"
        "<place id='SILENTFROMtask1TOtask2'/>"
        "<transition id='task2'><name><text>[ServiceTask] Perform Repairs</text></name></transition>"
        "<arc id='a1' source='startEvent1' target='task1'/>"
        "<arc id='a2' source='task1' target='SILENTFROMtask1TOtask2'/>"
        "<arc id='a3' source='SILENTFROMtask1TOtask2' target='task2'/>"
        "</net></pnml>"
    )

    root = ET.fromstring(assign_pnml_coordinates(pnml))

    place_ids = [
        node.get("id")
        for node in root.iter()
        if node.tag.split("}")[-1] == "place"
    ]
    assert place_ids == ["P1", "P2"]

    transitions = {
        node.get("id"): node.find("name/text").text
        for node in root.iter()
        if node.tag.split("}")[-1] == "transition"
    }
    assert transitions["task1"] == "receive bike and deposit"
    assert transitions["task2"] == "perform repairs"

    arcs = [
        (arc.get("source"), arc.get("target"))
        for arc in root.iter()
        if arc.tag.split("}")[-1] == "arc"
    ]
    assert ("P1", "task1") in arcs
    assert ("task1", "P2") in arcs
    assert ("P2", "task2") in arcs


def test_assign_pnml_coordinates_enforces_transition_place_adjacency_and_no_orphans():
    """Transition-to-transition links are bridged by places and isolated nodes
    are removed from the PNML net."""
    pnml = (
        "<pnml><net id='n1'>"
        "<place id='orphanPlace'/>"
        "<transition id='t1'/>"
        "<transition id='t2'/>"
        "<place id='p3'/>"
        "<arc id='a1' source='t1' target='t2'/>"
        "<arc id='a2' source='p3' target='t1'/>"
        "</net></pnml>"
    )

    root = ET.fromstring(assign_pnml_coordinates(pnml))

    place_ids = {
        node.get("id")
        for node in root.iter()
        if node.tag.split("}")[-1] == "place" and node.get("id")
    }
    transition_ids = {
        node.get("id")
        for node in root.iter()
        if node.tag.split("}")[-1] == "transition" and node.get("id")
    }

    arcs = [
        (arc.get("source"), arc.get("target"))
        for arc in root.iter()
        if arc.tag.split("}")[-1] == "arc"
    ]

    assert "orphanPlace" not in place_ids

    # No direct transition->transition or place->place arcs should remain.
    for source, target in arcs:
        assert not (source in transition_ids and target in transition_ids)
        assert not (source in place_ids and target in place_ids)

    # Every transition must have a place either before or after it.
    adjacency = {transition_id: False for transition_id in transition_ids}
    for source, target in arcs:
        if source in transition_ids and target in place_ids:
            adjacency[source] = True
        if source in place_ids and target in transition_ids:
            adjacency[target] = True
    assert all(adjacency.values())


# ---------------------------------------------------------------------------
# validate_pnml_connectivity
# ---------------------------------------------------------------------------


def _simple_pnml(transitions_and_arcs):
    """Build a minimal PNML string from a list of (id, [inbound places], [outbound places])
    tuples so individual validator tests need not repeat boilerplate."""
    parts = ["<pnml><net id='n1'>"]
    places = set()
    for tid, ins, outs in transitions_and_arcs:
        parts.append(f"<transition id='{tid}'/>")
        places.update(ins)
        places.update(outs)
    for pid in sorted(places):
        parts.append(f"<place id='{pid}'/>")
    arc_id = 0
    for tid, ins, outs in transitions_and_arcs:
        for pid in ins:
            parts.append(f"<arc id='a{arc_id}' source='{pid}' target='{tid}'/>")
            arc_id += 1
        for pid in outs:
            parts.append(f"<arc id='a{arc_id}' source='{tid}' target='{pid}'/>")
            arc_id += 1
    parts.append("</net></pnml>")
    return "".join(parts)


def test_validate_pnml_connectivity_accepts_regular_transition():
    """A transition with exactly one inbound and one outbound arc is valid."""
    pnml = _simple_pnml([("t1", ["p_in"], ["p_out"])])
    validate_pnml_connectivity(pnml)  # must not raise


def test_validate_pnml_connectivity_accepts_split_gateway():
    """A split gateway transition (one inbound, multiple outbound) is valid."""
    pnml = _simple_pnml([("split", ["p_in"], ["p_out1", "p_out2"])])
    validate_pnml_connectivity(pnml)  # must not raise


def test_validate_pnml_connectivity_accepts_join_gateway():
    """A join gateway transition (multiple inbound, one outbound) is valid."""
    pnml = _simple_pnml([("join", ["p_in1", "p_in2"], ["p_out"])])
    validate_pnml_connectivity(pnml)  # must not raise


def test_validate_pnml_connectivity_rejects_transition_without_inbound():
    """A transition with no inbound arc violates the connectivity constraint."""
    pnml = _simple_pnml([("t_source", [], ["p_out"])])
    with pytest.raises(PnmlStructureError, match="no inbound arc"):
        validate_pnml_connectivity(pnml)


def test_validate_pnml_connectivity_rejects_transition_without_outbound():
    """A transition with no outbound arc violates the connectivity constraint."""
    pnml = _simple_pnml([("t_sink", ["p_in"], [])])
    with pytest.raises(PnmlStructureError, match="no outbound arc"):
        validate_pnml_connectivity(pnml)


def test_validate_pnml_connectivity_rejects_isolated_transition():
    """A transition with neither inbound nor outbound arcs must raise once per direction."""
    pnml = "<pnml><net id='n1'><transition id='isolated'/></net></pnml>"
    with pytest.raises(PnmlStructureError) as exc_info:
        validate_pnml_connectivity(pnml)
    msg = str(exc_info.value)
    assert "no inbound arc" in msg
    assert "no outbound arc" in msg


def test_validate_pnml_connectivity_reports_all_violations():
    """When multiple transitions violate constraints all are reported in one error."""
    pnml = _simple_pnml([
        ("t_ok", ["p_in"], ["p_out"]),
        ("t_no_in", [], ["p_mid"]),
        ("t_no_out", ["p_mid"], []),
    ])
    with pytest.raises(PnmlStructureError) as exc_info:
        validate_pnml_connectivity(pnml)
    msg = str(exc_info.value)
    assert "t_no_in" in msg
    assert "t_no_out" in msg
    assert "t_ok" not in msg


def test_validate_pnml_connectivity_is_noop_for_empty_or_non_xml():
    """Falsy or non-XML inputs are silently accepted; the caller guards the contract."""
    validate_pnml_connectivity("")
    validate_pnml_connectivity(None)
    validate_pnml_connectivity("not xml at all")


def test_validate_pnml_connectivity_pnml_structure_error_is_value_error():
    """PnmlStructureError must be a ValueError subclass for existing handlers."""
    pnml = _simple_pnml([("t_sink", ["p_in"], [])])
    with pytest.raises(ValueError):
        validate_pnml_connectivity(pnml)


# ---------------------------------------------------------------------------
# repair_pnml_connectivity_from_bpmn
# ---------------------------------------------------------------------------


def test_repair_pnml_connectivity_from_bpmn_adds_missing_transition_relay():
    """When BPMN expects t1 -> t2, repair injects a PNML relay place/arc path."""
    bpmn = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<definitions xmlns='http://www.omg.org/spec/BPMN/20100524/MODEL'>"
        "<process id='p1'>"
        "<sequenceFlow id='f1' sourceRef='t1' targetRef='t2'/>"
        "</process></definitions>"
    )
    pnml = (
        "<pnml><net id='n1'>"
        "<transition id='t1'/><transition id='t2'/>"
        "<place id='p_in'/><place id='p_out'/>"
        "<arc id='a1' source='p_in' target='t1'/>"
        "<arc id='a2' source='t2' target='p_out'/>"
        "</net></pnml>"
    )

    repaired = repair_pnml_connectivity_from_bpmn(pnml, bpmn)
    validate_pnml_connectivity(repaired)

    root = ET.fromstring(repaired)
    arcs = [
        (arc.get("source"), arc.get("target"))
        for arc in root.iter()
        if arc.tag.split("}")[-1] == "arc"
    ]
    places = {
        p.get("id")
        for p in root.iter()
        if p.tag.split("}")[-1] == "place" and p.get("id")
    }

    # There must be at least one relay place such that t1->place and place->t2.
    assert any(src == "t1" and tgt in places for src, tgt in arcs)
    assert any(src in places and tgt == "t2" for src, tgt in arcs)


def test_repair_pnml_connectivity_from_bpmn_adds_anchors_for_event_side_flows():
    """Flows from/to non-transition BPMN nodes still create missing in/out anchors."""
    bpmn = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<definitions xmlns='http://www.omg.org/spec/BPMN/20100524/MODEL'>"
        "<process id='p1'>"
        "<sequenceFlow id='f_in' sourceRef='startEvent1' targetRef='task1'/>"
        "<sequenceFlow id='f_out' sourceRef='task1' targetRef='endEvent1'/>"
        "</process></definitions>"
    )
    pnml = "<pnml><net id='n1'><transition id='task1'/></net></pnml>"

    repaired = repair_pnml_connectivity_from_bpmn(pnml, bpmn)
    validate_pnml_connectivity(repaired)

    root = ET.fromstring(repaired)
    inbound = 0
    outbound = 0
    for arc in root.iter():
        if arc.tag.split("}")[-1] != "arc":
            continue
        source = arc.get("source")
        target = arc.get("target")
        if target == "task1":
            inbound += 1
        if source == "task1":
            outbound += 1
    assert inbound >= 1
    assert outbound >= 1


def test_sanitize_bpmn_for_transform_removes_duplicate_sequence_flows_and_edges():
    bpmn = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<definitions xmlns='http://www.omg.org/spec/BPMN/20100524/MODEL' "
        "xmlns:bpmndi='http://www.omg.org/spec/BPMN/20100524/DI' "
        "xmlns:di='http://www.omg.org/spec/DD/20100524/DI'>"
        "<process id='p1'>"
        "<startEvent id='s'/>"
        "<userTask id='a'/>"
        "<sequenceFlow id='f1' sourceRef='s' targetRef='a'/>"
        "<sequenceFlow id='f2' sourceRef='s' targetRef='a'/>"
        "</process>"
        "<bpmndi:BPMNDiagram id='d1'><bpmndi:BPMNPlane id='pl1' bpmnElement='p1'>"
        "<bpmndi:BPMNEdge id='f1_di' bpmnElement='f1'>"
        "<di:waypoint x='0' y='0'/><di:waypoint x='1' y='1'/></bpmndi:BPMNEdge>"
        "<bpmndi:BPMNEdge id='f2_di' bpmnElement='f2'>"
        "<di:waypoint x='0' y='0'/><di:waypoint x='1' y='1'/></bpmndi:BPMNEdge>"
        "</bpmndi:BPMNPlane></bpmndi:BPMNDiagram>"
        "</definitions>"
    )

    sanitized = sanitize_bpmn_for_transform(bpmn)
    root = ET.fromstring(sanitized)

    flow_pairs = []
    flow_ids = []
    for flow in root.iter():
        if flow.tag.split("}")[-1] != "sequenceFlow":
            continue
        flow_ids.append(flow.get("id"))
        flow_pairs.append((flow.get("sourceRef"), flow.get("targetRef")))

    assert flow_pairs == [("s", "a")]
    assert flow_ids == ["f1"]

    edge_targets = [
        edge.get("bpmnElement")
        for edge in root.iter()
        if edge.tag.split("}")[-1] == "BPMNEdge"
    ]
    assert edge_targets == ["f1"]


def test_sanitize_bpmn_for_transform_collapses_passthrough_gateway():
    bpmn = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<definitions xmlns='http://www.omg.org/spec/BPMN/20100524/MODEL' "
        "xmlns:bpmndi='http://www.omg.org/spec/BPMN/20100524/DI' "
        "xmlns:di='http://www.omg.org/spec/DD/20100524/DI'>"
        "<process id='p1'>"
        "<startEvent id='s'/>"
        "<exclusiveGateway id='g1'/>"
        "<userTask id='t1'/>"
        "<sequenceFlow id='f1' sourceRef='s' targetRef='g1'/>"
        "<sequenceFlow id='f2' sourceRef='g1' targetRef='t1'/>"
        "</process>"
        "<bpmndi:BPMNDiagram id='d1'><bpmndi:BPMNPlane id='pl1' bpmnElement='p1'>"
        "<bpmndi:BPMNShape id='g1_di' bpmnElement='g1'>"
        "<di:waypoint x='0' y='0'/></bpmndi:BPMNShape>"
        "<bpmndi:BPMNEdge id='f1_di' bpmnElement='f1'>"
        "<di:waypoint x='0' y='0'/><di:waypoint x='1' y='1'/></bpmndi:BPMNEdge>"
        "<bpmndi:BPMNEdge id='f2_di' bpmnElement='f2'>"
        "<di:waypoint x='0' y='0'/><di:waypoint x='1' y='1'/></bpmndi:BPMNEdge>"
        "</bpmndi:BPMNPlane></bpmndi:BPMNDiagram>"
        "</definitions>"
    )

    sanitized = sanitize_bpmn_for_transform(bpmn)
    root = ET.fromstring(sanitized)

    gateways = [
        e for e in root.iter() if e.tag.split("}")[-1] in {"exclusiveGateway", "parallelGateway"}
    ]
    assert gateways == []

    flows = [e for e in root.iter() if e.tag.split("}")[-1] == "sequenceFlow"]
    assert len(flows) == 1
    assert flows[0].get("sourceRef") == "s"
    assert flows[0].get("targetRef") == "t1"
