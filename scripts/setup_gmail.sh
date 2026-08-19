#!/bin/bash
# Gmail API Setup Guide + OAuth flow
# Run: bash /mnt/c/Users/asus/outreach-agent/scripts/setup_gmail.sh

PROJ="/mnt/c/Users/asus/outreach-agent"
CREDS_PATH="$PROJ/config/gmail_credentials.json"

echo "================================================"
echo " Gmail API Setup"
echo "================================================"
echo ""
echo "Step 1: Create Google Cloud Project + Enable Gmail API"
echo "-------------------------------------------------------"
echo "Open this URL in your Windows browser:"
echo ""
echo "  https://console.cloud.google.com/apis/library/gmail.googleapis.com"
echo ""
echo "Do this:"
echo "  1. Sign in with harshmude27@gmail.com"
echo "  2. Click 'Create Project' (top left dropdown) → name it 'outreach-agent'"
echo "  3. Click 'ENABLE' to enable Gmail API"
echo ""
read -p "Press ENTER when Gmail API is enabled..."

echo ""
echo "Step 2: Create OAuth 2.0 Credentials"
echo "--------------------------------------"
echo "Open this URL:"
echo ""
echo "  https://console.cloud.google.com/apis/credentials"
echo ""
echo "Do this:"
echo "  1. Click '+ CREATE CREDENTIALS' → 'OAuth client ID'"
echo "  2. If prompted for consent screen: External → fill in app name 'outreach-agent' → your email → save"
echo "  3. Application type: 'Desktop app'"
echo "  4. Name: 'outreach-agent-desktop'"
echo "  5. Click CREATE"
echo "  6. Click 'DOWNLOAD JSON' on the credentials that appear"
echo "  7. Save the file anywhere on your Windows desktop"
echo ""
read -p "Press ENTER when you have downloaded the credentials JSON..."

echo ""
echo "Step 3: Place credentials file"
echo "--------------------------------"
echo "Run this in a NEW PowerShell window (not WSL):"
echo ""
echo "  Copy-Item \"\$env:USERPROFILE\\Downloads\\client_secret_*.json\" \"C:\\Users\\asus\\outreach-agent\\config\\gmail_credentials.json\""
echo ""
echo "(Replace the filename with whatever Google named it)"
echo ""
read -p "Press ENTER when credentials.json is in config/ folder..."

# Verify file exists
if [ ! -f "$CREDS_PATH" ]; then
    echo "❌ File not found at: $CREDS_PATH"
    echo "   Make sure you copied it to config/gmail_credentials.json"
    exit 1
fi
echo "✅ credentials.json found"

echo ""
echo "Step 4: Running OAuth authentication flow..."
echo "----------------------------------------------"
echo "A URL will appear — open it in your Windows browser, sign in,"
echo "allow permissions, and paste the code back here."
echo ""

# Activate venv
source "$HOME/.venvs/outreach-agent/bin/activate"

# Run the auth script
python3 "$PROJ/scripts/gmail_auth.py"
