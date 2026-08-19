import json
from agents.draft import generate_draft

company = {
    "name": "PostHog",
    "domain": "posthog.com",
    "pain_point": "Tracking GitHub approval state and event analytics across providers",
    "evidence_url": "https://github.com/PostHog/posthog",
    "suggested_angle": "VC-backed open source analytics startup"
}

contact = {
    "contact_name": "James",
    "email": "james@posthog.com"
}

print("Testing generate_draft with Cloud LLM API...")
draft = generate_draft(company, contact)
print("\n✅ Generated Draft Result:")
print(json.dumps(draft, indent=2))
