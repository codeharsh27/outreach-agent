#!/bin/bash
# Check Ollama connectivity from WSL and list models

# Try multiple ways to get Windows host IP from WSL2
NAMESERVER=$(cat /etc/resolv.conf 2>/dev/null | grep nameserver | awk '{print $2}' | head -1)
GATEWAY=$(ip route show default 2>/dev/null | awk '/default/ {print $3}' | head -1)

echo "Detected DNS/nameserver: $NAMESERVER"
echo "Detected gateway: $GATEWAY"
echo ""
echo "Testing Ollama connectivity..."

# Try all possible host IPs in order
for HOST in "$GATEWAY" "$NAMESERVER" "host.docker.internal" "127.0.0.1" "localhost"; do
    [ -z "$HOST" ] && continue
    RESULT=$(curl -s --connect-timeout 2 "http://$HOST:11434/api/tags" 2>/dev/null)
    if [ -n "$RESULT" ] && echo "$RESULT" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        echo "✅ Connected at http://$HOST:11434"
        echo ""
        echo "Installed models:"
        echo "$RESULT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
models = data.get('models', [])
if not models:
    print('  (No models installed yet)')
for m in models:
    size_gb = round(m['size'] / 1e9, 1)
    print(f'  {m[\"name\"]} - {size_gb} GB')
"
        echo ""
        echo "OLLAMA_WSL_HOST=http://$HOST:11434" > /tmp/ollama_host.txt
        echo "✅ Host saved: http://$HOST:11434"
        exit 0
    fi
done

echo "❌ Cannot reach Ollama at any host."
echo ""
echo "Make sure you ran this in PowerShell BEFORE 'ollama serve':"
echo '  $env:OLLAMA_HOST = "http://0.0.0.0:11434"'
echo "  ollama serve"
