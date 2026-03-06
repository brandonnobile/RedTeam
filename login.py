#!/usr/bin/env python3
"""
RedTeam Software login script.
Authenticates against id.redteam.com via AWS Cognito SRP auth.
"""

from pycognito import Cognito

USER_POOL_ID = "us-east-1_BRaUQRaTR"
CLIENT_ID = "1v7lfl5iq9i0ihdid56llerjf7"
EMAIL = "bnobile@remnantconstruction.com"
PASSWORD = "Boca5656**"


def login():
    u = Cognito(USER_POOL_ID, CLIENT_ID, username=EMAIL)
    u.authenticate(password=PASSWORD)
    print("[+] LOGIN SUCCESS")
    print(f"    id_token:     {u.id_token[:80]}...")
    print(f"    access_token: {u.access_token[:80]}...")
    return u


if __name__ == "__main__":
    login()
