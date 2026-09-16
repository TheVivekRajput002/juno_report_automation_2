import re
from datetime import datetime
from typing import Dict, Any, Optional
from playwright.sync_api import Page
from config import DEFAULT_RESTAURANT_NAME, DEFAULT_SWIGGY_ID
from scrapers.swiggy.base import BaseSwiggyScraper
from scrapers.swiggy.auth import SwiggyAuth
from scrapers.swiggy.outlet_selector import SwiggyOutletSelector
from scrapers.swiggy.performance_scraper import SwiggyPerformanceScraper
from scrapers.swiggy.payout_scraper import SwiggyPayoutScraper
from scrapers.swiggy.network_capture import SwiggyNetworkCapture
from scrapers.swiggy.api_client import SwiggyApiClient
from scrapers.swiggy.api_discovery import SwiggyApiDiscovery
from scrapers.swiggy.session_manager import SwiggySessionManager


class SwiggyScraper(BaseSwiggyScraper):
    """
    Main coordinator facade for Swiggy Partner extraction pipeline.
    Composes modular sub-scrapers:
    - SwiggyAuth: Session validation & login checking on partner.swiggy.com
    - SwiggyOutletSelector: Outlet dropdown & Business Reports filter modal
    - SwiggyPerformanceScraper: Funnel & operational metrics extraction
    - SwiggyPayoutScraper: Finance & weekly payout breakdown extraction
    - SwiggyNetworkCapture: Isolated API discovery (does not affect Zomato)
    - SwiggyApiClient: Optional direct HTTP replay of discovered endpoints
    """

    def __init__(self, page: Optional[Page] = None):
        self.network_capture = SwiggyNetworkCapture(page)
        if page:
            self.network_capture.attach(page)

        super().__init__(page, network_capture=self.network_capture)

        self.api_client = (
            SwiggyApiClient.from_playwright_page(page, self.network_capture)
            if page
            else SwiggyApiClient.from_saved_session()
        )

        self.auth = SwiggyAuth(page)
        self.outlet_selector = SwiggyOutletSelector(page, network_capture=self.network_capture)
        self.performance_scraper = SwiggyPerformanceScraper(
            page, self.outlet_selector, self.network_capture, self.api_client
        )
        self.payout_scraper = SwiggyPayoutScraper(
            page, self.outlet_selector, self.network_capture, self.api_client
        )

        # Synchronize restaurant state references
        self.extracted_restaurant_name: Optional[str] = None
        self.extracted_restaurant_id: Optional[str] = None

    def check_login_status(self) -> bool:
        """Checks if the user session is active on Swiggy Partner portal."""
        return self.auth.check_login_status()

    def select_restaurant_outlet(self, restaurant_name_or_id: Optional[str] = None) -> bool:
        """Selects target restaurant outlet across dropdowns and filter modals."""
        res = self.outlet_selector.select_global_outlet(restaurant_name_or_id)
        if self.outlet_selector.extracted_restaurant_name:
            self.extracted_restaurant_name = self.outlet_selector.extracted_restaurant_name
        if self.outlet_selector.extracted_restaurant_id:
            self.extracted_restaurant_id = self.outlet_selector.extracted_restaurant_id
        return res

    def navigate_and_extract_performance_tab(
        self,
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
        restaurant_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extracts funnel & operational metrics from Business Reports tab."""
        data = self.performance_scraper.extract_data(start_date, end_date, date_label, restaurant_name, restaurant_id)
        if self.outlet_selector.extracted_restaurant_name:
            self.extracted_restaurant_name = self.outlet_selector.extracted_restaurant_name
        if self.outlet_selector.extracted_restaurant_id:
            self.extracted_restaurant_id = self.outlet_selector.extracted_restaurant_id
        return data

    def navigate_and_extract_payout_tab(
        self,
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
        restaurant_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extracts settlement & financial breakdown from Finance tab."""
        data = self.payout_scraper.extract_data(start_date, end_date, date_label, restaurant_name, restaurant_id)
        if self.outlet_selector.extracted_restaurant_name:
            self.extracted_restaurant_name = self.outlet_selector.extracted_restaurant_name
        if self.outlet_selector.extracted_restaurant_id:
            self.extracted_restaurant_id = self.outlet_selector.extracted_restaurant_id
        return data

    def extract_restaurant_info(self) -> Dict[str, str]:
        """Extracts restaurant name and ID if displayed on page."""
        info = {}
        if not self.page:
            return info
        try:
            for f in [self.page.main_frame] + self.page.frames:
                page_text = f.evaluate("() => document.body ? document.body.innerText : ''")
                m_id = re.search(r"\b(?:Outlet\s*ID|Swiggy\s*ID|ID)\s*[:#]?\s*(\d{5,10})", page_text, re.I)
                if m_id:
                    info["restaurant_id"] = m_id.group(1)
                    break

            res_elem = self.find_clickable([
                "[class*='restaurant-name']",
                "[class*='outlet-name']",
                "[class*='brand-name']",
                "[data-testid*='restaurant-name']",
                "h1", "h2"
            ], timeout_ms=1000)
            if res_elem:
                info["restaurant_name"] = res_elem.inner_text().strip()
        except Exception:
            pass
        return info

    def _persist_api_discovery(self, label: Optional[str] = None) -> None:
        """Saves captured API traffic and session cookies after a scrape run."""
        if not self.network_capture.entries:
            return
        summary = self.network_capture.summarize()
        cookies = SwiggySessionManager.extract_cookies_from_page(self.page) if self.page else []
        SwiggyApiDiscovery.persist_capture(
            entries=self.network_capture.entries,
            summary=summary,
            session_cookies=cookies,
            label=label,
        )
        if self.page:
            SwiggySessionManager.save_from_page(self.page, capture_entries=self.network_capture.entries)
            if self.network_capture.access_token:
                self.api_client.graphql.set_access_token(self.network_capture.access_token)
        self.network_capture.print_summary()

    def scrape_all(
        self,
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
        restaurant_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes complete sequential extraction from:
        1. Business Reports Tab (Funnel & Operational metrics)
        2. Finance Tab (Weekly payout card & settlement side drawer)

        After extraction, persists discovered API endpoints and session cookies
        to .user_data/swiggy_api_discovery/ for future direct HTTP replay.
        """
        target_id = restaurant_id or DEFAULT_SWIGGY_ID

        try:
            perf_data = self.navigate_and_extract_performance_tab(
                start_date, end_date, date_label, restaurant_name, target_id
            )
            payout_data = self.navigate_and_extract_payout_tab(
                start_date, end_date, date_label, restaurant_name, target_id
            )
            res_info = self.extract_restaurant_info()

            combined: Dict[str, Any] = {}
            combined.update(perf_data)
            combined.update(payout_data)
            combined.update(res_info)

            if self.extracted_restaurant_name:
                combined["restaurant_name"] = self.extracted_restaurant_name
            elif restaurant_name:
                combined["restaurant_name"] = restaurant_name

            if self.extracted_restaurant_id:
                combined["restaurant_id"] = self.extracted_restaurant_id
            elif restaurant_id:
                combined["restaurant_id"] = restaurant_id

            return combined
        finally:
            self._persist_api_discovery(label=date_label or "scrape")
            if self.page and self.api_client:
                self.api_client.sync_auth(self.page, self.network_capture)
