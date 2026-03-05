#!/usr/bin/env python3
"""
RedTeam Software login script.
Authenticates against id.redteam.com and returns a session.
"""

import requests
import json
import sys

EMAIL = "bnobile@remnantconstruction.com"
PASSWORD = "Boca5656*"
LOGIN_URL = "https://id.redteam.com"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
})

def get_login_page():
    print("[*] Fetching login page...")
    r = session.get(LOGIN_URL)
    print(f"    Status: {r.status_code}")
    print(f"    Final URL: {r.url}")
    return r

def attempt_login():
    print("[*] Attempting login...")

    # Try common Next.js auth API route
    endpoints = [
        "/api/auth/signin",
        "/api/auth/callback/credentials",
        "/api/login",
        "/login",
    ]

    payload = {"email": EMAIL, "password": PASSWORD}

    for endpoint in endpoints:
        url = f"{LOGIN_URL}{endpoint}"
        r = session.post(url, json=payload)
        print(f"    POST {endpoint} -> {r.status_code}")
        if r.status_code not in (404, 405):
            print(f"    Response: {r.text[:300]}")
            return r

    return None

def check_cookies():
    print("[*] Session cookies:")
    for c in session.cookies:
        print(f"    {c.name} = {c.value[:40]}...")

if __name__ == "__main__":
    r = get_login_page()
    attempt_login()
    check_cookies()
