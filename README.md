# outreach-agent

Automated cold outreach system — email + LinkedIn + X.

## Structure
```
outreach-agent/
├── agents/          # Python agent scripts
├── scripts/         # One-off setup scripts
├── config/          # Gmail credentials, Hermes config
├── data/
│   ├── targets/     # Company target lists (CSV)
│   └── tracker/     # SQLite tracker DB
├── prompts/         # Draft agent system prompts
├── .env             # Real secrets - DO NOT COMMIT
└── .env.example     # Template - safe to commit
```

## Setup
See implementation_plan.md for full setup steps.

## First run
```bash
# In WSL
cd /mnt/c/Users/asus/outreach-agent
python agents/discover.py     # Find today's targets
python agents/research.py     # Research each target
python agents/contact.py      # Find contact info
python agents/draft.py        # Generate drafts
# Then approve on Telegram → Gmail sends automatically
```
