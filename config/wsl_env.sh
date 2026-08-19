#!/bin/bash
# WSL environment — source this before running agents
# Usage: source /mnt/c/Users/asus/outreach-agent/config/wsl_env.sh

export OLLAMA_WSL_HOST="http://172.21.112.1:11434"
export OUTREACH_PROJECT="/mnt/c/Users/asus/outreach-agent"
export VENV_DIR="$HOME/.venvs/outreach-agent"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONUNBUFFERED=1
source "$HOME/.venvs/outreach-agent/bin/activate" 2>/dev/null || true
