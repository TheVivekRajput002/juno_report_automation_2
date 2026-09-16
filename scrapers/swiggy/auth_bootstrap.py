"""Shared auth bootstrap for Swiggy GraphQL — loads portal once to capture access_token."""

from typing import Optional

from playwright.sync_api import Page

from config import SWIGGY_REPORTS_URL
from scrapers.swiggy.api_client import SwiggyApiClient
from scrapers.swiggy.network_capture import SwiggyNetworkCapture


def bootstrap_swiggy_api_auth(
    page: Optional[Page],
    api_client: Optional[SwiggyApiClient],
    network_capture: Optional[SwiggyNetworkCapture],
) -> bool:
    """
    Ensures access_token is available for GraphQL calls.
    Navigates to Business Reports once if needed — no outlet UI interaction required.
    """
    if not api_client or not page:
        return False

    api_client.sync_auth(page, network_capture)
    if api_client.has_session():
        return True

    try:
        current = page.url.lower()
        if "partner.swiggy.com" not in current or "login" in current:
            print("[*] Loading Swiggy Partner portal to capture access_token...")
            page.goto(SWIGGY_REPORTS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
        else:
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

        api_client.sync_auth(page, network_capture)
        if network_capture and network_capture.access_token:
            api_client.graphql.set_access_token(network_capture.access_token)

        if api_client.has_session():
            print("[✓] Swiggy access_token captured for GraphQL API.")
            return True

        print("[!] Could not capture Swiggy access_token — will fall back to DOM scraping.")
    except Exception as e:
        print(f"[!] Swiggy auth bootstrap error: {e}")

    return api_client.has_session()
