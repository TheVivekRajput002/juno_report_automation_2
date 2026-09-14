import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page
from config import DEFAULT_RESTAURANT_NAME, DEFAULT_RESTAURANT_ID
from scrapers.zomato.base import BaseZomatoScraper
from scrapers.zomato.auth import ZomatoAuth
from scrapers.zomato.outlet_selector import OutletSelector
from scrapers.zomato.reporting_scraper import ReportingScraper
from scrapers.zomato.payout_scraper import PayoutScraper


class ZomatoScraper(BaseZomatoScraper):
    """
    Main coordinator facade for Zomato extraction pipeline.
    Composes modular sub-scrapers:
    - ZomatoAuth: Session validation & login checking
    - OutletSelector: Restaurant outlet modals/dialogs selection
    - ReportingScraper: Business reports matrix table extraction
    - PayoutScraper: Finance -> Payouts side-drawer extraction
    """

    def __init__(self, page: Optional[Page] = None):
        super().__init__(page)
        self.auth = ZomatoAuth(page)
        self.outlet_selector = OutletSelector(page)
        self.reporting_scraper = ReportingScraper(page, self.outlet_selector)
        self.payout_scraper = PayoutScraper(page, self.outlet_selector)

        # Synchronize restaurant state references
        self.extracted_restaurant_name: Optional[str] = None
        self.extracted_restaurant_id: Optional[str] = None

    def check_login_status(self) -> bool:
        """Checks if the user session is active on Zomato Partner portal."""
        return self.auth.check_login_status()

    def select_weekly_view(self) -> bool:
        """Ensures the Weekly view / granularity is selected in Business reports."""
        return self.reporting_scraper.select_weekly_view()

    def select_restaurant_outlet(self, restaurant_name_or_id: Optional[str] = None) -> bool:
        """Selects target restaurant outlet across modals and dialogs."""
        res = self.outlet_selector.select_outlet(restaurant_name_or_id)
        if self.outlet_selector.extracted_restaurant_name:
            self.extracted_restaurant_name = self.outlet_selector.extracted_restaurant_name
        if self.outlet_selector.extracted_restaurant_id:
            self.extracted_restaurant_id = self.outlet_selector.extracted_restaurant_id
        return res

    def navigate_and_extract_reporting_tab(
        self,
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
        restaurant_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extracts funnel & operational metrics from Reporting tab."""
        data = self.reporting_scraper.extract_data(start_date, end_date, date_label, restaurant_name, restaurant_id)
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
        """Extracts settlement & financial breakdown from Payouts drawer."""
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
                m_id = re.search(r"(?:Id|Res Id|Restaurant ID)\s*[:#]?\s*(\d{6,10})", page_text, re.I)
                if m_id:
                    info["restaurant_id"] = m_id.group(1)
                    break

            res_elem = self.find_clickable([
                "[class*='restaurant-name']",
                "[class*='outlet-name']",
                "[class*='brand-name']",
                "h1", "h2"
            ], timeout_ms=1000)
            if res_elem:
                info["restaurant_name"] = res_elem.inner_text().strip()
        except Exception:
            pass
        return info

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
        1. Reporting Tab (Business Reports matrix table)
        2. Payout Tab (Finance -> Payout details side drawer)
        """
        reporting_data = self.navigate_and_extract_reporting_tab(
            start_date, end_date, date_label, restaurant_name, restaurant_id
        )
        payout_data = self.navigate_and_extract_payout_tab(
            start_date, end_date, date_label, restaurant_name, restaurant_id
        )
        res_info = self.extract_restaurant_info()

        combined: Dict[str, Any] = {}
        combined.update(reporting_data)
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
