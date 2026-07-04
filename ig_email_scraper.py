"""
Fetch public business/creator emails from your Instagram followers and save to JSON.

Only picks up the `public_email` field Instagram exposes for business/creator
accounts that have chosen to display a contact email on their profile. Regular
personal accounts have no such field and are skipped.

Usage:
    python ig_email_scraper.py [--limit N] [--output followers_emails.json]
"""

import argparse
import json
import os
import random
import sys
import time
from getpass import getpass

from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ChallengeRequired,
    ClientError,
    LoginRequired,
    PleaseWaitFewMinutes,
    TwoFactorRequired,
)

SESSION_FILE = "ig_session.json"
DELAY_RANGE_SECONDS = (3, 7)


def describe_login_failure(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()

    if isinstance(exc, ChallengeRequired):
        return (
            "Instagram required a challenge step. Complete the manual verification in the browser "
            "or with the provided Instagram flow, then retry with the same device/session settings."
        )

    if isinstance(exc, TwoFactorRequired):
        return (
            "Instagram requested two-factor authentication. Provide the verification code or "
            "configure a 2FA handler before retrying."
        )

    if isinstance(exc, BadPassword) or "blacklist" in lowered or "bad password" in lowered:
        return (
            "Instagram rejected the password or temporarily blocked the IP address. Verify the "
            "credentials and retry from a different network or proxy if Instagram asks for further verification."
        )

    if "challenge" in lowered or "checkpoint" in lowered:
        return (
            "Instagram blocked the login with a challenge or checkpoint. Complete the manual "
            "verification flow, then retry."
        )

    return f"Instagram login failed: {message}"


def configure_client_proxy(cl: Client) -> None:
    proxy = os.getenv("IG_PROXY") or os.getenv("HTTPS_PROXY")
    if not proxy:
        return

    try:
        cl.set_proxy(proxy)
    except Exception as exc:
        print(f"Warning: could not apply proxy {proxy}: {exc}", file=sys.stderr)


def login(username: str, password: str) -> Client:
    cl = Client()
    configure_client_proxy(cl)

    if os.path.exists(SESSION_FILE):
        cl.load_settings(SESSION_FILE)
        try:
            cl.login(username, password, relogin=True)
            cl.get_timeline_feed()  # cheap call to confirm the session is still valid
            cl.dump_settings(SESSION_FILE)
            return cl
        except Exception as exc:
            print(f"Saved session was invalid or expired: {describe_login_failure(exc)}", file=sys.stderr)
            cl = Client()
            configure_client_proxy(cl)

    try:
        if not cl.login(username, password):
            raise RuntimeError("Instagram did not accept the login attempt.")
        cl.dump_settings(SESSION_FILE)
        return cl
    except Exception as exc:
        if os.path.exists(SESSION_FILE):
            try:
                os.remove(SESSION_FILE)
            except OSError:
                pass
        raise RuntimeError(describe_login_failure(exc)) from exc


def fetch_follower_emails(cl: Client, limit: int | None) -> list[dict]:
    my_user_id = cl.user_id
    followers = cl.user_followers(my_user_id, amount=limit or 0)

    results = []
    follower_items = list(followers.items())
    total = len(follower_items)

    for i, (pk, short_user) in enumerate(follower_items, start=1):
        print(f"[{i}/{total}] checking @{short_user.username}...", file=sys.stderr)
        try:
            info = cl.user_info(pk)
        except PleaseWaitFewMinutes:
            print("Rate limited by Instagram, stopping early.", file=sys.stderr)
            break
        except (ClientError, LoginRequired) as e:
            print(f"  skipped @{short_user.username}: {e}", file=sys.stderr)
            time.sleep(random.uniform(*DELAY_RANGE_SECONDS))
            continue

        if info.public_email:
            results.append(
                {
                    "pk": str(pk),
                    "username": info.username,
                    "full_name": info.full_name,
                    "public_email": info.public_email,
                    "is_business": info.is_business,
                }
            )
            print(f"  -> found email: {info.public_email}", file=sys.stderr)

        time.sleep(random.uniform(*DELAY_RANGE_SECONDS))

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=50, help="Max number of followers to check (default: 50)"
    )
    parser.add_argument(
        "--output", default="followers_emails.json", help="Output JSON file path"
    )
    args = parser.parse_args()

    load_dotenv()
    username = os.getenv("IG_USERNAME") or input("IG username: ")
    password = os.getenv("IG_PASSWORD") or getpass("IG password: ")

    try:
        cl = login(username, password)
    except RuntimeError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        sys.exit(1)

    results = fetch_follower_emails(cl, args.limit)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(results)} public email(s) to {args.output}")


if __name__ == "__main__":
    main()
