#!/bin/bash
# Quick diagnostic — show what the YC API batch field actually looks like
source /mnt/c/Users/asus/outreach-agent/config/wsl_env.sh
cd /mnt/c/Users/asus/outreach-agent

python3 - << 'EOF'
import httpx, json, collections

r = httpx.get("https://yc-oss.github.io/api/companies/hiring.json", timeout=15)
companies = r.json()

# Show unique batch values
batches = collections.Counter(c.get("batch","(none)") for c in companies)
print(f"Total companies: {len(companies)}")
print(f"\nAll batch values seen:")
for batch, count in sorted(batches.items(), key=lambda x: -x[1])[:30]:
    print(f"  {repr(batch):30s}  {count} companies")

print(f"\nSample company fields:")
sample = companies[0]
print(json.dumps({k: sample.get(k) for k in 
    ["name","batch","website","one_liner","github","tags","team_size"]}, indent=2))
EOF
