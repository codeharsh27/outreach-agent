"""
Shared configuration — loaded from .env
All agents import from here.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJ = Path("/mnt/c/Users/asus/outreach-agent")
load_dotenv(PROJ / ".env")

# ── LLM Cloud Provider Keys ──────────────────────────────────────
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
LLM_PROVIDER       = os.getenv("LLM_PROVIDER", "gemini")  # gemini | openrouter | ollama

# ── Ollama (fallback local model) ─────────────────────────────────
OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "http://172.21.112.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")

# ── GitHub ───────────────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ── Gmail ────────────────────────────────────────────────────────
GMAIL_SENDER  = os.getenv("GMAIL_SENDER_EMAIL", "harshmude27@gmail.com")
GMAIL_CREDS   = PROJ / "config" / "gmail_credentials.json"
GMAIL_TOKEN   = PROJ / "config" / "token.json"

# ── Telegram ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Contact APIs ─────────────────────────────────────────────────
HUNTER_API_KEY  = os.getenv("HUNTER_API_KEY",  "")
SNOVIO_USER_ID  = os.getenv("SNOVIO_USER_ID",  "")
SNOVIO_SECRET   = os.getenv("SNOVIO_SECRET",   "")
MINELEAD_API_KEY = os.getenv("MINELEAD_API_KEY", "")

# ── Your identity (used in all drafts) ───────────────────────────
YOUR_NAME     = os.getenv("YOUR_NAME",     "Harsh Mule")
YOUR_EMAIL    = os.getenv("YOUR_EMAIL",    "harshmude27@gmail.com")
SIDEDOOR_URL  = os.getenv("SIDEDOOR_URL",  "https://sidedoor-chi.vercel.app/")
PORTFOLIO_URL = os.getenv("PORTFOLIO_URL", "https://harshmule.vercel.app/")
TWITTER_URL   = os.getenv("TWITTER_URL",   "https://x.com/codeharsh27")
LINKEDIN_URL  = os.getenv("LINKEDIN_URL",  "https://www.linkedin.com/in/harshmule27/")
GITHUB_URL    = os.getenv("GITHUB_URL",    "https://github.com/codeharsh27")

# ── Data paths ───────────────────────────────────────────────────
DATA_DIR     = PROJ / "data"
TARGETS_DIR  = DATA_DIR / "targets"
TRACKER_DB   = DATA_DIR / "tracker" / "outreach.db"

# Create dirs if missing
TARGETS_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "tracker").mkdir(parents=True, exist_ok=True)
(PROJ / "config").mkdir(parents=True, exist_ok=True)

# ── Outreach limits ──────────────────────────────────────────────
TIER_A_COUNT = 10   # Deep research — specific angle per company
TIER_B_COUNT = 35   # Lightweight research — pattern-based

# ── Send timing ──────────────────────────────────────────────────
SEND_DAYS        = [1, 2, 3]   # Mon=0, Tue=1, Wed=2, Thu=3, Fri=4
SEND_HOUR_START  = 9           # 9am recipient local time
SEND_HOUR_END    = 11          # 11am recipient local time
SEND_MIN_DELAY_S = 120         # min seconds between sends (2 min)
SEND_MAX_DELAY_S = 480         # max seconds between sends (8 min)
