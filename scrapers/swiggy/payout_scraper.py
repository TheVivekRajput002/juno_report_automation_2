import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from playwright.sync_api import Page, Locator
from config import SWIGGY_FINANCE_URL
from scrapers.swiggy.base import BaseSwiggyScraper
from scrapers.swiggy.outlet_selector import SwiggyOutletSelector
from scrapers.swiggy.payout_parser import SwiggyPayoutParser
from scrapers.swiggy.network_capture import SwiggyNetworkCapture
from scrapers.swiggy.api_client import SwiggyApiClient
from scrapers.swiggy.auth_bootstrap import bootstrap_swiggy_api_auth


class SwiggyPayoutScraper(BaseSwiggyScraper):
    """
    Automates data extraction from Swiggy Partner Portal -> Finance -> Past Payouts tab.
    Extracts financial settlement breakdown from the weekly payout card and 'See details ->' side drawer.
    Implements dynamic date overlap matching for irregular payout cycles.
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
        self.parser = SwiggyPayoutParser()

    @staticmethod
    def parse_card_date_range(text: str, current_year: int = datetime.now().year) -> Optional[Tuple[datetime, datetime]]:
        """
        Parses start and end dates from card labels like:
        - '23rd Aug - 31st Aug'
        - '16 Aug - 22 Aug 2026'
        - '23 Aug 2026 to 31 Aug 2026'
        - 'Aug 23 - Aug 31'
        """
        if not text:
            return None

        # Clean ordinals (1st, 2nd, 3rd, 4th -> 1, 2, 3, 4)
        clean = re.sub(r"(\d+)(?:st|nd|rd|th)", r"\1", text)

        # Regex for 'DD Mon - DD Mon' or 'DD Mon YYYY - DD Mon YYYY'
        months = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
        pattern1 = rf"(\d{{1,2}})\s*({months})[\w]*\s*(?:\d{{4}})?\s*(?:-|to|–|—)\s*(\d{{1,2}})\s*({months})[\w]*\s*(\d{{4}})?"
        m1 = re.search(pattern1, clean, re.I)
        if m1:
            s_day, s_mon, e_day, e_mon, yr = m1.groups()
            year = int(yr) if yr else current_year
            try:
                s_dt = datetime.strptime(f"{s_day} {s_mon[:3]} {year}", "%d %b %Y")
                e_dt = datetime.strptime(f"{e_day} {e_mon[:3]} {year}", "%d %b %Y")
                return s_dt, e_dt
            except Exception:
                pass

        # Pattern for 'DD - DD Mon' (same month)
        pattern2 = rf"(\d{{1,2}})\s*(?:-|to|–|—)\s*(\d{{1,2}})\s*({months})[\w]*\s*(\d{{4}})?"
        m2 = re.search(pattern2, clean, re.I)
        if m2:
            s_day, e_day, mon, yr = m2.groups()
            year = int(yr) if yr else current_year
            try:
                s_dt = datetime.strptime(f"{s_day} {mon[:3]} {year}", "%d %b %Y")
                e_dt = datetime.strptime(f"{e_day} {mon[:3]} {year}", "%d %b %Y")
                return s_dt, e_dt
            except Exception:
                pass

        return None

    @classmethod
    def find_best_matching_cycle(
        cls,
        cards: List[Dict[str, Any]],
        target_start: datetime,
        target_end: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Dynamically evaluates and selects the payout card with the maximum overlap / closest matching date range.
        """
        if not cards:
            return None

        best_card = None
        best_score = -999999.0

        for card in cards:
            card_start = card.get("start")
            card_end = card.get("end")

            if not card_start or not card_end:
                # Try parsing from card text
                parsed = cls.parse_card_date_range(card.get("text", ""))
                if parsed:
                    card_start, card_end = parsed

            if card_start and card_end:
                # Overlap in days
                overlap_start = max(target_start, card_start)
                overlap_end = min(target_end, card_end)
                overlap_days = max(0, (overlap_end - overlap_start).days + 1)

                if overlap_days > 0:
                    # Score based on overlap days with minor penalty for duration discrepancy
                    target_len = (target_end - target_start).days + 1
                    card_len = (card_end - card_start).days + 1
                    len_diff = abs(target_len - card_len)
                    score = float(overlap_days * 10) - float(len_diff)
                else:
                    # Distance penalty
                    dist = abs((target_start - card_start).days)
                    score = -float(dist)
            else:
                score = -1000.0

            if score > best_score:
                best_score = score
                best_card = card

        return best_card

    def select_payout_card_and_open_details(
        self, start_date: datetime, end_date: datetime, date_label: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Locates the best matching payout card on Finance page using maximum overlap rule,
        and clicks 'See details ->' to open the breakdown drawer.
        """
        result = {"card_header": "", "drawer_text": ""}
        if not self.page:
            return result

        print(f"[*] Scanning past payout cards for target week: {start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}...")

        # Find all payout card elements across frames
        card_elements_data = []
        for f in [self.page.main_frame] + self.page.frames:
            try:
                cards = f.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('[data-testid*="payout-card"], [class*="payout-card"], [class*="payoutCard"], div[class*="settlement-card"], div[class*="card"]'));
                    return elements.map((el, idx) => ({
                        index: idx,
                        text: el.innerText || '',
                        hasDetailsBtn: Boolean(el.innerText && (el.innerText.includes('See details') || el.innerText.includes('Details') || el.innerText.includes('View details')))
                    })).filter(c => c.text.length > 20 && (c.text.includes('₹') || c.text.includes('Payout') || c.text.includes('Orders') || c.hasDetailsBtn));
                }""")
                if cards:
                    for c in cards:
                        c["frame"] = f
                        card_elements_data.append(c)
            except Exception:
                pass

        # Parse date ranges for each discovered card
        evaluated_cards = []
        for c in card_elements_data:
            txt = c.get("text", "")
            parsed = self.parse_card_date_range(txt)
            if parsed:
                s_dt, e_dt = parsed
                evaluated_cards.append({
                    "card": c,
                    "text": txt,
                    "start": s_dt,
                    "end": e_dt,
                    "label": f"{s_dt.strftime('%d %b')} - {e_dt.strftime('%d %b')}"
                })

        best_match = self.find_best_matching_cycle(evaluated_cards, start_date, end_date)
        if best_match:
            print(f"[+] Found best matching Swiggy payout card: '{best_match['label']}' (Score matched to target {date_label or ''})")
            card_obj = best_match["card"]
            result["card_header"] = best_match["text"]

            # Click 'See details ->' on the matched card
            card_idx = card_obj.get("index", 0)
            target_frame = card_obj.get("frame", self.page.main_frame)
            try:
                target_frame.evaluate("""(idx) => {
                    const cards = Array.from(document.querySelectorAll('[data-testid*="payout-card"], [class*="payout-card"], [class*="payoutCard"], div[class*="settlement-card"], div[class*="card"]'));
                    if (cards[idx]) {
                        const card = cards[idx];
                        const allElems = Array.from(card.querySelectorAll('button, a, [role="button"], span, div, [class*="details"]'));
                        const detailBtn = allElems.find(el => {
                            const t = (el.innerText || '').toLowerCase();
                            return t.includes('detail') || t.includes('view') || t.includes('see');
                        }) || card;
                        detailBtn.click();
                        return true;
                    }
                    return false;
                }""", card_idx)
                print("[+] Clicked 'See details ->' on matched payout card.")
                self.page.wait_for_timeout(2500)
            except Exception as e:
                print(f"[!] Warning clicking 'See details': {e}")
        else:
            # Fallback: Look for any 'See details' or payout card
            print("[*] Using fallback selector for 'See details ->'...")
            details_btn = self.find_clickable([
                "//button[contains(., 'See details') or contains(., 'View details')]",
                "//a[contains(., 'See details') or contains(., 'View details')]",
                "//span[contains(text(), 'See details')]/..",
                "//*[contains(text(), 'See details')]",
            ], timeout_ms=2000)
            if details_btn:
                details_btn.click()
                print("[+] Clicked 'See details' via Playwright locator.")
                self.page.wait_for_timeout(2500)

        return result

    def expand_drawer_accordions(self):
        """Expands collapsible accordions inside Swiggy Payout side drawer."""
        if not self.page:
            return
        print("[*] Expanding accordions in Swiggy Payout details side drawer...")
        try:
            accordions = [
                "//*[contains(text(), 'Total Customer Paid')]/..",
                "//*[contains(text(), 'Total Fees')]/..",
                "//*[contains(text(), 'Total Taxes')]/..",
                "//*[contains(text(), 'Growth Investments')]/..",
                "//button[contains(@aria-expanded, 'false')]",
                "//*[contains(@class, 'chevron') or contains(@class, 'arrow') or contains(@class, 'accordion')]",
            ]
            for sel in accordions:
                try:
                    elems = self.page.locator(sel)
                    for i in range(min(elems.count(), 3)):
                        elems.nth(i).click(timeout=600)
                        self.page.wait_for_timeout(150)
                except Exception:
                    pass

            for f in self.page.frames:
                try:
                    f.evaluate("""() => {
                        const drawer = document.querySelector('[class*="drawer"], [class*="modal"], [class*="sheet"], [class*="sidebar"], [class*="details"]') || document.body;
                        const clickables = Array.from(drawer.querySelectorAll('button[aria-expanded="false"], [role="button"], svg, [class*="chevron"], [class*="arrow"]'));
                        for (const el of clickables) {
                            try { el.click(); } catch(e) {}
                        }
                    }""")
                except Exception:
                    pass
            self.page.wait_for_timeout(1000)
        except Exception:
            pass

    def extract_data(
        self,
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
        restaurant_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Navigates to Finance -> Past Payouts, selects target outlet,
        evaluates irregular payout cycle cards using maximum overlap, clicks 'See details ->',
        expands drawer, and parses settlement fields.
        """
        data: Dict[str, Any] = {}
        if not self.page:
            return data

        print("\n" + "-" * 50)
        print("[2] Navigating to SWIGGY Finance (Payout Details)...")
        print("-" * 50)

        try:
            target_id = restaurant_id or restaurant_name

            # GraphQL API-first (no payout card / drawer UI needed)
            bootstrap_swiggy_api_auth(self.page, self.api_client, self.network_capture)
            if self.api_client and target_id and self.api_client.has_session():
                print(f"[*] Fetching Swiggy payout via GraphQL for outlet {target_id}...")
                self.api_client.validate_outlet_access(str(target_id))
                api_json = self.api_client.fetch_payout(str(target_id), start_date, end_date)
                if api_json:
                    api_parsed = self.parser.parse_graphql_payout_details(api_json)
                    if self.parser._has_core_payout_fields(api_parsed):
                        print("[✓] Swiggy payout metrics fetched via GraphQL API.")
                        return api_parsed
                    print("[*] GraphQL returned incomplete payout data — falling back to DOM.")

            self.close_all_drawers_and_modals()

            current_url = self.page.url.lower()
            if "finance" not in current_url and "payout" not in current_url:
                print(f"[*] Navigating directly to Finance URL: {SWIGGY_FINANCE_URL}")
                self.page.goto(SWIGGY_FINANCE_URL, wait_until="domcontentloaded", timeout=30000)
                self.page.wait_for_timeout(3000)

            # Step 1: Select target outlet from the top-left dropdown
            self.outlet_selector.select_global_outlet(restaurant_name_or_id=target_id, restaurant_name=restaurant_name)
            self.page.wait_for_timeout(2000)

            # Step 2: Navigate to Past Payouts / Current Payout tab if present
            past_tab = self.find_clickable([
                "//button[contains(., 'Past Payouts') or contains(., 'Payout History') or contains(., 'Past Payout')]",
                "//div[@role='tab'][contains(., 'Past Payouts') or contains(., 'Past')]",
                "//*[text()='Past Payouts']",
            ], timeout_ms=2000)
            if past_tab:
                try:
                    past_tab.click()
                    print("[+] Switched to 'Past Payouts' tab.")
                    self.page.wait_for_timeout(2000)
                except Exception:
                    pass

            # Step 3: Match cycle card by maximum overlap and click 'See details ->'
            card_info = self.select_payout_card_and_open_details(start_date, end_date, date_label)
            self.page.wait_for_timeout(2000)

            # Step 4: Expand accordions in the drawer
            self.expand_drawer_accordions()
            self.page.wait_for_timeout(1500)

            # Step 5: Capture drawer and body text
            drawer_text = ""
            all_text = ""
            for f in self.page.frames:
                try:
                    f_res = f.evaluate("""() => {
                        const drawer = document.querySelector('[class*="drawer"], [class*="modal"], [class*="sheet"], [class*="sidebar"], [class*="details"], [data-testid*="drawer"]') || document.body;
                        return {
                            drawerText: drawer ? drawer.innerText : '',
                            allText: document.body ? document.body.innerText : ''
                        };
                    }""")
                    if len(f_res.get("drawerText", "")) > len(drawer_text):
                        drawer_text = f_res.get("drawerText", "")
                    if len(f_res.get("allText", "")) > len(all_text):
                        all_text = f_res.get("allText", "")
                except Exception:
                    pass

            # Step 6: Parse financial breakdown — prefer intercepted JSON, fall back to DOM text
            latest_json = self.network_capture.get_best_response_json("payout")
            parsed = self.parser.parse_payout_text(
                drawer_text=drawer_text,
                all_text=all_text,
                card_header_text=card_info.get("card_header", ""),
                raw_json=latest_json,
            )
            data.update(parsed)

            print("[✓] Extracted from Swiggy Finance tab:", {k: v for k, v in data.items() if v is not None})

        except Exception as e:
            print(f"[!] Error in Swiggy Finance tab extraction: {e}")
        finally:
            self.close_all_drawers_and_modals()

        return data
