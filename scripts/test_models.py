import httpx
from agents.config import GEMINI_API_KEY, OPENROUTER_API_KEY
from openai import OpenAI

print(f"GEMINI_API_KEY set: {bool(GEMINI_API_KEY)} (len={len(GEMINI_API_KEY)})")

# Fetch all available models from Gemini API
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY.strip()}"
try:
    r = httpx.get(url, timeout=10)
    if r.status_code == 200:
        models = [m["name"].replace("models/", "") for m in r.json().get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", [])]
        print(f"\n✅ Active Gemini models ({len(models)}): {models}")
    else:
        print(f"Failed to fetch models: HTTP {r.status_code} {r.text[:200]}")
except Exception as e:
        print(f"Error fetching models: {e}")

# Test active models
models = [
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemma-4-26b-a4b-it",
]

for m in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY.strip()}"
    payload = {
        "contents": [{"parts": [{"text": "Say hello in JSON format: {\"greeting\": \"hello\"}"}]}],
        "generationConfig": {"temperature": 0.5, "response_mime_type": "application/json"}
    }
    try:
        r = httpx.post(url, json=payload, timeout=8)
        print(f"\nModel {m} -> HTTP {r.status_code}")
        if r.status_code == 200:
            print("SUCCESS!", r.json()["candidates"][0]["content"]["parts"][0]["text"])
        else:
            print(r.text[:150])
    except Exception as e:
        print(f"Model {m} error: {e}")

# Test OpenRouter models
if OPENROUTER_API_KEY:
    print("\n--- Testing OpenRouter ---")
    or_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY.strip())
    try:
        # Fetch available models list from OpenRouter
        r = httpx.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}"}, timeout=8)
        data = r.json()
        free_models = [m["id"] for m in data.get("data", []) if ":free" in m["id"] or "free" in m.get("pricing", {}).get("prompt", "1")]
        print(f"Available free/cheap OpenRouter models (first 10): {free_models[:10]}")
    except Exception as e:
        print(f"OpenRouter models fetch error: {e}")
