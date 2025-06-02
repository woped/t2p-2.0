import os

PROMPTING_STRATEGIE = os.getenv("PROMPTING_STRATEGIE", "few_shot")
API_HOST = os.getenv("API_HOST", "woped.dhbw-karlsruhe.de")
API_PORT = int(os.getenv("API_PORT", 443))
