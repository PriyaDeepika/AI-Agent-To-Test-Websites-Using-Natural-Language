"""Central configuration. Everything is optional; defaults work without any API key."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or None   # optional: enables LLM planner
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-flash-lite-latest")

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "agent.db"))

BROWSER_HEADLESS = _bool("BROWSER_HEADLESS", True)
BROWSER_SLOW_MO_MS = _int("BROWSER_SLOW_MO_MS", 0)
ACTION_TIMEOUT_MS = _int("ACTION_TIMEOUT_MS", 10000)
NAV_TIMEOUT_MS = _int("NAV_TIMEOUT_MS", 30000)

MAX_STEP_RETRIES = _int("MAX_STEP_RETRIES", 2)      # recovery attempts per step
MAX_TOTAL_ACTIONS = _int("MAX_TOTAL_ACTIONS", 60)   # hard cap on actions per run
RUN_TIMEOUT_S = _int("RUN_TIMEOUT_S", 300)
USER_RESPONSE_TIMEOUT_S = _int("USER_RESPONSE_TIMEOUT_S", 600)

# Local demo/regression pages are served by this same Flask app.
DEMO_BASE_URL = os.getenv("DEMO_BASE_URL", "http://127.0.0.1:5000")
ALLOW_PRIVATE_NETWORK = _bool("ALLOW_PRIVATE_NETWORK", False)  # localhost demo pages are always allowed
BLOCKED_DOMAINS = [d.strip().lower() for d in os.getenv("BLOCKED_DOMAINS", "").split(",") if d.strip()]

HOST = os.getenv("HOST", "127.0.0.1")
PORT = _int("PORT", 5000)
