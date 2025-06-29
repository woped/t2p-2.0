import os

TRANSFORMER_BASE_URL = os.environ.get('TRANSFORMER_BASE_URL') or 'https://woped.dhbw-karlsruhe.de/pnml-bpmn-transformer'
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
