"""
Gmail OAuth authentication script.
Runs the one-time auth flow and saves token.json to config/.
After this runs once, the outreach agent can send email without re-auth.
"""

import os
import sys
import json
from pathlib import Path

PROJ = Path("/mnt/c/Users/asus/outreach-agent")
CREDS_FILE = PROJ / "config" / "gmail_credentials.json"
TOKEN_FILE = PROJ / "config" / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.send",
          "https://www.googleapis.com/auth/gmail.readonly"]

def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("❌ Missing Google libraries. Run the installer first.")
        sys.exit(1)

    creds = None

    # Load existing token if available
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing existing token...")
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                print(f"❌ credentials.json not found at {CREDS_FILE}")
                print("   Run setup_gmail.sh first.")
                sys.exit(1)

            print("Starting OAuth flow...")
            print("=" * 50)
            print("A URL will appear below.")
            print("Open it in your Windows browser, sign in with")
            print("harshmude27@gmail.com, allow all permissions.")
            print("=" * 50)
            print()

            # Use console flow — works in WSL without a browser
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS_FILE), SCOPES
            )
            # run_console() prints URL + prompts for code — perfect for WSL
            creds = flow.run_local_server(
                port=0,
                authorization_prompt_message=
                    "\nOpen this URL in your Windows browser:\n{url}\n",
                success_message=
                    "✅ Authentication successful! You can close this tab.",
                open_browser=False,
            )

        # Save token for future use
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"\n✅ Token saved to {TOKEN_FILE}")

    # Test the connection
    print("\nTesting Gmail connection...")
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress")
        total = profile.get("messagesTotal", 0)
        print(f"✅ Connected as: {email}")
        print(f"   Total messages in inbox: {total:,}")
        print()
        print("=" * 50)
        print(" Gmail API setup complete!")
        print("=" * 50)
        print()
        print("Next step: Build the agents!")
        print("The outreach agent can now send emails from your account.")
    except Exception as e:
        print(f"❌ Gmail API test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
