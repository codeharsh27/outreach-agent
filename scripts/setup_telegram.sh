#!/bin/bash
# Setup Telegram bot as approval gate for outreach drafts
# Run: bash /mnt/c/Users/asus/outreach-agent/scripts/setup_telegram.sh

ENV_FILE="/mnt/c/Users/asus/outreach-agent/.env"

echo "================================================"
echo " Telegram Approval Gate Setup"
echo "================================================"
echo ""
echo "Step 1: Create your Telegram bot"
echo "---------------------------------"
echo "1. Open Telegram app (phone or desktop)"
echo "2. Search for: @BotFather"
echo "3. Send: /newbot"
echo "4. Name it: OutreachApproval"
echo "5. Username: outreach_harsh_bot (or any unique name ending in _bot)"
echo "6. BotFather will give you a token like: 7234567890:AAExxxxxxxxxxxxxxx"
echo ""
read -p "Paste your bot token here: " BOT_TOKEN

if [ -z "$BOT_TOKEN" ]; then
    echo "❌ No token entered. Run this script again when ready."
    exit 1
fi

echo ""
echo "Step 2: Get your Telegram Chat ID"
echo "----------------------------------"
echo "1. Send ANY message to your new bot in Telegram (e.g. 'hello')"
echo "2. We'll fetch your chat ID automatically..."
echo ""
echo "Waiting 5 seconds for you to send a message to your bot..."
sleep 5

UPDATES=$(curl -s "https://api.telegram.org/bot$BOT_TOKEN/getUpdates")
CHAT_ID=$(echo "$UPDATES" | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('result', [])
if results:
    print(results[-1]['message']['chat']['id'])
else:
    print('')
" 2>/dev/null)

if [ -z "$CHAT_ID" ]; then
    echo "⚠️  Couldn't auto-detect chat ID."
    echo "Go to: https://api.telegram.org/bot${BOT_TOKEN}/getUpdates"
    echo "Find: result[0].message.chat.id"
    echo ""
    read -p "Paste your chat ID here: " CHAT_ID
fi

echo "✅ Chat ID: $CHAT_ID"

# Update .env file
sed -i "s|TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$BOT_TOKEN|" "$ENV_FILE"
sed -i "s|TELEGRAM_CHAT_ID=.*|TELEGRAM_CHAT_ID=$CHAT_ID|" "$ENV_FILE"

echo ""
echo "Step 3: Testing the bot..."
TEST_RESULT=$(curl -s -X POST \
    "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    -d "chat_id=$CHAT_ID" \
    -d "text=✅ Outreach Agent connected! You will receive draft approvals here." \
    -d "parse_mode=HTML")

if echo "$TEST_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
    echo "✅ Test message sent to your Telegram!"
    echo ""
    echo "================================================"
    echo " Telegram setup complete!"
    echo "================================================"
    echo ""
    echo "Bot token and Chat ID saved to .env"
    echo ""
    echo "Next step: Set up Gmail API"
    echo "Run: bash /mnt/c/Users/asus/outreach-agent/scripts/setup_gmail.sh"
else
    echo "❌ Test message failed. Check your token and try again."
    echo "Response: $TEST_RESULT"
fi
