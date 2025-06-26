import xml.etree.ElementTree as ET

def json_to_bpmn(bpmn_data):
    # Define XML namespaces for BPMN 2.0
    ns = {
        'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
        'bpmndi': 'http://www.omg.org/spec/BPMN/20100524/DI',
        'di': 'http://www.omg.org/spec/DD/20100524/DI',
        'dc': 'http://www.omg.org/spec/DD/20100524/DC',
        'xsi': "http://www.w3.org/2001/XMLSchema-instance"
    }
    
    # Register namespaces to avoid ns0, ns1, etc. prefixes
    ET.register_namespace('', ns['bpmn'])
    ET.register_namespace('bpmndi', ns['bpmndi'])
    ET.register_namespace('di', ns['di'])
    ET.register_namespace('dc', ns['dc'])
    ET.register_namespace('xsi', ns['xsi'])

    # Create root definitions element
    definitions = ET.Element(f"{{{ns['bpmn']}}}definitions", attrib={
        f"{{{ns['xsi']}}}schemaLocation": "http://www.omg.org/spec/BPMN/20100524/MODEL BPMN20.xsd",
        'targetNamespace': "http://example.bpmn.com/schema/bpmn"
    })

    # Create process element
    process = ET.SubElement(definitions, f"{{{ns['bpmn']}}}process", attrib={
        'id': 'Process_1', 
        'isExecutable': 'false'
    })

    # Valid element types for validation
    VALID_EVENT_TYPES = ['startEvent', 'endEvent']
    VALID_TASK_TYPES = ['userTask', 'serviceTask', 'task']
    VALID_GATEWAY_TYPES = ['exclusiveGateway', 'parallelGateway']
    VALID_FLOW_TYPES = ['sequenceFlow']

    # Create all events
    for event in bpmn_data.get('events', []):
        event_type = event['type']
        
        # Validation to ensure only valid event types
        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event type: '{event_type}'. "
                f"Only {VALID_EVENT_TYPES} are supported. "
                f"Got: {event}"
            )
            
        ET.SubElement(process, f"{{{ns['bpmn']}}}{event_type}", attrib={
            'id': event['id'], 
            'name': event.get('name', '')
        })

    # Create all tasks
    for task in bpmn_data.get('tasks', []):
        task_type = task['type']
        
        # Validation to ensure only valid task types
        if task_type not in VALID_TASK_TYPES:
            raise ValueError(
                f"Invalid task type: '{task_type}'. "
                f"Only {VALID_TASK_TYPES} are supported. "
                f"Got: {task}"
            )
            
        ET.SubElement(process, f"{{{ns['bpmn']}}}{task_type}", attrib={
            'id': task['id'], 
            'name': task.get('name', '')
        })

    # Create all gateways
    for gateway in bpmn_data.get('gateways', []):
        gateway_type = gateway['type']
        
        # Validation to ensure only valid gateway types
        if gateway_type not in VALID_GATEWAY_TYPES:
            raise ValueError(
                f"Invalid gateway type: '{gateway_type}'. "
                f"Only {VALID_GATEWAY_TYPES} are supported. "
                f"Got: {gateway}"
            )
            
        ET.SubElement(process, f"{{{ns['bpmn']}}}{gateway_type}", attrib={
            'id': gateway['id'], 
            'name': gateway.get('name', '')
        })

    # Create all sequence flows
    for flow in bpmn_data.get('flows', []):
        flow_type = flow['type']
        
        # Validation to ensure only valid flow types
        if flow_type not in VALID_FLOW_TYPES:
            raise ValueError(
                f"Invalid flow type: '{flow_type}'. "
                f"Only {VALID_FLOW_TYPES} are supported. "
                f"Got: {flow}"
            )
            
        ET.SubElement(process, f"{{{ns['bpmn']}}}{flow_type}", attrib={
            'id': flow['id'], 
            'sourceRef': flow['source'], 
            'targetRef': flow['target']
        })

    # Create BPMN Diagram Information (BPMNDI) section
    bpmn_di = ET.SubElement(definitions, f"{{{ns['bpmndi']}}}BPMNDiagram", attrib={
        'id': 'BPMNDiagram_1'
    })
    bpmn_plane = ET.SubElement(bpmn_di, f"{{{ns['bpmndi']}}}BPMNPlane", attrib={
        'id': 'BPMNPlane_1', 
        'bpmnElement': 'Process_1'
    })

    # Generate diagram elements for all visual elements (tasks, events, gateways)
    all_elements = (
        bpmn_data.get('tasks', []) + 
        bpmn_data.get('events', []) + 
        bpmn_data.get('gateways', [])
    )
    
    for element in all_elements:
        bpmn_shape = ET.SubElement(bpmn_plane, f"{{{ns['bpmndi']}}}BPMNShape", attrib={
            'id': f"{element['id']}_di", 
            'bpmnElement': element['id']
        })
        # Default positioning - can be customized based on requirements
        ET.SubElement(bpmn_shape, f"{{{ns['dc']}}}Bounds", attrib={
            'x': '100', 
            'y': '100', 
            'width': '100', 
            'height': '80'
        })

    # Generate diagram elements for flows
    for flow in bpmn_data.get('flows', []):
        bpmn_edge = ET.SubElement(bpmn_plane, f"{{{ns['bpmndi']}}}BPMNEdge", attrib={
            'id': f"{flow['id']}_di", 
            'bpmnElement': flow['id']
        })
        # Default waypoints - can be customized based on actual element positions
        waypoints = [
            {'x': '120', 'y': '150'}, 
            {'x': '250', 'y': '150'}
        ]
        for waypoint in waypoints:
            ET.SubElement(bpmn_edge, f"{{{ns['di']}}}waypoint", attrib={
                'x': waypoint['x'], 
                'y': waypoint['y']
            })

    # Create XML tree and format it
    tree = ET.ElementTree(definitions)
    ET.indent(tree, space="  ", level=0)
    
    # Save to file (optional)
    tree.write('bpmn_output.bpmn', encoding='utf-8', xml_declaration=True)

    # Convert to string for return
    bpmn_string = ET.tostring(definitions, encoding='utf-8', xml_declaration=True).decode('utf-8')
    
    return bpmn_string


# Example usage and testing function
def test_json_to_bpmn():
    """Test function to validate the JSON to BPMN conversion."""
    test_data = {
        "events": [
            {"id": "startEvent1", "type": "startEvent", "name": "Process Started"},
            {"id": "endEvent1", "type": "endEvent", "name": "Process Completed"}
        ],
        "tasks": [
            {"id": "task1", "type": "userTask", "name": "Review Application"},
            {"id": "task2", "type": "serviceTask", "name": "Send Notification"}
        ],
        "gateways": [
            {"id": "gateway1", "type": "exclusiveGateway", "name": "Decision Point"}
        ],
        "flows": [
            {"id": "flow1", "type": "sequenceFlow", "source": "startEvent1", "target": "task1"},
            {"id": "flow2", "type": "sequenceFlow", "source": "task1", "target": "gateway1"},
            {"id": "flow3", "type": "sequenceFlow", "source": "gateway1", "target": "task2"},
            {"id": "flow4", "type": "sequenceFlow", "source": "task2", "target": "endEvent1"}
        ]
    }
    
    try:
        result = json_to_bpmn(test_data)
        print("✅ Conversion successful!")
        print("Generated BPMN XML:")
        print(result)
        return True
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        return False


if __name__ == "__main__":
    test_json_to_bpmn()