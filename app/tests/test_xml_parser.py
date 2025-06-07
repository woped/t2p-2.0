import unittest
from unittest.mock import patch, mock_open
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from backend.xml_parser import json_to_bpmn

class TestJsonToBpmn(unittest.TestCase):
    def setUp(self):
        """
        Set up the bpmn_data.
        """
        self.bpmn_data = {
            'events': [{'type': 'Start', 'id': 'start_event', 'name': 'Start Event'}],
            'tasks': [{'type': 'Task', 'id': 'task_1', 'name': 'Task 1'}],
            'gateways': [{'type': 'Gateway', 'id': 'gateway_1', 'name': 'Gateway 1'}],
            'flows': [{'id': 'flow_1', 'source': 'start_event', 'target': 'task_1'}]
        }

    @patch("xml.etree.ElementTree.ElementTree.write")
    def test_json_to_bpmn(self, mock_write):
        """
        Test the json_to_bpmn function. It should be called twice.
        """
        json_to_bpmn(self.bpmn_data)
        mock_write.assert_any_call('bpmn_output.bpmn', encoding='utf-8', xml_declaration=True)
        self.assertEqual(mock_write.call_count, 2)

if __name__ == '__main__':
    unittest.main()