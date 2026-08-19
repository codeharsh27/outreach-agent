import time
from agents.draft import call_llm

start = time.time()
print("Calling Cloud LLM API...")
res = call_llm("You are a helpful JSON assistant", 'Output JSON: {"status": "ok", "message": "hello"}')
elapsed = time.time() - start

print(f"\n✅ Completed in {elapsed:.2f} seconds!")
print(f"Response:\n{res}")
