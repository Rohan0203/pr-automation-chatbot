"""Minimal TrueFoundry API connectivity test.

Tests 4 approaches to find what works on Cargill's network:
  1. Raw httpx (no proxy, no CA bundle)
  2. Raw httpx (with CA bundle)
  3. Raw httpx (with CA bundle + proxy)
  4. openai SDK (with CA bundle)

Run: python test_tfy.py
"""
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

API_KEY = os.environ["TRUEFOUNDRY_API_KEY"]
BASE_URL = os.environ["TRUEFOUNDRY_BASE_URL"]
MODEL = os.environ["TRUEFOUNDRY_MODEL"]
CA_BUNDLE = os.environ.get("CA_BUNDLE_PATH")
PROXY = (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip() or None

PAYLOAD = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "Say hello in one word."}],
    "max_tokens": 10,
}
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
URL = f"{BASE_URL}/v1/chat/completions"


async def test_1_raw_no_verify():
    """Raw httpx, no SSL verify, no proxy."""
    import httpx
    print("\n--- Test 1: Raw httpx (verify=False, no proxy) ---")
    try:
        async with httpx.AsyncClient(verify=False, timeout=15) as c:
            r = await c.post(URL, json=PAYLOAD, headers=HEADERS)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


async def test_2_raw_ca_bundle():
    """Raw httpx with CA bundle, no proxy."""
    import httpx
    print("\n--- Test 2: Raw httpx (CA bundle, no proxy) ---")
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    print(f"  verify={verify}")
    try:
        async with httpx.AsyncClient(verify=verify, timeout=15) as c:
            r = await c.post(URL, json=PAYLOAD, headers=HEADERS)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


async def test_3_raw_ca_proxy():
    """Raw httpx with CA bundle + proxy."""
    import httpx
    print("\n--- Test 3: Raw httpx (CA bundle + proxy) ---")
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    proxy_url = PROXY or "http://web.prod.proxy.cargill.com:4200"
    print(f"  verify={verify}, proxy={proxy_url}")
    try:
        async with httpx.AsyncClient(verify=verify, proxy=proxy_url, timeout=15) as c:
            r = await c.post(URL, json=PAYLOAD, headers=HEADERS)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


async def test_4_openai_sdk():
    """OpenAI SDK with CA bundle."""
    print("\n--- Test 4: OpenAI SDK (CA bundle, no proxy) ---")
    import httpx
    from openai import AsyncOpenAI
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    print(f"  verify={verify}")
    try:
        http_client = httpx.AsyncClient(verify=verify, timeout=30)
        client = AsyncOpenAI(
            api_key=API_KEY,
            base_url=f"{BASE_URL}/v1",
            http_client=http_client,
        )
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        print(f"Response: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


async def test_5_openai_sdk_proxy():
    """OpenAI SDK with CA bundle + proxy."""
    print("\n--- Test 5: OpenAI SDK (CA bundle + proxy) ---")
    import httpx
    from openai import AsyncOpenAI
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    proxy_url = PROXY or "http://web.prod.proxy.cargill.com:4200"
    print(f"  verify={verify}, proxy={proxy_url}")
    try:
        http_client = httpx.AsyncClient(verify=verify, proxy=proxy_url, timeout=30)
        client = AsyncOpenAI(
            api_key=API_KEY,
            base_url=f"{BASE_URL}/v1",
            http_client=http_client,
        )
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        print(f"Response: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


def test_6_requests_sync():
    """Sync requests library (uses OS DNS resolver)."""
    print("\n--- Test 6: requests (sync, OS resolver, CA bundle) ---")
    import requests as req
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    print(f"  verify={verify}")
    try:
        r = req.post(URL, json=PAYLOAD, headers=HEADERS, verify=verify, timeout=15)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


def test_7_openai_sync():
    """Sync OpenAI SDK."""
    print("\n--- Test 7: OpenAI SDK sync (CA bundle) ---")
    import httpx
    from openai import OpenAI
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    print(f"  verify={verify}")
    try:
        http_client = httpx.Client(verify=verify, timeout=30)
        client = OpenAI(
            api_key=API_KEY,
            base_url=f"{BASE_URL}/v1",
            http_client=http_client,
        )
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        print(f"Response: {resp.choices[0].message.content}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


async def test_8_async_transport_mapped():
    """Async httpx with custom transport that maps hostname to IP."""
    print("\n--- Test 8: httpx AsyncClient with transport (map host→IP) ---")
    import httpx
    import socket
    from urllib.parse import urlparse
    host = urlparse(BASE_URL).hostname
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    print(f"  verify={verify}")
    try:
        # Pre-resolve
        ip = socket.getaddrinfo(host, 443)[0][4][0]
        print(f"  Resolved {host} → {ip}")
        transport = httpx.AsyncHTTPTransport(
            verify=verify,
            local_address=None,
        )
        async with httpx.AsyncClient(
            verify=verify,
            timeout=15,
            transport=transport,
        ) as c:
            # Use IP directly but set Host header
            ip_url = URL.replace(host, ip)
            custom_headers = {**HEADERS, "Host": host}
            r = await c.post(ip_url, json=PAYLOAD, headers=custom_headers)
            print(f"Status: {r.status_code}")
            print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


def test_9_urllib_sync():
    """urllib3 direct (lowest level, OS resolver)."""
    print("\n--- Test 9: urllib3 direct (OS resolver) ---")
    import urllib3
    import json
    verify = CA_BUNDLE if CA_BUNDLE and Path(CA_BUNDLE).exists() else True
    print(f"  verify={verify}")
    try:
        http = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=CA_BUNDLE if CA_BUNDLE else None)
        r = http.request(
            "POST", URL,
            body=json.dumps(PAYLOAD).encode(),
            headers=HEADERS,
            timeout=15,
        )
        print(f"Status: {r.status}")
        print(f"Response: {r.data.decode()[:200]}")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")


async def main():
    print("=" * 60)
    print("TrueFoundry Connectivity Test")
    print(f"Base URL : {BASE_URL}")
    print(f"Model    : {MODEL}")
    print(f"CA Bundle: {CA_BUNDLE} (exists={Path(CA_BUNDLE).exists() if CA_BUNDLE else 'N/A'})")
    print(f"Proxy    : {PROXY or 'not set'}")
    print("=" * 60)

    # DNS check first
    import socket
    from urllib.parse import urlparse
    host = urlparse(BASE_URL).hostname
    print(f"\nDNS lookup for {host}...")
    try:
        ip = socket.getaddrinfo(host, 443)[0][4][0]
        print(f"  Resolved: {ip}")
    except socket.gaierror as e:
        print(f"  DNS FAILED: {e}")
        print("  (This means the host needs proxy or VPN)")

    await test_1_raw_no_verify()
    await test_2_raw_ca_bundle()
    await test_3_raw_ca_proxy()
    await test_4_openai_sdk()
    await test_5_openai_sdk_proxy()
    test_6_requests_sync()
    test_7_openai_sync()
    await test_8_async_transport_mapped()
    test_9_urllib_sync()

    print("\n" + "=" * 60)
    print("Done. Use the test number that works to configure backend_wlg.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
