import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page
from config import SWIGGY_REPORTS_URL, SWIGGY_DASHBOARD_URL
from scrapers.swiggy.base import BaseSwiggyScraper
from scrapers.swiggy.outlet_selector import SwiggyOutletSelector
from scrapers.swiggy.performance_parser import SwiggyPerformanceParser
from scrapers.swiggy.network_capture import SwiggyNetworkCapture
from scrapers.swiggy.api_client import SwiggyApiClient
from scrapers.swiggy.auth_bootstrap import bootstrap_swiggy_api_auth


class SwiggyPerformanceScraper(BaseSwiggyScraper):
    """
    Automates extraction from Swiggy Partner Portal -> Business Reports / Performance tab.
    Extracts Funnel (Impressions, Menu Opens, I2M, M2O, C2O), Operations (Visibility, KPT),
    and Restaurant Cancelled Orders (Mx Rejections).
    """

    def __init__(
        self,
        page: Optional[Page] = None,
        outlet_selector: Optional[SwiggyOutletSelector] = None,
        network_capture: Optional[SwiggyNetworkCapture] = None,
        api_client: Optional[SwiggyApiClient] = None,
    ):
        super().__init__(page, network_capture=network_capture)
        self.outlet_selector = outlet_selector or SwiggyOutletSelector(page, network_capture=self.network_capture)
        self.api_client = api_client
        self.parser = SwiggyPerformanceParser()

    def set_date_range(self, start_date: datetime, end_date: datetime, date_label: Optional[str] = None):
        """
        Applies custom date range filter on Swiggy Business Reports page.
        """
        if not self.page:
            return
        print(f"[*] Setting Business Reports date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")

        try:
            # Look for date picker / date range button
            date_btn_selectors = [
                "[data-testid*='date-picker']",
                "[data-testid*='date-filter']",
                "[data-testid*='date-range']",
                "[data-testid*='date']",
                "//button[contains(@class, 'date') or contains(@class, 'calendar') or contains(@class, 'period')]",
                "//div[@role='button'][contains(., 'Date') or contains(., 'Last 7') or contains(., 'Last week') or contains(., 'Custom') or contains(., 'days')]",
                "//button[contains(., 'Date') or contains(., 'Last 7') or contains(., 'Last week') or contains(., 'Custom') or contains(., 'days')]",
                "//div[contains(@class, 'date-picker') or contains(@class, 'datePicker')]",
                "//*[contains(text(), 'Date Range') or contains(text(), 'Custom Range')]",
            ]
            date_btn = self.find_clickable(date_btn_selectors, timeout_ms=2000)
            if not date_btn:
                # JS fallback to find date button
                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        clicked = f.evaluate("""() => {
                            const btns = Array.from(document.querySelectorAll('button, div[role="button"], div[class*="date"]'));
                            for (const b of btns) {
                                const txt = (b.innerText || '').toLowerCase();
                                if (txt.includes('last 7') || txt.includes('last 30') || txt.includes('custom') || 
                                    txt.includes('last week') || /\\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\\b/i.test(txt)) {
                                    b.click();
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        if clicked:
                            print("[+] Clicked date range selector via JS evaluation.")
                            self.page.wait_for_timeout(1000)
                            break
                    except Exception:
                        pass
            else:
                date_btn.click()
                print("[+] Opened date range picker.")
                self.page.wait_for_timeout(1000)

            # Look for custom range option
            custom_opt = self.find_clickable([
                "//li[contains(., 'Custom')]",
                "//div[contains(., 'Custom Range')]",
                "//button[contains(., 'Custom')]",
                "//span[contains(., 'Custom')]",
                "//*[text()='Custom' or text()='Custom Range' or text()='Custom Date']",
            ], timeout_ms=1500)
            if custom_opt:
                custom_opt.click()
                print("[+] Selected 'Custom Range' in date picker.")
                self.page.wait_for_timeout(800)
            else:
                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        f.evaluate("""() => {
                            const items = Array.from(document.querySelectorAll('li, button, div, span'));
                            for (const it of items) {
                                const txt = (it.innerText || '').trim().toLowerCase();
                                if (txt === 'custom' || txt === 'custom range' || txt === 'custom date') {
                                    it.click();
                                    return true;
                                }
                            }
                            return false;
                        }""")
                    except Exception:
                        pass

            # Look for start and end inputs
            inputs = self.page.locator("input[type='date'], input[placeholder*='YYYY'], input[placeholder*='DD/MM'], input[placeholder*='DD-MM'], input[placeholder*='Start'], input[type='text']").all()
            date_inputs = [inp for inp in inputs if inp.is_visible()]
            if len(date_inputs) >= 2:
                for inp, dt in zip(date_inputs[:2], [start_date, end_date]):
                    try:
                        ph = inp.get_attribute("placeholder") or ""
                        inp.click()
                        inp.fill("")
                        if "dd/mm" in ph.lower() or "dd-mm" in ph.lower() or "/" in ph:
                            inp.fill(dt.strftime("%d/%m/%Y"))
                        else:
                            inp.fill(dt.strftime("%Y-%m-%d"))
                        self.page.wait_for_timeout(300)
                    except Exception:
                        pass

            # JS fill for date inputs
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    f.evaluate("""({ sDateYmd, eDateYmd, sDateDmy, eDateDmy }) => {
                        const inps = Array.from(document.querySelectorAll('input[type="date"], input[placeholder*="YYYY"], input[placeholder*="DD"], input[placeholder*="Start"], input[type="text"]'));
                        const visible = inps.filter(i => i.offsetParent !== null);
                        if (visible.length >= 2) {
                            visible[0].value = visible[0].placeholder && visible[0].placeholder.includes('DD') ? sDateDmy : sDateYmd;
                            visible[0].dispatchEvent(new Event('input', { bubbles: true }));
                            visible[0].dispatchEvent(new Event('change', { bubbles: true }));
                            
                            visible[1].value = visible[1].placeholder && visible[1].placeholder.includes('DD') ? eDateDmy : eDateYmd;
                            visible[1].dispatchEvent(new Event('input', { bubbles: true }));
                            visible[1].dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""", {
                        "sDateYmd": start_date.strftime("%Y-%m-%d"),
                        "eDateYmd": end_date.strftime("%Y-%m-%d"),
                        "sDateDmy": start_date.strftime("%d/%m/%Y"),
                        "eDateDmy": end_date.strftime("%d/%m/%Y"),
                    })
                except Exception:
                    pass

            apply_btn = self.find_clickable([
                "//button[normalize-space()='Apply' or contains(., 'Apply')]",
                "//button[normalize-space()='Done' or contains(., 'Done')]",
                "//div[contains(@class, 'calendar')]//button[contains(., 'Apply')]",
            ], timeout_ms=1500)
            if apply_btn:
                apply_btn.click()
                print(f"[+] Applied date range: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}")
                self.page.wait_for_timeout(2500)
            else:
                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        f.evaluate("""() => {
                            const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                            for (const b of btns) {
                                const txt = (b.innerText || '').trim().toLowerCase();
                                if (txt === 'apply' || txt === 'done' || txt === 'show data') {
                                    b.click();
                                    return true;
                                }
                            }
                            return false;
                        }""")
                    except Exception:
                        pass
                self.page.wait_for_timeout(2000)

        except Exception as e:
            print(f"[!] Notice setting Swiggy date range: {e}")

    def extract_data(
        self,
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
        restaurant_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Navigates to Swiggy Business Reports, configures outlet filter modal ('Filter by outlets'),
        sets date range, and extracts funnel + operational performance metrics.
        """
        data: Dict[str, Any] = {}
        if not self.page:
            return data

        print("\n" + "-" * 50)
        print("[1] Navigating to SWIGGY Business Reports (Performance Metrics)...")
        print("-" * 50)

        try:
            target_id = restaurant_id or restaurant_name

            # GraphQL API-first (no outlet dropdown / filter modal needed)
            bootstrap_swiggy_api_auth(self.page, self.api_client, self.network_capture)
            if self.api_client and target_id and self.api_client.has_session():
                print(f"[*] Fetching Swiggy performance via GraphQL for outlet {target_id}...")
                self.api_client.validate_outlet_access(str(target_id))
                api_json = self.api_client.fetch_performance(str(target_id), start_date, end_date)
                if api_json:
                    api_parsed = self.parser.parse_graphql_business_metrics(api_json)
                    if self.parser._has_core_performance_fields(api_parsed):
                        print("[✓] Swiggy performance metrics fetched via GraphQL API.")
                        return api_parsed
                    print("[*] GraphQL returned no core performance fields — falling back to DOM.")

            self.close_all_drawers_and_modals()

            current_url = self.page.url.lower()
            if "business-metrics" not in current_url and "reports" not in current_url:
                print(f"[*] Navigating directly to Reports URL: {SWIGGY_REPORTS_URL}")
                self.page.goto(SWIGGY_REPORTS_URL, wait_until="domcontentloaded", timeout=30000)
                self.page.wait_for_timeout(3000)

            # Step A: Ensure global outlet or modal outlet is selected
            self.outlet_selector.select_global_outlet(restaurant_name_or_id=target_id, restaurant_name=restaurant_name)
            self.page.wait_for_timeout(1500)

            # Step B: Filter Modal -> "Filter by outlets" (not Brands) -> Select outlet ID
            self.outlet_selector.select_outlet_in_filter_modal(restaurant_name_or_id=target_id, restaurant_name=restaurant_name)
            self.page.wait_for_timeout(2000)

            # Step C: Set Date Range
            self.set_date_range(start_date, end_date, date_label)
            self.page.wait_for_timeout(2500)

            # Step D: Extract DOM body text across frames
            combined_body_text = ""
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    txt = f.evaluate("() => document.body ? document.body.innerText : ''")
                    if len(txt) > len(combined_body_text):
                        combined_body_text = txt
                except Exception:
                    pass

            # Step E: Parse metrics — prefer intercepted JSON, fall back to DOM text
            latest_json = self.network_capture.get_best_response_json("performance")
            parsed = self.parser.parse_performance_text(combined_body_text, raw_json=latest_json)
            data.update(parsed)

            print("[✓] Extracted from Swiggy Business Reports:", {k: v for k, v in data.items() if v is not None})

        except Exception as e:
            print(f"[!] Error in Swiggy Business Reports extraction: {e}")

        return data
