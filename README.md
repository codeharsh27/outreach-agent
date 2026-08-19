# 🛰️ Outreach Agent

> Autonomous, Staggered Lead Discovery, Light Research, Sub-Second Gemini 3.6 Flash Drafting, and Human-in-the-Loop Telegram Outreach Engine.

Modeled after modern production-grade agentic architectures like **Hermes Agent**, Outreach Agent runs continuous 24-hour background micro-batches to discover high-fit startups, perform 3-layer light technical research, generate personalized cold outreach in < 300ms using Google Gemini Flash, and deliver interactive approval cards via Telegram.

---

## 🏗️ Architecture & Pipeline Overview

```
[ 24-HOUR STAGGERED BACKGROUND PRE-STAGING ]
                                │
   ┌────────────────────────────┼────────────────────────────┐
   │                            │                            │
   ▼                            ▼                            ▼
02:00 PM Batch               06:00 PM Batch               10:00 PM Batch
(15 Companies)               (15 Companies)               (15 Companies)
   │                            │                            │
   ├─► Scraping: YC, GitHub Trending, ProductHunt, Wellfound, a16z, Indian Tech
   ├─► 3-Layer Light Research: Repo README + Twitter + Template Hook (0.1s)
   └─► Contact Finder: GitHub Profile → Commit Email → Minelead → MX Check
                                │
                                ▼
                   [ MIDNIGHT DRAFT GENERATION ]
   └─► Gemini 3.6 Flash generates 45-50 drafts in < 15 seconds
       Stored in SQLite DB (`status = 'drafted_ready'`)
                                │
                                ▼
                 [ 08:00 AM TELEGRAM REVIEW PUSH ]
   └─► Pushes 45-50 formatted cards with inline buttons:
       [✅ Approve & Send Email]  [✏️ Edit Email]  [❌ Skip Draft]
                                │
                                ▼
                [ TIMEZONE-AWARE GMAIL DISPATCH ]
   └─► Approved emails sent via Gmail API between 09:00 - 11:00 AM recipient local time
       Appends native default Gmail signature & converts markdown links to HTML <a href>
```

---

## ✨ Key Features

- **Sub-Second LLM Generation**: Uses **Google Gemini 3.6 Flash** (< 300ms per draft) with zero local GPU load or local VRAM footprint.
- **Human-in-the-Loop Control**: Inline Telegram buttons allowing real-time `Approve`, `Edit`, or `Skip` actions directly on your phone.
- **Zero Token & Security Leakage**: `.env`, `token.json`, and database files are isolated. API keys are encrypted via GitHub Secrets.
- **Deliverability & MX Verification**: Verifies email domain MX records to prevent bounces and protect your sender domain reputation.
- **Proof-of-Work Messaging**: Personalization links real engineering proof (`SideDoor`, `drift-watch` at `Oximy YC26`) directly to the target startup's stack.
- **Cloud Native Scheduling**: Deploys via **GitHub Actions** (`.github/workflows/outreach_cron.yml`) to execute 100% autonomously without keeping your laptop open.

---

## ⚡ Quickstart & Local Setup

### 1. Requirements
- Python 3.11+
- Git & WSL (or Linux / macOS)
- Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/))
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))

### 2. Installation
```bash
git clone https://github.com/codeharsh27/outreach-agent.git
cd outreach-agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory:

```env
# Gemini API Key (Free, sub-second generation)
GEMINI_API_KEY=AIzaSy...

# Telegram Bot Setup
TELEGRAM_BOT_TOKEN=8777139128:...
TELEGRAM_CHAT_ID=1918356...

# Gmail Sender Configuration
GMAIL_SENDER_EMAIL=you@gmail.com
```

### 4. Authenticate Gmail API
Run the one-time OAuth setup script:
```bash
python3 scripts/setup_gmail.sh
```

---

## 🕹️ Usage & Command Reference

| Command | Action |
|---|---|
| `python3 -m agents.orchestrate run` | Runs full end-to-end daily pipeline. |
| `python3 -m agents.orchestrate minibatch` | Runs a 15-company background pre-stage micro-batch. |
| `python3 -m agents.orchestrate draft_night` | Runs night drafting for pre-staged companies using Gemini 3.6 Flash. |
| `python3 -m agents.orchestrate morning_push` | Pushes ready cards to Telegram app at 8 AM. |
| `python3 -m agents.orchestrate stats` | Prints live database metrics and pipeline state. |

---

## ☁️ Autonomous Cloud Deployment (GitHub Actions)

This project runs 100% autonomously on **GitHub Actions**.

1. Fork or push this repository to GitHub (`codeharsh27/outreach-agent`).
2. Navigate to **Settings → Secrets and variables → Actions**.
3. Add the following repository secrets:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GMAIL_SENDER_EMAIL`

The cron workflow ([`.github/workflows/outreach_cron.yml`](.github/workflows/outreach_cron.yml)) executes every Monday through Friday at 08:00 AM UTC.

---

## 🛡️ License

MIT License. Designed and built by [Harsh Mule](https://github.com/codeharsh27).
