import os
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.80"))

if not ENDPOINT or not KEY:
    raise EnvironmentError(
        "Missing required env vars: AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY"
    )
