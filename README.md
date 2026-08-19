# Outreach Agent 🛰️

<p align="center">
  <a href="https://github.com/codeharsh27/outreach-agent"><img src="https://img.shields.io/badge/Docs-outreach--agent.github.io-FFD700?style=for-the-badge" alt="Documentation"></a>
  <a href="https://t.me/BotFather"><img src="https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Bot"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/codeharsh27"><img src="https://img.shields.io/badge/Built%20by-Harsh%20Mule-blueviolet?style=for-the-badge" alt="Built by Harsh Mule"></a>
</p>

**The autonomous, sub-second outreach & lead discovery agent.** Designed for high-velocity software engineers seeking job and contract opportunities at YC, VC-backed, and top Indian tech startups. It discovers high-fit companies, performs 3-layer light technical research in 0.1s, generates human-toned outreach with **Google Gemini 3.6 Flash (< 300ms)**, and delivers interactive review cards to your Telegram app with live editing controls.

Run it on a $5 cloud VPS, local WSL2, or **100% serverless via GitHub Actions**. It's not tied to your laptop — review and approve cards from your phone over morning coffee.

---

<table>
<tr><td><b>24-Hour Staggered Pipeline</b></td><td>Continuous background micro-batches (2 PM, 6 PM, 10 PM) discover startups, perform light research, and find contacts without API rate limits.</td></tr>
<tr><td><b>Sub-Second LLM Drafting</b></td><td>Powered by Google Gemini 3.6 Flash (&lt; 300ms per draft) with zero local GPU load or VRAM overhead.</td></tr>
<tr><td><b>Human-in-the-Loop Telegram Control</b></td><td>Delivers interactive cards to your Telegram app with inline buttons: <code>[✅ Approve & Send]</code>, <code>[✏️ Edit Email]</code>, and <code>[❌ Skip]</code>.</td></tr>
<tr><td><b>Interactive Real-Time Editing</b></td><td>Tap <code>[✏️ Edit Email]</code> directly in Telegram to customize your copy before approval — card text refreshes live in your chat.</td></tr>
<tr><td><b>Deliverability & MX Verification</b></td><td>Verifies recipient domain MX records and contact emails before drafting to protect domain reputation and prevent bounces.</td></tr>
<tr><td><b>Proof-of-Work Personalization</b></td><td>Connects real engineering projects (<code>SideDoor</code>, <code>drift-watch</code> at <code>Oximy YC26</code>) directly to the target startup's technical pain points.</td></tr>
<tr><td><b>Timezone-Aware Gmail Dispatch</b></td><td>Sends emails via Gmail API between 9:00 AM – 11:00 AM recipient local time with 2–8 minute randomized delays and native Gmail signatures.</td></tr>
<tr><td><b>Zero Data & Credential Leakage</b></td><td>Secret keys live encrypted in GitHub Secrets. Markdown links automatically convert to clean HTML <code>&lt;a href="..."&gt;</code> tags without ugly raw URLs.</td></tr>
</table>

---

## ⚡ Quickstart

### Linux, macOS, WSL2

```bash
git clone https://github.com/codeharsh27/outreach-agent.git
cd outreach-agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup (`.env`)

Create a `.env` file in the project root:

```env
# Gemini API Key (Free, sub-second generation)
GEMINI_API_KEY=AIzaSy...

# Telegram Bot Token & Chat ID
TELEGRAM_BOT_TOKEN=8777139128:...
TELEGRAM_CHAT_ID=1918356...

# Gmail Sender Address
GMAIL_SENDER_EMAIL=you@gmail.com
```

### One-Time Gmail API Authentication

```bash
python3 scripts/setup_gmail.sh
```

---

## 🕹️ CLI & Pipeline Commands

Outreach Agent has a unified CLI entry point (`agents.orchestrate`):

| Action | Command | Description |
|---|---|---|
| **Run Full Pipeline** | `python3 -m agents.orchestrate run` | Runs discovery → research → contact → draft → Telegram push → Gmail send |
| **Run Micro-Batch** | `python3 -m agents.orchestrate minibatch` | Runs a 15-company background pre-stage job (Discovery + Research + Contact) |
| **Night Drafting** | `python3 -m agents.orchestrate draft_night` | Runs Gemini 3.6 Flash drafting for pre-staged companies |
| **Morning Telegram Push** | `python3 -m agents.orchestrate morning_push` | Streams 45–50 pre-staged draft cards to Telegram app at 8:00 AM |
| **Pipeline Metrics** | `python3 -m agents.orchestrate stats` | Prints real-time database counts, tier breakdown, and draft status |

---

## 📱 Telegram Interactive Card Reference

When cards land on your Telegram app, you control the workflow with 3 inline buttons:

```
┌─────────────────────────────────────────────────────────────┐
│ 🏢 PostHog  ·  James  ·  posthog.com                        │
│ 📧 hey@posthog.com                                          │
│                                                             │
│ ━━━━━━ EMAIL DRAFT ━━━━━━                                   │
│ Subject: When GitHub approval events silently drift...      │
│                                                             │
│ Hi James,                                                   │
│ Diving through PostHog's open-source repo, I noticed how    │
│ tricky it gets to track GitHub approval states...           │
│                                                             │
│ ━━━━━━ LINKEDIN (copy-paste) ━━━━━━                         │
│ Hey James, noticed how PostHog tracks GitHub approval...    │
│                                                             │
│ ━━━━━━ X REPLY ━━━━━━                                       │
│ The hardest part of tracking multi-provider event states... │
└─────────────────────────────────────────────────────────────┘
  [✅ Approve & Send Email]  [✏️ Edit Email]  [❌ Skip Draft]
```

- **`[✅ Approve & Send Email]`**: Queues email for timezone-aware Gmail sending.
- **`[✏️ Edit Email]`**: Reply with custom copy → database updates → card refreshes live on your screen.
- **`[❌ Skip Draft]`**: Archives draft and removes card.

---

## ☁️ Autonomous Cloud Deployment (GitHub Actions)

Outreach Agent runs 100% autonomously in the cloud via **GitHub Actions**.

1. Push your repository to GitHub (`codeharsh27/outreach-agent`).
2. Go to **Settings → Secrets and variables → Actions**.
3. Add these 4 encrypted repository secrets:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GMAIL_SENDER_EMAIL`

The cron workflow ([`.github/workflows/outreach_cron.yml`](.github/workflows/outreach_cron.yml)) executes every Monday through Friday at 08:00 AM UTC. Your laptop can be completely off while cards stream to your phone every morning.

---

## 🛡️ License & Author

MIT License. Designed and engineered by **[Harsh Mule](https://github.com/codeharsh27)**.
