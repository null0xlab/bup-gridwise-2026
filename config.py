import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present
load_dotenv()

# Check fallback locations if OPENROUTER_API_KEY is not in current environment
if not os.environ.get("OPENROUTER_API_KEY"):
    fallback_paths = [
        Path.cwd() / ".env",
        Path.home() / ".env",
        Path(r"C:\Users\Lenovo\gridwise\.env"),
        Path(r"E:\WarQ\server\.env")
    ]
    for p in fallback_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OPENROUTER_API_KEY=") and not line.startswith("#"):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if key:
                                os.environ["OPENROUTER_API_KEY"] = key
                                break
            except Exception:
                pass
        if os.environ.get("OPENROUTER_API_KEY"):
            break

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "google/gemini-2.5-flash")
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0")
