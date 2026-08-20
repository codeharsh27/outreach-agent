<img width="1397" height="218" alt="image" src="https://github.com/user-attachments/assets/e06db397-c94e-4819-b117-28e69ab9696c" />

# Outreach Agent - Built using Hermes Agent

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License: MIT"></a>
  <a href="https://github.com/codeharsh27/outreach-agent"><img src="https://img.shields.io/badge/Built%20by-Harsh%20Mule-6e40c9?style=flat-square" alt="Built by Harsh Mule"></a>
  <a href="https://supabase.com"><img src="https://img.shields.io/badge/Database-Supabase-3ecf8e?style=flat-square" alt="Supabase"></a>
  <a href="https://aistudio.google.com"><img src="https://img.shields.io/badge/LLM-Gemini%20Flash-4285F4?style=flat-square" alt="Gemini Flash"></a>
  <img src="https://img.shields.io/badge/Platform-GitHub%20Actions-2088FF?style=flat-square" alt="GitHub Actions">
</p>

An autonomous outreach agent for software engineers. Discovers high-fit startups, finds contacts, generates personalized cold emails using Gemini Flash, and delivers interactive review cards to Telegram every morning. Approve, edit, or skip — then emails go out via Gmail during recipient business hours.

Runs 100% in the cloud via GitHub Actions. No laptop required after setup.

---

## How It Works

```
Afternoon / Evening (background)
  Discover startups  →  Light research  →  Find contact email

Midnight
  Gemini Flash generates personalized cold emails  (<300ms per draft)

8:00 AM
  Draft cards stream to your Telegram app

You (from your phone)
  [Approve & Send]   [Edit Email]   [Skip]

Gmail
  Sends during recipient business hours (9-11 AM local time)
  Randomized 2-8 min delay between sends
  Appends your Gmail signature automatically
```

---

## Features

| | |
|---|---|
| **Staggered pipeline** | Runs in 15-company micro-batches throughout the day to avoid API rate limits. |
| **Sub-second drafting** | Google Gemini Flash generates each email in under 300ms. No local GPU needed. |
| **Personalized voice** | Emails are written in your voice — your name, role, projects, and email examples. |
| **Human review gate** | Every email passes through you on Telegram before it sends. |
| **Live editing** | Tap Edit in Telegram, reply with your changes. The card updates instantly. |
| **MX verification** | Checks domain mail records before drafting to avoid bounces. |
| **Timezone-aware send** | Gmail API sends during 9-11 AM recipient local time, not yours. |
| **Cloud-persistent DB** | Supabase stores all data. Companies, contacts, and drafts survive between GitHub Actions runs. |
| **Multi-user safe** | Each user runs their own Supabase project. No shared state, no mixing. |

---

## One-Paste Agent Setup

> If you are using an AI coding agent (Claude, Cursor, Antigravity, or similar), copy the prompt below and paste it into your agent. The agent will handle the full setup interactively — checking dependencies, collecting keys, setting up Supabase, and configuring GitHub Actions.

```
You are setting up the Outreach Agent from https://github.com/codeharsh27/outreach-agent.
Follow these steps in order. At each step, check whether it is already done before proceeding.
If you need a value from the user (API key, URL, etc.), explain what it is, where to get it, and wait for them to paste it.

Step 1 — Environment check
- Are we running on Linux, macOS, or WSL2?
- If on bare Windows (not WSL), tell the user to open WSL2 first: run `wsl --install` in PowerShell, reboot, then come back.
- Check: Python 3.11+ is installed. If not, install via: sudo apt install python3 python3-pip python3-venv
- Check: git is installed. If not, install via: sudo apt install git

Step 2 — Clone and install
- git clone https://github.com/codeharsh27/outreach-agent.git ~/outreach-agent
- cd ~/outreach-agent
- python3 -m venv .venv && source .venv/bin/activate
- pip install -r requirements.txt

Step 3 — Collect API keys (one at a time, explain each before asking)
a. Gemini API key — free at https://aistudio.google.com/apikey
   Ask the user to paste it.
b. Telegram Bot Token — open Telegram, message @BotFather, send /newbot, follow prompts.
   Ask the user to paste the token.
c. Telegram Chat ID — tell the user to send any message to their new bot, then fetch:
   curl https://api.telegram.org/bot<TOKEN>/getUpdates
   Extract the chat.id value. Ask the user to paste it.
d. Gmail address — ask the user for their Gmail address.

Step 4 — Personalization (for cold email voice)
Ask the user:
- Your full name? (e.g. Harsh Mule)
- Your role? (e.g. Product Engineer, Backend Engineer, Full Stack Developer)
- Your main project name(s)? (e.g. SideDoor & drift-watch)
- One sentence describing what your projects do? (e.g. SideDoor surfaces job opportunities; drift-watch detects API schema drift)
- Your project URL(s) (optional)?
- Your portfolio URL (optional)?
- Your GitHub URL (optional)?

Step 5 — Supabase setup (cloud database, free tier)
- Tell the user to go to https://supabase.com, create a free account, and create a new project.
- Once the project is ready: Project Settings → API
  - Copy "Project URL" (looks like https://xxxx.supabase.co)
  - Copy "anon / public" key (long JWT string starting with eyJ)
- Ask the user to paste both.
- Tell the user to open the SQL Editor in Supabase dashboard and run the contents of scripts/supabase_schema.sql
- Then run this SQL to disable RLS:
  ALTER TABLE companies DISABLE ROW LEVEL SECURITY;
  ALTER TABLE contacts DISABLE ROW LEVEL SECURITY;
  ALTER TABLE drafts DISABLE ROW LEVEL SECURITY;
  ALTER TABLE sends DISABLE ROW LEVEL SECURITY;
  ALTER TABLE follow_ups DISABLE ROW LEVEL SECURITY;

Step 6 — Write .env file
Write all collected values into ~/outreach-agent/.env using the format from .env.example.

Step 7 — Gmail OAuth
- Run: python3 scripts/setup_gmail.py
- A browser window will open. Tell the user to log in and click Allow.
- Confirm the token.json file was created in the config/ directory.

Step 8 — Verify and run first batch
- Run: PYTHONPATH=. python3 -m agents.orchestrate stats
- Confirm Supabase connected and tables are accessible.
- Run: PYTHONPATH=. python3 -m agents.orchestrate minibatch
- Confirm the first 15 companies are discovered, researched, and contacts found.

Step 9 — Configure GitHub Secrets for Autonomous Cloud Execution
Tell the user to go to their GitHub repository → Settings → Secrets and variables → Actions, and add the following repository secrets:
- SUPABASE_URL
- SUPABASE_KEY
- GEMINI_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- GMAIL_SENDER_EMAIL
- GMAIL_TOKEN_JSON (the contents of ~/outreach-agent/config/token.json as a single raw JSON string)
- YOUR_NAME
- USER_ROLE
- USER_PROJECT_NAME
- USER_PROJECT_DESC

If any step fails, read the error carefully, fix it, and continue from where it failed.
```

---

## Manual Setup

### Requirements

- Python 3.11+
- Git and WSL2 (on Windows) or Linux / macOS
- Gemini API key — [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free)
- Telegram bot — [@BotFather](https://t.me/BotFather) (free)
- Supabase project — [supabase.com](https://supabase.com) (free tier)

### Install

```bash
git clone https://github.com/codeharsh27/outreach-agent.git
cd outreach-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database

Create a free Supabase project, then run [`scripts/supabase_schema.sql`](scripts/supabase_schema.sql) in the SQL Editor to create all tables.

Disable Row Level Security on all tables:

```sql
ALTER TABLE companies   DISABLE ROW LEVEL SECURITY;
ALTER TABLE contacts    DISABLE ROW LEVEL SECURITY;
ALTER TABLE drafts      DISABLE ROW LEVEL SECURITY;
ALTER TABLE sends       DISABLE ROW LEVEL SECURITY;
ALTER TABLE follow_ups  DISABLE ROW LEVEL SECURITY;
```

### Environment Variables

Copy `.env.example` to `.env` and fill in all values:

```env
# LLM
GEMINI_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Gmail
GMAIL_SENDER_EMAIL=

# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# Your identity (used in email drafts)
YOUR_NAME=Harsh Mule
YOUR_EMAIL=
USER_ROLE=Product Engineer
USER_PROJECT_NAME=SideDoor & drift-watch
USER_PROJECT_DESC=SideDoor surfaces evidenced job opportunities; drift-watch detects API schema drift.
SIDEDOOR_URL=https://sidedoor-chi.vercel.app/
PORTFOLIO_URL=https://harshmule.vercel.app/
GITHUB_URL=https://github.com/codeharsh27
```

### Gmail Authentication

Run once to authorize Gmail API access:

```bash
python3 scripts/setup_gmail.py
```

A browser window opens. Log in and click Allow. A `config/token.json` file is saved.

### Verify Setup

```bash
PYTHONPATH=. python3 -m agents.orchestrate stats
```

---

## Commands

```bash
# Run full pipeline end-to-end
PYTHONPATH=. python3 -m agents.orchestrate run

# Background micro-batch (15 companies: discover + research + contact)
PYTHONPATH=. python3 -m agents.orchestrate minibatch

# Night drafting — generate emails for pre-staged companies
PYTHONPATH=. python3 -m agents.orchestrate draft_night

# Morning push — stream draft cards to Telegram
PYTHONPATH=. python3 -m agents.orchestrate morning_push

# Pipeline stats
PYTHONPATH=. python3 -m agents.orchestrate stats
```

---

## Cloud Deployment (GitHub Actions)

The pipeline runs automatically every weekday at 8:00 AM UTC via [`.github/workflows/outreach_cron.yml`](.github/workflows/outreach_cron.yml).

Add these secrets to your GitHub repository under **Settings → Secrets and variables → Actions**:

| Secret Name | Description / Example Value |
|---|---|
| `SUPABASE_URL` | `https://idbqrcmrohvwhgfwhqhw.supabase.co` |
| `SUPABASE_KEY` | Supabase anon key starting with `eyJ...` |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram chat ID |
| `GMAIL_SENDER_EMAIL` | `harshmude27@gmail.com` |
| `GMAIL_TOKEN_JSON` | Raw content of `config/token.json` as a single JSON string |
| `YOUR_NAME` | `Harsh Mule` |
| `USER_ROLE` | `Product Engineer` |
| `USER_PROJECT_NAME` | `SideDoor & drift-watch` |
| `USER_PROJECT_DESC` | `SideDoor surfaces job opportunities; drift-watch detects API schema drift.` |

Once secrets are set, the pipeline runs 100% autonomously in the cloud. Your laptop can be off.

---

## Telegram Card Flow

Each morning, cards arrive in your Telegram app:

```
PostHog  ·  James  ·  posthog.com
hey@posthog.com

--- EMAIL DRAFT ---
Subject: When GitHub approval events silently drift

Hi James,
Diving through PostHog's open-source repo...

[Approve & Send Email]   [Edit Email]   [Skip Draft]
```

Tapping **Edit Email** prompts you to reply with your revised text. The card updates live. Tapping **Approve** queues the email for timezone-aware Gmail delivery.

---

If you find Outreach Agent useful, please give it a ⭐ on GitHub!

## License
MIT. Built by [Harsh Mule](https://github.com/codeharsh27).
