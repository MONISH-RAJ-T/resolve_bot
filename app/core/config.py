"""All settings come from environment variables (see .env.example)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

POLICIES_PATH = os.getenv("POLICIES_PATH", "./data/policies.md")
MANIFEST_PATH = os.getenv("MANIFEST_PATH", "./data/manifest.json")
DB_PATH = os.getenv("DB_PATH", "./data/shopsphere.db")
APP_TODAY = os.getenv("APP_TODAY", "2026-07-01")  # the date the app treats as "today"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # only "gemini" is implemented
LLM_MODEL = os.getenv("LLM_MODEL") or "gemini-2.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))  # seconds per LLM request

MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "6"))  # per customer message
REPLY_DEADLINE = float(os.getenv("REPLY_DEADLINE", "25"))  # stop calling the LLM after this many seconds
