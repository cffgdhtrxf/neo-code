"""
Tavily API connectivity test
Ref: https://docs.tavily.com
"""

import os
import requests
import time
import socket

API_KEY = os.environ.get("TAVILY_API_KEY", "")
if not API_KEY:
    raise SystemExit(
        "TAVILY_API_KEY 未设置。请先 export TAVILY_API_KEY=\"tvly-...\" 后运行本脚本。"
    )
TAVILY_URL = "https://api.tavily.com/search"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}
PAYLOAD = {
    "query": "What is the weather today",
    "max_results": 3,
    "search_depth": "basic",
    "include_answer": True,
}


def test_dns_resolution():
    """Step 1: DNS resolution"""
    print("=" * 60)
    print("[1] DNS resolving api.tavily.com ...")
    try:
        ip = socket.getaddrinfo("api.tavily.com", 443)
        ips = set(addr[4][0] for addr in ip)
        print(f"    [OK] Resolved: {ips}")
        return True
    except socket.gaierror as e:
        print(f"    [FAIL] DNS failed: {e}")
        return False


def test_tcp_connect():
    """Step 2: TCP connect"""
    print("=" * 60)
    print("[2] TCP connecting api.tavily.com:443 ...")
    try:
        sock = socket.create_connection(("api.tavily.com", 443), timeout=10)
        sock.close()
        print("    [OK] TCP connected")
        return True
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"    [FAIL] TCP failed: {e}")
        return False


def test_https_direct():
    """Step 3: HTTPS direct request"""
    print("=" * 60)
    print("[3] HTTPS direct request to Tavily Search API ...")
    print(f"    URL: {TAVILY_URL}")
    start = time.time()
    try:
        resp = requests.post(
            TAVILY_URL,
            headers=HEADERS,
            json=PAYLOAD,
            timeout=15,
        )
        elapsed = time.time() - start
        print(f"    [OK] Elapsed: {elapsed:.2f}s")
        print(f"    HTTP Status: {resp.status_code}")
        print(f"    Response (first 500 chars):")
        print(f"    {resp.text[:500]}")
        return True
    except requests.exceptions.ReadTimeout:
        elapsed = time.time() - start
        print(f"    [FAIL] Read timeout ({elapsed:.2f}s) -- likely blocked or network too slow")
        return False
    except requests.exceptions.ConnectTimeout:
        elapsed = time.time() - start
        print(f"    [FAIL] Connect timeout ({elapsed:.2f}s) -- most likely blocked by firewall")
        return False
    except requests.exceptions.ConnectionError as e:
        elapsed = time.time() - start
        print(f"    [FAIL] Connection error ({elapsed:.2f}s): {e}")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"    [FAIL] Unknown error ({elapsed:.2f}s): {type(e).__name__}: {e}")
        return False


def test_with_proxy(proxy_url):
    """Step 4: Request via proxy"""
    print("=" * 60)
    print(f"[4] Proxy test: {proxy_url}")
    proxies = {"http": proxy_url, "https": proxy_url}
    start = time.time()
    try:
        resp = requests.post(
            TAVILY_URL,
            headers=HEADERS,
            json=PAYLOAD,
            timeout=15,
            proxies=proxies,
        )
        elapsed = time.time() - start
        print(f"    [OK] Elapsed: {elapsed:.2f}s")
        print(f"    HTTP Status: {resp.status_code}")
        data = resp.json()
        answer = data.get("answer", "N/A")
        results_count = len(data.get("results", []))
        print(f"    Answer: {answer[:200]}")
        print(f"    Results count: {results_count}")
        return True
    except requests.exceptions.ReadTimeout:
        elapsed = time.time() - start
        print(f"    [FAIL] Read timeout ({elapsed:.2f}s)")
        return False
    except requests.exceptions.ConnectTimeout:
        elapsed = time.time() - start
        print(f"    [FAIL] Connect timeout ({elapsed:.2f}s) -- proxy dead")
        return False
    except requests.exceptions.ProxyError as e:
        elapsed = time.time() - start
        print(f"    [FAIL] Proxy error ({elapsed:.2f}s): {e}")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"    [FAIL] Error ({elapsed:.2f}s): {type(e).__name__}: {e}")
        return False


def main():
    print("Tavily API Connectivity Test")
    print(f"API Key: {API_KEY[:30]}...{API_KEY[-10:]}")
    print()

    dns_ok = test_dns_resolution()
    tcp_ok = test_tcp_connect() if dns_ok else False
    direct_ok = test_https_direct() if tcp_ok else False

    if not direct_ok:
        print("\n[!] Direct connection failed, trying common proxy ports...")
        common_proxies = [
            "http://127.0.0.1:7890",   # Clash
            "http://127.0.0.1:7891",   # Clash (alt)
            "http://127.0.0.1:10809",  # V2Ray / v2rayN
            "http://127.0.0.1:1080",   # SOCKS5 HTTP proxy
            "http://127.0.0.1:8080",   # Common HTTP proxy
            "http://127.0.0.1:8118",   # Privoxy
        ]
        found = False
        for proxy in common_proxies:
            if test_with_proxy(proxy):
                found = True
                print(f"\n[OK] Working proxy found: {proxy}")
                print(f"    Set in CONFIG: \"PROXY\": \"{proxy}\"")
                break
        if not found:
            print("\n[FAIL] No working proxy found on common ports")
            print("    Please set PROXY config manually with your proxy address")

    print("\n" + "=" * 60)
    print("Diagnosis complete")


if __name__ == "__main__":
    main()
