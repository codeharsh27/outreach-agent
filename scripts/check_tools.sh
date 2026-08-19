#!/bin/bash
# Check actual tool-calling capability via /api/show endpoint
# This is more accurate than reading the /api/tags response

OLLAMA_HOST="http://172.21.112.1:11434"

echo "Checking tool-calling support via /api/show..."
echo ""

for MODEL in "qwen2.5:3b" "qwen3:4b"; do
    RESULT=$(curl -s --connect-timeout 3 \
        -X POST "$OLLAMA_HOST/api/show" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$MODEL\"}" 2>/dev/null)
    
    if [ -z "$RESULT" ]; then
        echo "  $MODEL: (not installed)"
        continue
    fi

    # Check capabilities array
    CAPS=$(echo "$RESULT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
caps = d.get('capabilities', [])
details = d.get('details', {})
template = d.get('template', '')
# Tool calling is indicated by 'tools' in capabilities
# or by [TOOL_CALLS] in template
has_tools = 'tools' in caps or '[TOOL_CALLS]' in template or 'tool_calls' in template.lower()
print('tools' if has_tools else 'no_tools')
print('|'.join(caps) if caps else 'none')
" 2>/dev/null)
    
    HAS_TOOLS=$(echo "$CAPS" | head -1)
    CAP_LIST=$(echo "$CAPS" | tail -1)
    
    if [ "$HAS_TOOLS" = "tools" ]; then
        echo "  ✅ $MODEL — tool calling CONFIRMED (capabilities: $CAP_LIST)"
    else
        echo "  ⚠️  $MODEL — no tool calling (capabilities: $CAP_LIST)"
    fi
done
