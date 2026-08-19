"""
Draft agent — generates 3 outreach formats per company:
  1. Email (primary, fully automated send)
  2. LinkedIn message (you copy-paste, 10 sec)
  3. X reply (find a recent tweet, draft a reply, you post)

Uses local Ollama (qwen3:4b) with Harsh's exact voice rules
and 3 real email samples as few-shot examples.
"""
import httpx
import sqlite3
import json
import time
from openai import OpenAI
from agents.config import (
    OLLAMA_HOST, OLLAMA_MODEL, TRACKER_DB,
    YOUR_NAME, SIDEDOOR_URL, PORTFOLIO_URL,
    TWITTER_URL, LINKEDIN_URL, GITHUB_URL,
    GMAIL_SENDER, GEMINI_API_KEY, OPENROUTER_API_KEY
)
from agents.tracker import save_draft

ollama = OpenAI(base_url=f"{OLLAMA_HOST}/v1", api_key="ollama")

# ── Signature (used in all emails) ───────────────────────────────
SIGNATURE = f"""--
{YOUR_NAME}
Building [SideDoor]({SIDEDOOR_URL}) | [Portfolio]({PORTFOLIO_URL})
Socials: [X]({TWITTER_URL}) | [LinkedIn]({LINKEDIN_URL}) | [Github]({GITHUB_URL})"""

# ── Few-shot examples (Harsh's actual emails that worked) ────────
FEW_SHOT_EXAMPLES = """
EXAMPLE 1:
Subject: The silent regression hiding in your normalization layer
Body:
Hi Krrish,
Read a breakdown of how LiteLLM's normalization can quietly drop things across providers, tool-calls argument type, citation fields, safe_settings so provider swap ships a regression nobody catches until it's live.
I have built drift-watch for a similar problem at Oximy(YC26) - diffs vendor API response shapes and flags exactly that kind of silent drift before it hits production. It maps closely onto what your normalization layer risks, just at a bigger scale.
Worth pointing it at a couple of your provider pairs? Or if this is already solved internally, genuinely curious how.

EXAMPLE 2:
Subject: "Most intent data is noise" - what's actually driving signal at OrbitShift.ai then?
Body:
Hi Saurabh,
Caught your line from the roundtable, that "most intent data is noise people pay a premium to feel good about", and AI SDRs are scaling spam faster than trust. Rare for a sales-intelligence CEO to say that about his own category.
Genuinely curious: if intent data's mostly noise, what's the actual signal you trust at OrbitShift now, human-in-the-loop validation, narrower account criteria, something else?
I've been chewing on the same tradeoff building SideDoor - matches candidates to real evidence instead of resume spam. Would value your take if you have two minutes.

EXAMPLE 3:
Subject: Neil, one thing about Intangles is hard to fake
Body:
Hi Neil,
What I find interesting about Intangles is that the data doesn't stay on a dashboard. Eventually it has to tell someone that a machine is about to fail, and be right often enough for them to trust it.
That last part seems much harder than building the model.
I've been thinking about this while building SideDoor. I started with the same question from a different angle: can you find the real problem before you start building the solution?
I'm looking for somewhere I can contribute to problems with that kind of consequence.
If there's a product or engineering problem at Intangles where an extra pair of hands could actually move it forward, I'd love to take a shot at it.
"""

# ── System prompt with voice rules ───────────────────────────────
SYSTEM_PROMPT = f"""You are writing cold outreach on behalf of {YOUR_NAME}, a software engineer who built SideDoor ({SIDEDOOR_URL}) and drift-watch.

VOICE RULES — follow exactly:

Subject line:
- Reference something SPECIFIC about their tech, a quote they said, or their core challenge
- Must make the recipient think "how did they notice that?"
- NEVER: "Quick question", "Collaboration?", "Reaching out", "Hope this finds you well"
- FORMAT: plain text, no quotes around subject, max 12 words

Email body (4-6 sentences MAX, never more):
1. Opening: what you NOTICED about their work — specific, not generic
   - Reference: a code pattern, a public issue, a product behavior, a hiring signal
   - NEVER start with "I", "My name", "Hope", "I saw your profile"
2. Connection (1-2 sentences): link their specific problem to what Harsh has built
   - Reference built projects naturally: SideDoor ({SIDEDOOR_URL}), drift-watch, Oximy (YC26)
3. Ask (1 sentence, soft, genuine, ONE thing only):
   - "Worth pointing X at Y?" (technical)
   - "Genuinely curious how you've solved X." (intellectual)
   - "If there's a problem at [Company] where an extra pair of hands could move it, I'd love to take a shot." (work offer)
4. DO NOT add signature lines, "--" dividers, or horizontal bars. Keep the body clean and natural.

Tone:
- Match their public voice — casual if they tweet casually, precise if they write technical posts
- Never corporate, never apologetic, never templated, no artificial dividers or AI signatures
- Short is always better

Here are 3 real examples of emails Harsh wrote that worked:
{FEW_SHOT_EXAMPLES}

IMPORTANT: Output ONLY valid JSON, nothing else. No markdown code blocks."""


# ── X / Twitter: find recent tweet ───────────────────────────────

def find_recent_tweet(twitter_handle: str) -> dict | None:
    """
    Try to find a recent relevant tweet via nitter (no auth needed).
    Returns {url, text} or None.
    """
    if not twitter_handle:
        return None
    handle = twitter_handle.replace("https://x.com/", "").replace("https://twitter.com/", "").strip("/")
    try:
        # Use nitter as a scraping proxy (no auth needed)
        nitter_instances = ["https://nitter.net", "https://nitter.privacydev.net"]
        for instance in nitter_instances:
            try:
                r = httpx.get(f"{instance}/{handle}", timeout=8,
                              headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200:
                    continue
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, "html.parser")
                tweets = soup.select(".tweet-content")
                links = soup.select(".tweet-link")
                if tweets and links:
                    text = tweets[0].get_text(strip=True)
                    tweet_path = links[0].get("href", "")
                    tweet_url = f"https://x.com{tweet_path}"
                    return {"text": text[:280], "url": tweet_url}
            except Exception:
                continue
    except Exception:
        pass
    return None


# ── Cloud LLM API Client (Gemini Flash - Sub-second) ─────────────

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Call cloud LLM (Gemini Flash or OpenRouter) for sub-second generation.
    Falls back to local Ollama if no cloud API key is present.
    """
    # 1. Try Gemini API (Free, sub-second)
    if GEMINI_API_KEY and len(GEMINI_API_KEY.strip()) > 5:
        for model in ["gemini-3.6-flash", "gemini-1.5-flash-latest", "gemini-2.5-flash-lite", "gemini-3.5-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY.strip()}"
                payload = {
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": 0.7,
                        "response_mime_type": "application/json"
                    }
                }
                r = httpx.post(url, json=payload, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                elif r.status_code != 404:
                    print(f"    [Gemini API ({model})] HTTP {r.status_code}: {r.text[:100]}")
            except Exception as e:
                pass

    # 2. Try OpenRouter API
    if OPENROUTER_API_KEY and len(OPENROUTER_API_KEY.strip()) > 5:
        or_models = [
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-coder-32b-instruct"
        ]
        or_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY.strip())
        for m in or_models:
            try:
                response = or_client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                )
                text = response.choices[0].message.content.strip()
                if text:
                    return text
            except Exception:
                pass

    # 3. Fallback to local Ollama
    response = ollama.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Main draft generation ─────────────────────────────────────────

def generate_draft(company: dict, contact: dict) -> dict:
    """
    Generate email + LinkedIn + X reply drafts for one company in < 1 second.
    Returns dict with all three.
    """
    company_name = company["name"]
    contact_name = (contact.get("contact_name") or contact.get("name") or "").split()[0] or "there"
    domain = company.get("domain", "")
    pain_point = company.get("pain_point", "")
    evidence_url = company.get("evidence_url", "")
    angle = company.get("suggested_angle", "")
    twitter_url = contact.get("twitter_url") or company.get("twitter_url")

    print(f"  ✍️  Drafting for {company_name} → {contact_name}")

    # Find recent tweet for X reply
    tweet = find_recent_tweet(twitter_url) if twitter_url else None

    # Build the prompt
    user_prompt = f"""Company: {company_name}
Contact first name: {contact_name}
Their domain: {domain}
Pain point found: {pain_point}
Evidence URL: {evidence_url}
Suggested angle: {angle}
Recent tweet (if any): {tweet['text'] if tweet else 'none found'}
Tweet URL (if any): {tweet['url'] if tweet else ''}

Write three outreach formats:
1. Email (subject + body in Harsh's voice, MAX 100-140 words total, NO signature lines or -- dividers)
2. LinkedIn DM (same angle, plain text, no markdown links, max 200 chars)
3. X reply to their tweet (max 250 chars, smart observation or question, no pitch)

Output ONLY this JSON structure:
{{
  "email_subject": "...",
  "email_body": "Hi {contact_name},\\n...",
  "linkedin_msg": "...",
  "x_reply_text": "...",
  "x_reply_url": "{tweet['url'] if tweet else ''}"
}}"""

    try:
        text = call_llm(SYSTEM_PROMPT, user_prompt)

        # Extract JSON even if model wraps it
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            draft = json.loads(text[start:end])

            # Clean any accidental -- dividers
            body = draft.get("email_body", "")
            if "--" in body:
                body = body.split("--")[0].strip()
                draft["email_body"] = body

            return draft

    except Exception as e:
        print(f"    [Draft LLM] Error: {e}")

    # Fallback draft
    return {
        "email_subject": f"Quick thought about {company_name}",
        "email_body": f"Hi {contact_name},\n\n{angle}",
        "linkedin_msg": f"Hi {contact_name}, {angle[:150]}",
        "x_reply_text": f"Interesting angle on {pain_point[:100]}",
        "x_reply_url": tweet["url"] if tweet else "",
    }


# ── Main draft run ────────────────────────────────────────────────

def run(limit=45):
    """Generate drafts for top N researched + contacted companies with no draft yet."""
    print("\n✍️  Running draft agent...")

    conn = sqlite3.connect(str(TRACKER_DB))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            co.id as company_id,
            co.name, co.domain, co.twitter_url,
            co.pain_point, co.evidence_url, co.suggested_angle, co.tier,
            ct.id as contact_id,
            ct.name as contact_name,
            ct.email, ct.linkedin_url, ct.twitter_url as contact_twitter
        FROM companies co
        JOIN contacts ct ON ct.company_id = co.id
        WHERE co.pain_point IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM drafts d WHERE d.company_id = co.id
          )
        ORDER BY co.fit_score DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    print(f"   {len(rows)} companies need drafts\n")

    drafted = 0
    from agents.tracker import update_company_status
    for row in rows:
        company = dict(row)
        contact = dict(row)
        try:
            draft = generate_draft(company, contact)
            save_draft(company["company_id"], company["contact_id"], {
                "email_subject": draft.get("email_subject", ""),
                "email_body": draft.get("email_body", ""),
                "linkedin_msg": draft.get("linkedin_msg", ""),
                "x_reply_text": draft.get("x_reply_text", ""),
                "x_reply_url": draft.get("x_reply_url", ""),
                "status": "drafted_ready",
            })
            update_company_status(company["company_id"], "drafted_ready")
            drafted += 1
            print(f"    ✅ {company['name']}: '{draft.get('email_subject', '')[:50]}'")
            time.sleep(4.0)  # Stay within Gemini free tier 15 RPM limit
        except Exception as e:
            print(f"    ❌ {company['name']}: {e}")

    print(f"\n✅ Draft agent complete: {drafted}/{len(rows)} drafts created")


if __name__ == "__main__":
    run()
