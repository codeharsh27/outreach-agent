#!/bin/bash
# Verify Ollama + model installation from WSL

GATEWAY=$(ip route show default 2>/dev/null | awk '/default/ {print $3}' | head -1)
NAMESERVER=$(cat /etc/resolv.conf 2>/dev/null | grep nameserver | awk '{print $2}' | head -1)

OLLAMA_HOST=""
for HOST in "$GATEWAY" "$NAMESERVER" "host.docker.internal" "127.0.0.1"; do
    [ -z "$HOST" ] && continue
    RESULT=$(curl -s --connect-timeout 2 "http://$HOST:11434/api/tags" 2>/dev/null)
    if [ -n "$RESULT" ]; then
        OLLAMA_HOST="http://$HOST:11434"
        break
    fi
done

if [ -z "$OLLAMA_HOST" ]; then
    echo "❌ Ollama not reachable. Make sure 'ollama serve' is running in PowerShell with:"
    echo '   $env:OLLAMA_HOST = "http://0.0.0.0:11434"'
    echo "   ollama serve"
    exit 1
fi

echo "✅ Ollama reachable at: $OLLAMA_HOST"
echo ""

# Save for other scripts
echo "OLLAMA_WSL_HOST=$OLLAMA_HOST" > /tmp/ollama_host.txt

# List models
echo "Installed models:"
echo "$RESULT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
models = data.get('models', [])
if not models:
    print('  (none yet)')
for m in models:
    size_gb = round(m['size'] / 1e9, 1)
    caps = m.get('details', {}).get('capabilities', [])
    tool_support = '✅ tools' if 'tools' in caps else '⚠️  no tools'
    print(f'  {m[\"name\"]:40s} {size_gb} GB  {tool_support}')
"

echo ""

# Check GitHub token in .env
ENV_FILE="/mnt/c/Users/asus/outreach-agent/.env"
if grep -q "PASTE_YOUR_GITHUB_TOKEN_HERE" "$ENV_FILE" 2>/dev/null; then
    echo "⚠️  GitHub token NOT set yet in .env"
elif grep -q "^GITHUB_TOKEN=gh" "$ENV_FILE" 2>/dev/null; then
    echo "✅ GitHub token looks set in .env"
else
    echo "✅ GitHub token present in .env"
fi

echo ""
echo "All checks done."
