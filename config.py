import os
from dotenv import load_dotenv

# Load configuration from the project's local .env file when present.
# Secrets stay outside version control and are supplied through the environment
# in deployed environments.
load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "google/gemini-2.5-flash")
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0")
