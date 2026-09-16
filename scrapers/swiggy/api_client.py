"""
Swiggy API facade — delegates to SwiggyGraphQLClient for direct data fetching.
Swiggy-only module; Zomato is unaffected.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from scrapers.swiggy.graphql_client import SwiggyGraphQLClient
from scrapers.swiggy.network_capture import SwiggyNetworkCapture
from scrapers.swiggy.session_manager import SwiggySessionManager


class SwiggyApiClient:
    """
    High-level Swiggy data client. Uses GraphQL with access_token auth.
    Playwright is only needed once to capture the token — not for data extraction.
    """

    def __init__(self, access_token: Optional[str] = None):
        self.graphql = SwiggyGraphQLClient(access_token=access_token)

    @classmethod
    def from_playwright_page(cls, page: Page, capture: Optional[SwiggyNetworkCapture] = None) -> "SwiggyApiClient":
        token = (
            SwiggySessionManager.extract_access_token_from_page(page)
            or SwiggySessionManager.extract_access_token_from_capture_entries(capture.entries if capture else [])
            or SwiggySessionManager.load_access_token()
        )
        return cls(access_token=token)

    @classmethod
    def from_saved_session(cls) -> "SwiggyApiClient":
        return cls(access_token=SwiggySessionManager.load_access_token())

    def sync_auth(self, page: Optional[Page] = None, capture: Optional[SwiggyNetworkCapture] = None) -> None:
        token = self.graphql.access_token
        if page:
            token = SwiggySessionManager.extract_access_token_from_page(page) or token
        if capture:
            token = SwiggySessionManager.extract_access_token_from_capture_entries(capture.entries) or token
        if token:
            self.graphql.set_access_token(token)

    def has_session(self) -> bool:
        return self.graphql.has_session()

    def close(self) -> None:
        self.graphql.close()

    def validate_outlet_access(self, outlet_id: str, seed_outlet_id: Optional[str] = None) -> bool:
        if not self.has_session():
            return False
        try:
            seed = seed_outlet_id or outlet_id
            accessible = self.graphql.list_accessible_outlet_ids(seed)
            if not accessible:
                return True  # Cannot verify — proceed anyway
            if int(outlet_id) not in accessible:
                print(f"[!] Swiggy outlet {outlet_id} is NOT in this account's accessible outlets ({len(accessible)} total).")
                print("[!] Check outlets.json swiggy_id or log into the correct Swiggy Partner account.")
                return False
            return True
        except Exception as e:
            print(f"[!] Swiggy outlet validation skipped due to error: {e}")
            return True

    def fetch_performance(
        self,
        outlet_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        if not self.has_session():
            return None
        return self.graphql.fetch_business_metrics(outlet_id, start_date, end_date)

    def fetch_payout(
        self,
        outlet_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[Dict[str, Any]]:
        if not self.has_session():
            return None
        return self.graphql.fetch_payout_for_date_range(outlet_id, start_date, end_date)

    def list_outlet_ids(self, seed_outlet_id: str) -> List[int]:
        return self.graphql.list_accessible_outlet_ids(seed_outlet_id)
