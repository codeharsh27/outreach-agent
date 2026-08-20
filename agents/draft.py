"""
Draft agent — generates personalized cold emails only.
LinkedIn and X drafts removed — email is the only outreach channel here.

Uses Google Gemini Flash (sub-second) with the user's own voice rules,
3 real email examples as few-shot, and personalization from .env.
"""
import httpx
import json
import time
from openai import OpenAI
from agents.config import (
    OLLAMA_HOST, OLLAMA_MODEL,
    YOUR_NAME, SIDEDOOR_URL, PORTFOLIO_URL,
    TWITTER_URL, LINKEDIN_URL, GITHUB_URL,
    GMAIL_SENDER, GEMINI_API_KEY, OPENROUTER_API_KEY,
    USER_ROLE, USER_PROJECT_NAME, USER_PROJECT_DESC,
)
from agents.tracker import save_draft, update_company_status, verify_connection

ollama = OpenAI(base_url=f"{OLLAMA_HOST}/v1", api_key="ollama")

# ── Few-shot examples (real emails that worked) ───────────────────
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

# ── System prompt — built from personalization vars ───────────────
SYSTEM_PROMPT = f"""You are writing cold outreach emails on behalf of {YOUR_NAME}, a {USER_ROLE} who built {USER_PROJECT_NAME} ({SIDEDOOR_URL}).

About their project: {USER_PROJECT_DESC}

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
2. Connection (1-2 sentences): link their specific problem to what {YOUR_NAME} has built
   - Reference built projects naturally: {USER_PROJECT_NAME} ({SIDEDOOR_URL}), Portfolio ({PORTFOLIO_URL})
3. Ask (1 sentence, soft, genuine, ONE thing only):
   - "Worth pointing X at Y?" (technical)
   - "Genuinely curious how you've solved X." (intellectual)
   - "If there's a problem at [Company] where an extra pair of hands could move it, I'd love to take a shot." (work offer)
4. DO NOT add signature lines, "--" dividers, or horizontal bars. Keep the body clean and natural.

Tone:
- Match their public voice — casual if they tweet casually, precise if they write technical posts
- Never corporate, never apologetic, never templated, no artificial dividers or AI signatures
- Short is always better. Under 120 words is ideal.

Here are 3 real examples of emails that worked:
{FEW_SHOT_EXAMPLES}

IMPORTANT: Output ONLY valid JSON, nothing else. No markdown code blocks."""


# ── Cloud LLM API Client ──────────────────────────────────────────

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Call Gemini Flash (primary), OpenRouter (fallback), then local Ollama.
    Returns raw text response from the model.
    """
    # 1. Gemini API (Free, sub-second)
    if GEMINI_API_KEY and len(GEMINI_API_KEY.strip()) > 5:
        for model in ["gemini-2.5-flash-lite", "gemini-1.5-flash-latest", "gemini-2.0-flash"]:
            try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={GEMINI_API_KEY.strip()}"
                )
                payload = {
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "temperature": 0.7,
                        "response_mime_type": "application/json",
                    },
                }
                r = httpx.post(url, json=payload, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                elif r.status_code not in (404, 429):
                    print(f"    [Gemini ({model})] HTTP {r.status_code}: {r.text[:100]}")
            except Exception:
                pass

    # 2. OpenRouter fallback
    if OPENROUTER_API_KEY and len(OPENROUTER_API_KEY.strip()) > 5:
        or_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY.strip()
        )
        for m in ["google/gemini-2.0-flash-001", "meta-llama/llama-3.3-70b-instruct"]:
            try:
                response = or_client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=0.7,
                )
                text = response.choices[0].message.content.strip()
                if text:
                    return text
            except Exception:
                pass

    # 3. Local Ollama (final fallback)
    response = ollama.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


# ── Email draft generation ────────────────────────────────────────

def generate_draft(company: dict, contact: dict) -> dict:
    """
    Generate a personalized cold email for one company/contact pair.
    Returns: {"email_subject": "...", "email_body": "..."}
    """
    company_name = company.get("name", "")
    contact_name = (
        contact.get("contact_name") or contact.get("name") or ""
    ).split()[0] or "there"
    domain       = company.get("domain", "")
    pain_point   = company.get("pain_point", "")
    evidence_url = company.get("evidence_url", "")
    angle        = company.get("suggested_angle", "")

    print(f"  ✍️  Drafting email for {company_name} → {contact_name}")

    user_prompt = f"""Company: {company_name}
Contact first name: {contact_name}
Their domain: {domain}
Pain point found: {pain_point}
Evidence URL: {evidence_url}
Suggested angle: {angle}

Write a cold outreach email in {YOUR_NAME}'s voice.
Keep body under 120 words. No signature lines or -- dividers.

Output ONLY this JSON:
{{
  "email_subject": "...",
  "email_body": "Hi {contact_name},\\n..."
}}"""

    try:
        text = call_llm(SYSTEM_PROMPT, user_prompt)

        # Extract JSON even if model adds surrounding text
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            draft = json.loads(text[start:end])

            # Strip any accidental -- dividers or signature lines
            body = draft.get("email_body", "")
            if "--" in body:
                body = body.split("--")[0].strip()
                draft["email_body"] = body

            return draft

    except Exception as e:
        print(f"    [Draft LLM] Error: {e}")

    # Fallback
    return {
        "email_subject": f"Quick thought about {company_name}",
        "email_body":    f"Hi {contact_name},\n\n{angle}",
    }


# ── Main draft run ────────────────────────────────────────────────

def run(limit: int = 45):
    """Generate email drafts for top N contacted companies with no draft yet."""
    print("\n✍️  Running draft agent...")
    verify_connection()

    from agents.tracker import _sb
    sb = _sb()

    # Get companies that have a contact but no draft yet
    drafted_res = sb.table("drafts").select("company_id").execute()
    drafted_ids = {r["company_id"] for r in (drafted_res.data or [])}

    rows_res = sb.table("companies") \
        .select(
            "id as company_id, name, domain, pain_point, evidence_url, suggested_angle, tier, fit_score, "
            "contacts!contacts_company_id_fkey(id, name, email)"
        ) \
        .not_.is_("pain_point", "null") \
        .order("fit_score", desc=True) \
        .limit(limit * 3) \
        .execute()

    rows = []
    for r in (rows_res.data or []):
        if r["company_id"] in drafted_ids:
            continue
        contacts_list = r.get("contacts", []) or []
        if not contacts_list:
            continue
        contact = contacts_list[0]
        rows.append((r, contact))
        if len(rows) >= limit:
            break

    print(f"   {len(rows)} companies need email drafts\n")

    drafted = 0
    for company, contact in rows:
        try:
            draft = generate_draft(company, contact)
            save_draft(company["company_id"], contact["id"], {
                "email_subject": draft.get("email_subject", ""),
                "email_body":    draft.get("email_body", ""),
                "status":        "drafted_ready",
            })
            update_company_status(company["company_id"], "drafted_ready")
            drafted += 1
            print(f"    ✅ {company['name']}: '{draft.get('email_subject', '')[:55]}'")
            time.sleep(4.0)  # Stay within Gemini free tier 15 RPM
        except Exception as e:
            print(f"    ❌ {company['name']}: {e}")

    print(f"\n✅ Draft agent complete: {drafted}/{len(rows)} drafts created")


if __name__ == "__main__":
    run()
