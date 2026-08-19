#!/bin/bash
# Install Hermes Agent in WSL + configure for outreach pipeline
# Run this from WSL: bash /mnt/c/Users/asus/outreach-agent/scripts/install_hermes.sh

set -e

echo "================================================"
echo " Hermes Agent Installer for Outreach Pipeline"
echo "================================================"
echo ""

# 1. Check Python
echo "[1/6] Checking Python..."
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)
if [ -z "$PYTHON" ]; then
    echo "  Installing Python 3..."
    sudo apt-get update -q && sudo apt-get install -y python3 python3-pip python3-venv
fi
PYTHON_VER=$($PYTHON --version 2>&1)
echo "  ✅ $PYTHON_VER"

# 2. Check pip / uv
echo "[2/6] Installing uv (fast Python package manager)..."
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.cargo/env" 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "  ✅ uv $(uv --version 2>/dev/null || echo 'installed')"

# 3. Create project venv in WSL home (NOT on /mnt/c - NTFS breaks Unix symlinks)
echo "[3/6] Creating Python virtual environment..."
PROJ="/mnt/c/Users/asus/outreach-agent"
VENV_DIR="$HOME/.venvs/outreach-agent"
export PATH="$HOME/.local/bin:$PATH"

mkdir -p "$HOME/.venvs"
if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating venv at $VENV_DIR ..."
    uv venv "$VENV_DIR" --python python3 || {
        echo "  uv venv failed, trying python3 -m venv..."
        python3 -m venv "$VENV_DIR"
    }
fi

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "  ❌ Failed to create venv. Check Python installation."
    exit 1
fi

source "$VENV_DIR/bin/activate"
echo "  ✅ venv at $VENV_DIR"

cd "$PROJ"

# 4. Install core Python deps for the outreach pipeline
echo "[4/6] Installing outreach pipeline dependencies..."
uv pip install --quiet \
    httpx \
    requests \
    beautifulsoup4 \
    PyGithub \
    python-dotenv \
    google-auth \
    google-auth-oauthlib \
    google-api-python-client \
    anthropic \
    openai \
    aiohttp \
    sqlite-utils \
    pytz \
    python-telegram-bot
echo "  ✅ Dependencies installed"

# 5. Try installing Hermes Agent
echo "[5/6] Installing Hermes Agent..."
# Try pip first (simplest)
if pip install -q hermes-agent 2>/dev/null; then
    echo "  ✅ Hermes installed via pip"
else
    echo "  ⚠️  pip install failed, trying from source..."
    if command -v git &>/dev/null; then
        if [ ! -d "$HOME/hermes-agent" ]; then
            git clone https://github.com/NousResearch/hermes-agent.git "$HOME/hermes-agent" 2>/dev/null || true
        fi
        if [ -d "$HOME/hermes-agent" ]; then
            cd "$HOME/hermes-agent"
            pip install -q -e . 2>/dev/null || true
            cd "$PROJ"
            echo "  ✅ Hermes installed from source"
        else
            echo "  ⚠️  Hermes install skipped - will set up alternative scheduler"
        fi
    fi
fi

# 6. Get Ollama host for config
echo "[6/6] Detecting Ollama host..."
GATEWAY=$(ip route show default 2>/dev/null | awk '/default/ {print $3}' | head -1)
NAMESERVER=$(cat /etc/resolv.conf 2>/dev/null | grep nameserver | awk '{print $2}' | head -1)

OLLAMA_HOST_FOUND=""
for HOST in "$GATEWAY" "$NAMESERVER" "host.docker.internal" "127.0.0.1"; do
    [ -z "$HOST" ] && continue
    RESULT=$(curl -s --connect-timeout 2 "http://$HOST:11434/api/tags" 2>/dev/null)
    if [ -n "$RESULT" ]; then
        OLLAMA_HOST_FOUND="http://$HOST:11434"
        echo "  ✅ Ollama reachable at $OLLAMA_HOST_FOUND"
        break
    fi
done

if [ -z "$OLLAMA_HOST_FOUND" ]; then
    echo "  ⚠️  Ollama not reachable right now - make sure 'ollama serve' is running in PowerShell"
    OLLAMA_HOST_FOUND="http://172.x.x.1:11434"
fi

# Write WSL-specific env additions
WSL_ENV="$PROJ/config/wsl_env.sh"
mkdir -p "$PROJ/config"
cat > "$WSL_ENV" << EOF
#!/bin/bash
# WSL environment — source this before running agents
# Usage: source /mnt/c/Users/asus/outreach-agent/config/wsl_env.sh

export OLLAMA_WSL_HOST="$OLLAMA_HOST_FOUND"
export OUTREACH_PROJECT="/mnt/c/Users/asus/outreach-agent"
export VENV_DIR="\$HOME/.venvs/outreach-agent"
export PATH="\$HOME/.local/bin:\$PATH"
source "\$HOME/.venvs/outreach-agent/bin/activate" 2>/dev/null || true
EOF
chmod +x "$WSL_ENV"
echo "  ✅ WSL env config written to config/wsl_env.sh"

echo ""
echo "================================================"
echo " Installation complete!"
echo "================================================"
echo ""
echo "Next step: Set up Telegram bot for approval gate."
echo "Run: bash /mnt/c/Users/asus/outreach-agent/scripts/setup_telegram.sh"
echo ""
echo "To activate the project environment in future WSL sessions:"
echo "  source /mnt/c/Users/asus/outreach-agent/config/wsl_env.sh"
