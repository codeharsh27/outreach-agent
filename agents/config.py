"""
Shared configuration — loaded from .env
All agents import from here.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ── Resolve project root dynamically (works on any machine) ──────
PROJ = Path(__file__).resolve().parent.parent
load_dotenv(PROJ / ".env")

# ── Supabase (Cloud DB) ──────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

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
GMAIL_SENDER  = os.getenv("GMAIL_SENDER_EMAIL", "")
GMAIL_CREDS   = PROJ / "config" / "gmail_credentials.json"
GMAIL_TOKEN   = PROJ / "config" / "token.json"

# ── Telegram ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Contact APIs ─────────────────────────────────────────────────
HUNTER_API_KEY   = os.getenv("HUNTER_API_KEY",  "")
SNOVIO_USER_ID   = os.getenv("SNOVIO_USER_ID",  "")
SNOVIO_SECRET    = os.getenv("SNOVIO_SECRET",   "")
MINELEAD_API_KEY = os.getenv("MINELEAD_API_KEY", "")

# ── User identity (used in all email drafts) ─────────────────────
YOUR_NAME     = os.getenv("YOUR_NAME",     "")
YOUR_EMAIL    = os.getenv("YOUR_EMAIL",    "")
SIDEDOOR_URL  = os.getenv("SIDEDOOR_URL",  "")
PORTFOLIO_URL = os.getenv("PORTFOLIO_URL", "")
TWITTER_URL   = os.getenv("TWITTER_URL",   "")
LINKEDIN_URL  = os.getenv("LINKEDIN_URL",  "")
GITHUB_URL    = os.getenv("GITHUB_URL",    "")

# ── Personalization (email drafting voice) ───────────────────────
USER_ROLE         = os.getenv("USER_ROLE",         "Product Engineer")
USER_PROJECT_NAME = os.getenv("USER_PROJECT_NAME", "SideDoor & drift-watch")
USER_PROJECT_DESC = os.getenv("USER_PROJECT_DESC", "SideDoor surfaces evidenced job opportunities at startups based on real technical evidence, and drift-watch flags silent API schema drift before production.")

DEFAULT_SIGNATURE_MARKDOWN = (
    "Harsh Mule\n"
    "Building [SideDoor](https://sidedoor-chi.vercel.app/) | [Portfolio](https://harshmule.vercel.app/)\n"
    "Socials: [X](https://x.com/codeharsh27) | [LinkedIn](https://www.linkedin.com/in/harshmule27/) | [Github](https://github.com/codeharsh27)"
)

# ── Local dirs (Gmail credentials only — DB is now Supabase) ────
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
