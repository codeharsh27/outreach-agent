#!/bin/bash
# Install any missing deps and run a test of the pipeline
source /mnt/c/Users/asus/outreach-agent/config/wsl_env.sh

cd /mnt/c/Users/asus/outreach-agent

echo "Installing any missing dependencies..."
uv pip install --quiet dnspython pytz 2>/dev/null || pip install -q dnspython pytz

echo ""
echo "Running pipeline in TEST mode (discover + research + draft, no real send)..."
echo ""

python3 -m agents.orchestrate test
