"""Quick httpx sync test with NO_PROXY."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import httpx

API_KEY = os.environ["TRUEFOUNDRY_API_KEY"]
CA = r"C:\Users\r139148\Downloads\ca_bundle.pem"
URL = "https://tfy-dev.aiops.cloudapps.cargill.com/v1/chat/completions"

# Test sync httpx (uses OS socket resolver)
print("Sync httpx test...")
try:
    r = httpx.Client(verify=CA, timeout=15).post(
        URL,
        json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    print(f"SYNC OK: {r.status_code} {r.text[:100]}")
except Exception as e:
    print(f"SYNC FAILED: {e}")

# Test async httpx
import asyncio
async def test_async():
    print("\nAsync httpx test...")
    try:
        async with httpx.AsyncClient(verify=CA, timeout=15) as c:
            r = await c.post(
                URL,
                json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            )
            print(f"ASYNC OK: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"ASYNC FAILED: {e}")

asyncio.run(test_async())
