import xml.etree.ElementTree as ET
import uuid

def json_to_bpmn(bpmn_data):
    # Register namespaces for proper XML generation
    ET.register_namespace('', 'http://www.omg.org/spec/BPMN/20100524/MODEL')
    ET.register_namespace('bpmndi', 'http://www.omg.org/spec/BPMN/20100524/DI')
    ET.register_namespace('di', 'http://www.omg.org/spec/DD/20100524/DI')
    ET.register_namespace('dc', 'http://www.omg.org/spec/DD/20100524/DC')
    ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')

    # Create root element with proper namespaces and attributes
    definitions = ET.Element('definitions')
    definitions.set('xmlns', 'http://www.omg.org/spec/BPMN/20100524/MODEL')
    definitions.set('xmlns:bpmndi', 'http://www.omg.org/spec/BPMN/20100524/DI')
    definitions.set('xmlns:di', 'http://www.omg.org/spec/DD/20100524/DI')
    definitions.set('xmlns:dc', 'http://www.omg.org/spec/DD/20100524/DC')
    definitions.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    definitions.set('id', f'Definitions_{uuid.uuid4().hex[:8]}')
    definitions.set('targetNamespace', 'http://bpmn.io/schema/bpmn')

    # Create process element
    process_id = f'Process_{uuid.uuid4().hex[:8]}'
    process = ET.SubElement(definitions, 'process')
    process.set('id', process_id)
    process.set('isExecutable', 'false')

    # Create all events, tasks, and gateways with incoming/outgoing references
    for event in bpmn_data.get('events', []):
        event_type = 'startEvent' if event['type'] == 'Start' else 'endEvent' if event['type'] == 'End' else 'intermediateCatchEvent'
        event_elem = ET.SubElement(process, event_type)
        event_elem.set('id', event['id'])
        if event.get('name'):
            event_elem.set('name', event['name'])
        
        # Add incoming and outgoing flow references
        incoming_flows = [flow['id'] for flow in bpmn_data.get('flows', []) if flow['target'] == event['id']]
        outgoing_flows = [flow['id'] for flow in bpmn_data.get('flows', []) if flow['source'] == event['id']]
        
        for flow_id in incoming_flows:
            incoming_elem = ET.SubElement(event_elem, 'incoming')
            incoming_elem.text = flow_id
            
        for flow_id in outgoing_flows:
            outgoing_elem = ET.SubElement(event_elem, 'outgoing')
            outgoing_elem.text = flow_id

    for task in bpmn_data.get('tasks', []):
        # Map task types to proper BPMN task types (camelCase)
        task_type_map = {
            'task': 'task',
            'usertask': 'userTask',
            'servicetask': 'serviceTask',
            'manualtask': 'manualTask',
            'scripttask': 'scriptTask',
            'businessruletask': 'businessRuleTask',
            'sendtask': 'sendTask',
            'receivetask': 'receiveTask'
        }
        task_type = task_type_map.get(task['type'].lower(), 'task')
        task_elem = ET.SubElement(process, task_type)
        task_elem.set('id', task['id'])
        if task.get('name'):
            task_elem.set('name', task['name'])
            
        # Add incoming and outgoing flow references
        incoming_flows = [flow['id'] for flow in bpmn_data.get('flows', []) if flow['target'] == task['id']]
        outgoing_flows = [flow['id'] for flow in bpmn_data.get('flows', []) if flow['source'] == task['id']]
        
        for flow_id in incoming_flows:
            incoming_elem = ET.SubElement(task_elem, 'incoming')
            incoming_elem.text = flow_id
            
        for flow_id in outgoing_flows:
            outgoing_elem = ET.SubElement(task_elem, 'outgoing')
            outgoing_elem.text = flow_id

    for gateway in bpmn_data.get('gateways', []):
        # Map gateway types to proper BPMN gateway types (camelCase)
        gateway_type_map = {
            'exclusivegateway': 'exclusiveGateway',
            'inclusivegateway': 'inclusiveGateway',
            'parallelgateway': 'parallelGateway',
            'eventbasedgateway': 'eventBasedGateway',
            'complexgateway': 'complexGateway'
        }
        gateway_type = gateway_type_map.get(gateway['type'].lower(), 'exclusiveGateway')
        gateway_elem = ET.SubElement(process, gateway_type)
        gateway_elem.set('id', gateway['id'])
        if gateway.get('name'):
            gateway_elem.set('name', gateway['name'])
            
        # Add incoming and outgoing flow references
        incoming_flows = [flow['id'] for flow in bpmn_data.get('flows', []) if flow['target'] == gateway['id']]
        outgoing_flows = [flow['id'] for flow in bpmn_data.get('flows', []) if flow['source'] == gateway['id']]
        
        for flow_id in incoming_flows:
            incoming_elem = ET.SubElement(gateway_elem, 'incoming')
            incoming_elem.text = flow_id
            
        for flow_id in outgoing_flows:
            outgoing_elem = ET.SubElement(gateway_elem, 'outgoing')
            outgoing_elem.text = flow_id

    for flow in bpmn_data.get('flows', []):
        flow_elem = ET.SubElement(process, 'sequenceFlow')
        flow_elem.set('id', flow['id'])
        flow_elem.set('sourceRef', flow['source'])
        flow_elem.set('targetRef', flow['target'])

    # Save the XML to a file
    tree = ET.ElementTree(definitions)
    ET.indent(tree, space="  ", level=0)
    tree.write('bpmn_output.bpmn', encoding='utf-8', xml_declaration=True)

    bpmn_string = ET.tostring(definitions, encoding='utf-8', xml_declaration=True).decode('utf-8')
    
    return bpmn_string

def json_to_pnml(bpmn_data):
    """
    Convert BPMN JSON data to PNML (Petri Net Markup Language) format.
    """
    # Create root element
    pnml = ET.Element('pnml')
    
    # Create net element with standard attributes
    net = ET.SubElement(pnml, 'net')
    net.set('type', 'http://www.informatik.hu-berlin.de/top/pntd/ptNetb')
    net.set('id', 'noID')
    
    # Position counters for automatic layout
    pos_x = 100
    pos_y = 100
    spacing = 150
    
    # Convert events to places
    for i, event in enumerate(bpmn_data.get('events', [])):
        place = ET.SubElement(net, 'place')
        place.set('id', event['id'])
        
        # Name element
        name_elem = ET.SubElement(place, 'name')
        text_elem = ET.SubElement(name_elem, 'text')
        text_elem.text = event.get('name', event['id'])
        
        graphics_name = ET.SubElement(name_elem, 'graphics')
        offset_name = ET.SubElement(graphics_name, 'offset')
        offset_name.set('x', str(pos_x))
        offset_name.set('y', str(pos_y + 40))
        
        # Graphics element
        graphics = ET.SubElement(place, 'graphics')
        position = ET.SubElement(graphics, 'position')
        position.set('x', str(pos_x))
        position.set('y', str(pos_y))
        
        dimension = ET.SubElement(graphics, 'dimension')
        dimension.set('x', '40')
        dimension.set('y', '40')
        
        pos_x += spacing
    
    # Convert tasks to transitions
    for i, task in enumerate(bpmn_data.get('tasks', [])):
        transition = ET.SubElement(net, 'transition')
        transition.set('id', task['id'])
        
        # Name element
        name_elem = ET.SubElement(transition, 'name')
        text_elem = ET.SubElement(name_elem, 'text')
        text_elem.text = task.get('name', task['id'])
        
        graphics_name = ET.SubElement(name_elem, 'graphics')
        offset_name = ET.SubElement(graphics_name, 'offset')
        offset_name.set('x', str(pos_x))
        offset_name.set('y', str(pos_y + 40))
        
        # Graphics element
        graphics = ET.SubElement(transition, 'graphics')
        position = ET.SubElement(graphics, 'position')
        position.set('x', str(pos_x))
        position.set('y', str(pos_y))
        
        dimension = ET.SubElement(graphics, 'dimension')
        dimension.set('x', '40')
        dimension.set('y', '40')
        
        pos_x += spacing
    
    # Convert flows to arcs
    for i, flow in enumerate(bpmn_data.get('flows', [])):
        arc = ET.SubElement(net, 'arc')
        arc.set('id', flow['id'])
        arc.set('source', flow['source'])
        arc.set('target', flow['target'])
        
        # Inscription element
        inscription = ET.SubElement(arc, 'inscription')
        text_elem = ET.SubElement(inscription, 'text')
        text_elem.text = '1'
    
    # Save the XML to a file
    tree = ET.ElementTree(pnml)
    ET.indent(tree, space="  ", level=0)
    tree.write('pnml_output.pnml', encoding='utf-8', xml_declaration=True)
    
    pnml_string = ET.tostring(pnml, encoding='utf-8', xml_declaration=True).decode('utf-8')
    
    return pnml_string