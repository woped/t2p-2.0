import xml.etree.ElementTree as ET

def json_to_bpmn(bpmn_data):
    ns = {
        'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
        'bpmndi': 'http://www.omg.org/spec/BPMN/20100524/DI',
        'di': 'http://www.omg.org/spec/DD/20100524/DI',
        'dc': 'http://www.omg.org/spec/DD/20100524/DC',
        'xsi': "http://www.w3.org/2001/XMLSchema-instance"
    }
    ET.register_namespace('', ns['bpmn'])
    ET.register_namespace('bpmndi', ns['bpmndi'])
    ET.register_namespace('di', ns['di'])
    ET.register_namespace('dc', ns['dc'])
    ET.register_namespace('xsi', ns['xsi'])

    definitions = ET.Element(f"{{{ns['bpmn']}}}definitions", attrib={
        f"{{{ns['xsi']}}}schemaLocation": "http://www.omg.org/spec/BPMN/20100524/MODEL BPMN20.xsd",
        'targetNamespace': "http://example.bpmn.com/schema/bpmn"
    })

    process = ET.SubElement(definitions, f"{{{ns['bpmn']}}}process", attrib={'id': 'Process_1', 'isExecutable': 'false'})

    # Create all events, tasks, and gateways
    for event in bpmn_data['events']:
        event_type = 'startEvent' if event['type'] == 'Start' else 'endEvent' if event['type'] == 'End' else 'intermediateCatchEvent'
        ET.SubElement(process, f"{{{ns['bpmn']}}}{event_type}", id=event['id'], name=event['name'])

    for task in bpmn_data['tasks']:
        ET.SubElement(process, f"{{{ns['bpmn']}}}{task['type']}", id=task['id'], name=task['name'])

    for gateway in bpmn_data['gateways']:
        ET.SubElement(process, f"{{{ns['bpmn']}}}{gateway['type']}", id=gateway['id'], name=gateway['name'])

    for flow in bpmn_data['flows']:
        ET.SubElement(process, f"{{{ns['bpmn']}}}sequenceFlow", id=flow['id'], sourceRef=flow['source'], targetRef=flow['target'])

    # BPMNDI section
    bpmn_di = ET.SubElement(definitions, f"{{{ns['bpmndi']}}}BPMNDiagram", attrib={'id': 'BPMNDiagram_1'})
    bpmn_plane = ET.SubElement(bpmn_di, f"{{{ns['bpmndi']}}}BPMNPlane", attrib={'id': 'BPMNPlane_1', 'bpmnElement': 'Process_1'})

    # Generate diagram elements for tasks, events, gateways
    for element in bpmn_data['tasks'] + bpmn_data['events'] + bpmn_data['gateways']:
        bpmn_shape = ET.SubElement(bpmn_plane, f"{{{ns['bpmndi']}}}BPMNShape", attrib={'id': f"{element['id']}_di", 'bpmnElement': element['id']})
        ET.SubElement(bpmn_shape, f"{{{ns['dc']}}}Bounds", attrib={'x': '100', 'y': '100', 'width': '100', 'height': '80'})

    # Generate diagram elements for flows
    for flow in bpmn_data['flows']:
        bpmn_edge = ET.SubElement(bpmn_plane, f"{{{ns['bpmndi']}}}BPMNEdge", attrib={'id': f"{flow['id']}_di", 'bpmnElement': flow['id']})
        waypoints = [{'x': '120', 'y': '150'}, {'x': '250', 'y': '150'}]  # Example waypoints, adjust based on actual positions
        for waypoint in waypoints:
            ET.SubElement(bpmn_edge, f"{{{ns['di']}}}waypoint", attrib={'x': waypoint['x'], 'y': waypoint['y']})

    # Save the XML to a file
    tree = ET.ElementTree(definitions)
    ET.indent(tree, space="  ", level=0)
    tree.write('bpmn_output.bpmn', encoding='utf-8', xml_declaration=True)

    bpmn_string = ET.tostring(definitions, encoding='utf-8', xml_declaration=True).decode('utf-8')
    
    return bpmn_string