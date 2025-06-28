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

    # Generate diagram elements with improved positioning
    def get_element_position(element_type, index):
        """Calculate position based on element type and index."""
        # Base positions and spacing
        start_x = 50
        start_y = 150
        horizontal_spacing = 200
        vertical_spacing = 120
        
        # Different Y positions for different element types
        y_offsets = {
            'startEvent': 0,
            'endEvent': 0,
            'task': 0,
            'userTask': 0,
            'serviceTask': 0,
            'exclusiveGateway': -60,
            'parallelGateway': -60
        }
        
        # Calculate X position based on process flow order
        x = start_x + (index * horizontal_spacing)
        y = start_y + y_offsets.get(element_type, 0)
        
        return x, y
    
    def get_element_dimensions(element_type):
        """Get appropriate width and height for different element types."""
        dimensions = {
            'startEvent': (36, 36),
            'endEvent': (36, 36),
            'task': (100, 80),
            'userTask': (100, 80),
            'serviceTask': (100, 80),
            'exclusiveGateway': (50, 50),
            'parallelGateway': (50, 50)
        }
        return dimensions.get(element_type, (100, 80))
    
    # Create a mapping of element flow order for better positioning
    element_positions = {}
    position_index = 0
    
    # Position start events first
    for event in bpmn_data.get('events', []):
        if event['type'] == 'startEvent':
            x, y = get_element_position(event['type'], position_index)
            element_positions[event['id']] = (x, y, event['type'])
            position_index += 1
    
    # Position tasks and gateways based on flow sequence
    flows = bpmn_data.get('flows', [])
    processed_elements = set()
    
    # Build a simple flow graph to determine order
    for flow in flows:
        source_id = flow['source']
        target_id = flow['target']
        
        if target_id not in processed_elements:
            # Find the target element
            target_element = None
            for element_list in [bpmn_data.get('tasks', []), bpmn_data.get('gateways', []), bpmn_data.get('events', [])]:
                for elem in element_list:
                    if elem['id'] == target_id:
                        target_element = elem
                        break
                if target_element:
                    break
            
            if target_element and target_element['type'] != 'startEvent':
                x, y = get_element_position(target_element['type'], position_index)
                element_positions[target_id] = (x, y, target_element['type'])
                processed_elements.add(target_id)
                position_index += 1
    
    # Position any remaining elements that weren't caught in the flow
    all_elements = (
        bpmn_data.get('tasks', []) + 
        bpmn_data.get('events', []) + 
        bpmn_data.get('gateways', [])
    )
    
    for element in all_elements:
        if element['id'] not in element_positions:
            x, y = get_element_position(element['type'], position_index)
            element_positions[element['id']] = (x, y, element['type'])
            position_index += 1
    
    # Create BPMN shapes with calculated positions
    for element in all_elements:
        x, y, element_type = element_positions[element['id']]
        width, height = get_element_dimensions(element_type)
        
        bpmn_shape = ET.SubElement(bpmn_plane, f"{{{ns['bpmndi']}}}BPMNShape", attrib={
            'id': f"{element['id']}_di", 
            'bpmnElement': element['id']
        })
        ET.SubElement(bpmn_shape, f"{{{ns['dc']}}}Bounds", attrib={
            'x': str(x), 
            'y': str(y), 
            'width': str(width), 
            'height': str(height)
        })

    # Generate diagram elements for flows with calculated waypoints
    for flow in bpmn_data.get('flows', []):
        bpmn_edge = ET.SubElement(bpmn_plane, f"{{{ns['bpmndi']}}}BPMNEdge", attrib={
            'id': f"{flow['id']}_di", 
            'bpmnElement': flow['id']
        })
        
        # Calculate waypoints based on source and target positions
        source_id = flow['source']
        target_id = flow['target']
        
        if source_id in element_positions and target_id in element_positions:
            source_x, source_y, source_type = element_positions[source_id]
            target_x, target_y, target_type = element_positions[target_id]
            
            # Calculate connection points (center-right of source to center-left of target)
            source_width, source_height = get_element_dimensions(source_type)
            target_width, target_height = get_element_dimensions(target_type)
            
            # Source waypoint (right edge, center)
            source_waypoint_x = source_x + source_width
            source_waypoint_y = source_y + (source_height // 2)
            
            # Target waypoint (left edge, center)
            target_waypoint_x = target_x
            target_waypoint_y = target_y + (target_height // 2)
            
            waypoints = [
                {'x': str(source_waypoint_x), 'y': str(source_waypoint_y)}, 
                {'x': str(target_waypoint_x), 'y': str(target_waypoint_y)}
            ]
        else:
            # Fallback to default waypoints if positions not found
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