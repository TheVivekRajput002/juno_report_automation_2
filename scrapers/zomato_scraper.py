import time
import re
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from playwright.sync_api import Page, Locator
from config import (
    ZOMATO_BASE_URL,
    ZOMATO_DASHBOARD_URL,
    ZOMATO_FINANCE_URL,
    ZOMATO_REPORTS_URL,
)
from processors.metric_calculator import clean_number


class ZomatoScraper:
    """
    Automates data extraction from Zomato Restaurant Partner Portal:
    1. Reporting Tab (Business reports matrix table):
       - Online %, Kitchen preparation time, Impressions, Impressions to menu,
         Menu to order, Cart to order, New users, Rejections.
    2. Finance -> Payouts Tab (Payout details side-drawer):
       - Orders, Net order value (A), Item subtotal, Total discounts, Packaging charges,
         Order level deductions (C), Tax deductions (D), Investments in growth (E), Est payout.
    """

    def __init__(self, page: Optional[Page] = None):
        self.page = page
        self.intercepted_data: Dict[str, Any] = {}
        self.extracted_restaurant_name: Optional[str] = None
        self.extracted_restaurant_id: Optional[str] = None
        if self.page:
            self._setup_network_interception()

    @staticmethod
    def _parse_outlet_label(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Parses restaurant name and ID from outlet labels like 'The Spice Meridian (Id: 22663260)' or 'The Paneer Story\nShankar Nagar, Raipur | ID: 22749423'."""
        if not text:
            return None, None

        # Extract ID first
        res_id = None
        m_id = re.search(r"\b(?:[Ii][Dd]|Id|ID)[:\s#]+(\d{6,10})", text)
        if m_id:
            res_id = m_id.group(1).strip()

        # Extract clean name (first line or before address / pipe / ID)
        first_line = text.strip().split("\n")[0].strip()
        clean = re.sub(r"\s*\(?\b[Ii][Dd]\b:?\s*\d+\)?.*$", "", first_line, flags=re.I)
        clean = re.sub(r"\s*\|.*$", "", clean).strip()
        clean = re.sub(r"\s*-\s*\d+.*$", "", clean).strip()
        if clean.endswith("(") or clean.endswith("-"):
            clean = clean[:-1].strip()

        name = clean if clean and not clean.isdigit() else None
        if not res_id and text.strip().isdigit():
            res_id = text.strip()

        return name, res_id


    def _setup_network_interception(self):
        """Intercepts internal JSON responses for reporting, payouts, and settlements."""
        def handle_response(response):
            try:
                url = response.url.lower()
                if any(kw in url for kw in ["api", "settlement", "report", "payout", "performance", "metric", "finance"]):
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        data = response.json()
                        self.intercepted_data[response.url] = data
            except Exception:
                pass

        self.page.on("response", handle_response)

    def _find_clickable(self, candidates: List[str], timeout_ms: int = 2000) -> Optional[Locator]:
        """Tries multiple selectors safely across main page and all frames and returns the first visible one."""
        for sel in candidates:
            try:
                elem = self.page.locator(sel).first
                if elem.is_visible(timeout=timeout_ms):
                    return elem
            except Exception:
                pass
            for f in self.page.frames:
                try:
                    elem = f.locator(sel).first
                    if elem.is_visible(timeout=timeout_ms // 2):
                        return elem
                except Exception:
                    pass
        return None

    def check_login_status(self) -> bool:
        """Checks if the user session is active on Zomato Partner portal."""
        try:
            self.page.goto(ZOMATO_DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
            current_url = self.page.url

            # Redirected to login/signin
            if "login" in current_url or "signin" in current_url:
                return False

            # Check if any nav element or body text is present
            keywords = ["Reporting", "Finance", "Orders", "Menu", "Payouts", "Business reports"]
            for kw in keywords:
                try:
                    elem = self.page.get_by_text(kw, exact=False).first
                    if elem.is_visible(timeout=1000):
                        return True
                except Exception:
                    pass

            for f in self.page.frames:
                try:
                    body_text = f.evaluate("() => document.body ? document.body.innerText : ''")
                    if any(k.lower() in body_text.lower() for k in ["reporting", "finance", "payouts", "orders", "delivered"]):
                        return True
                except Exception:
                    pass

            return False
        except Exception:
            return False

    def select_weekly_view(self) -> bool:
        """Ensures the Weekly view / granularity is selected in Business reports."""
        print("[*] Checking 'Weekly' view / granularity...")
        # Check if weekly view is already active
        for f in [self.page.main_frame] + self.page.frames:
            try:
                txt = f.evaluate("() => document.body ? document.body.innerText : ''")
                if "week" in txt.lower() and any(f"week {n}" in txt.lower() for n in range(1, 53)):
                    print("[+] Weekly view is active in reporting table.")
                    return True
            except Exception:
                pass

        weekly_selectors = [
            "//button[normalize-space()='Weekly']",
            "//div[@role='tab'][normalize-space()='Weekly']",
            "//span[normalize-space()='Weekly']",
            "//a[normalize-space()='Weekly']",
            "//label[contains(., 'Weekly')]",
            "//*[contains(@class, 'tab') or contains(@class, 'toggle') or contains(@class, 'btn')][normalize-space()='Weekly']",
            "//div[contains(@class, 'dropdown') or @role='button'][contains(., 'Daily') or contains(., 'Monthly') or contains(., 'Weekly')]",
        ]
        weekly_btn = self._find_clickable(weekly_selectors, timeout_ms=2500)
        if weekly_btn:
            try:
                btn_txt = weekly_btn.inner_text().strip()
                if "weekly" in btn_txt.lower():
                    weekly_btn.click()
                    print("[+] Clicked 'Weekly' view toggle.")
                    self.page.wait_for_timeout(2500)
                    return True
                else:
                    weekly_btn.click()
                    self.page.wait_for_timeout(1000)
                    opt = self._find_clickable(["//div[@role='option'][contains(., 'Weekly')]", "//li[contains(., 'Weekly')]"], timeout_ms=1500)
                    if opt:
                        opt.click()
                        print("[+] Selected 'Weekly' from view dropdown.")
                        self.page.wait_for_timeout(2500)
                        return True
            except Exception as e:
                print(f"[!] Notice selecting 'Weekly': {e}")

        # Try evaluating click on Weekly element in any frame
        for f in [self.page.main_frame] + self.page.frames:
            try:
                clicked = f.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('button, div, span, a, label, [role="tab"]'));
                    for (const el of elements) {
                        if (el.innerText && el.innerText.trim().toLowerCase() === 'weekly') {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if clicked:
                    print("[+] Clicked 'Weekly' via frame DOM evaluation.")
                    self.page.wait_for_timeout(2500)
                    return True
            except Exception:
                pass

        return False

    def select_restaurant_outlet(self, restaurant_name_or_id: Optional[str] = None) -> bool:
        """
        Selects the specific restaurant outlet from:
        1. Reporting page: 'All outlets' Filter modal ('#modal')
        2. Payouts page: 'Show data for' Dialog ('div[role="dialog"]' / '.z-10.max-h-[720px]')
        Matches by Restaurant ID (e.g. 22317789 / 21735067) or Name (e.g. Biryani Lovers).
        """
        target = (str(restaurant_name_or_id).strip() if restaurant_name_or_id else DEFAULT_RESTAURANT_ID).lower()
        target_name = (str(restaurant_name_or_id).strip() if restaurant_name_or_id else DEFAULT_RESTAURANT_NAME).lower()
        display_target = restaurant_name_or_id or f"{DEFAULT_RESTAURANT_NAME} ({DEFAULT_RESTAURANT_ID})"
        print(f"[*] Selecting restaurant outlet for target: '{display_target}'...")

        try:
            # Check if modal/dialog is already open
            modal_already_open = False
            payout_dialog = self._find_clickable([
                "//div[@role='dialog']",
                "//div[contains(@class, 'max-h-[720px]')]",
                "//*[text()='Show data for']/ancestor::div[@role='dialog' or contains(@class, 'z-50') or contains(@class, 'z-10')]",
            ], timeout_ms=1000)

            reporting_modal = self._find_clickable([
                "#modal",
                "div[id='modal']",
                "div.sc-fBuWsC",
            ], timeout_ms=1000)

            if payout_dialog or reporting_modal:
                modal_already_open = True
                print("[*] Outlet selection dialog/modal is already open.")

            # If not already open, trigger the button
            if not modal_already_open:
                outlet_btn_selectors = [
                    "//span[normalize-space()='All outlets']",
                    "//div[contains(@class, 'css-1ccmdtj')]",
                    "//div[contains(@class, 'css-rwuj9v')]",
                    "//button[contains(., 'All outlets')]",
                    "//div[@role='button'][contains(., 'All outlets')]",
                    "//*[text()='All outlets']",
                    "//button[contains(., 'Show data for') or contains(., 'outlets')]",
                    "//div[@role='button'][contains(., 'Show data for') or contains(., 'outlets')]",
                    "//div[contains(@class, 'outlet-select') or contains(@class, 'outletSelect')]",
                    "//button[contains(., 'Select Outlet') or contains(., 'Select restaurant')]",
                    f"//button[contains(., '{target}') or contains(., '{target_name}')]",
                    f"//div[@role='button'][contains(., '{target}') or contains(., '{target_name}')]",
                ]

                outlet_btn = self._find_clickable(outlet_btn_selectors, timeout_ms=2500)
                if not outlet_btn:
                    outlet_btn = self._find_clickable([
                        "//div[contains(., 'Generate report')]/following::div[contains(@class, 'css-r8w159')][1]",
                        "//div[contains(., 'Generate report')]/following::*[contains(., 'outlet') or contains(., 'All')][1]",
                        "//button[contains(., 'Generate report')]/following-sibling::*[1]",
                    ], timeout_ms=1500)

                if outlet_btn:
                    btn_text = outlet_btn.inner_text().strip()
                    print(f"[*] Found outlet selector button: '{btn_text}'")

                    # If already selected this specific restaurant ID and not 'All outlets'
                    if (target in btn_text.lower() or target_name in btn_text.lower()) and "all outlet" not in btn_text.lower():
                        print(f"[+] Restaurant '{btn_text}' is already active.")
                        name, res_id = self._parse_outlet_label(btn_text)
                        if name:
                            self.extracted_restaurant_name = name
                        if res_id:
                            self.extracted_restaurant_id = res_id
                        return True

                    outlet_btn.click()
                    self.page.wait_for_timeout(1500)
                else:
                    # JS fallback to click any element with 'All outlets' or outlet trigger
                    clicked_trigger = self.page.evaluate("""() => {
                        const candidates = Array.from(document.querySelectorAll('span, div, button, a'));
                        const allOutlets = candidates.find(
                            el => el.innerText && (el.innerText.trim() === 'All outlets' || el.innerText.trim().includes('outlets') || el.innerText.trim().includes('Show data for'))
                        );
                        if (allOutlets) {
                            allOutlets.click();
                            return true;
                        }
                        return false;
                    }""")
                    if clicked_trigger:
                        print("[+] Clicked outlet selector trigger via JS evaluation.")
                        self.page.wait_for_timeout(1500)

            # Wait briefly for dialog animation
            self.page.wait_for_timeout(1000)

            # -------------------------------------------------------------
            # CASE A: PAYOUTS DIALOG ("Show data for" / role="dialog")
            # -------------------------------------------------------------
            payout_dialog = self._find_clickable([
                "//div[@role='dialog']",
                "//div[contains(@class, 'max-h-[720px]')]",
                "//*[text()='Show data for']/ancestor::section",
            ], timeout_ms=1500)

            if payout_dialog:
                print("[*] Detected Payouts 'Show data for' dialog.")

                # Ensure 'Restaurant' tab is active
                res_tab = self._find_clickable([
                    "//div[@role='dialog']//span[normalize-space()='Restaurant']",
                    "//span[normalize-space()='Restaurant']",
                ], timeout_ms=1000)
                if res_tab:
                    try:
                        res_tab.click()
                        self.page.wait_for_timeout(400)
                    except Exception:
                        pass

                # Search box
                search_box = self._find_clickable([
                    "//div[@role='dialog']//input[contains(@placeholder, 'Search')]",
                    "//input[contains(@placeholder, 'Search by restaurant ID')]",
                    "//div[@role='dialog']//input",
                ], timeout_ms=1500)

                search_query = str(restaurant_name_or_id or DEFAULT_RESTAURANT_ID).strip()
                if search_box:
                    try:
                        search_box.fill("")
                        self.page.wait_for_timeout(200)
                        search_box.fill(search_query)
                        print(f"[*] Typed '{search_query}' in Payouts outlet search box.")
                        self.page.wait_for_timeout(800)
                    except Exception as e:
                        print(f"[!] Error typing in Payouts search box: {e}")

                # Click target outlet option (radio button / label)
                payout_item_selectors = [
                    f"//div[@role='dialog']//label[@for='{target}']",
                    f"//div[@role='dialog']//input[@id='{target}']",
                    f"//label[@for='{target}']",
                    f"//input[@id='{target}']",
                    f"//div[@role='dialog']//label[contains(., '{target}')]",
                    f"//div[@role='dialog']//label[contains(., '{target_name}')]",
                    f"//div[@role='dialog']//*[contains(text(), '{target}')]",
                ]
                payout_item = self._find_clickable(payout_item_selectors, timeout_ms=2000)
                if payout_item:
                    try:
                        payout_text = payout_item.inner_text().strip()
                        payout_item.click()
                        print(f"[+] Clicked outlet radio option: '{payout_text or target}'")
                        name, res_id = self._parse_outlet_label(payout_text)
                        if name:
                            self.extracted_restaurant_name = name
                        if res_id:
                            self.extracted_restaurant_id = res_id
                        self.page.wait_for_timeout(800)
                    except Exception as e:
                        print(f"[!] Error clicking Payouts outlet radio: {e}")
                else:
                    # JS fallback for Payouts dialog
                    clicked_payout_text = self.page.evaluate("""({ target, targetName }) => {
                        const dialog = document.querySelector('div[role="dialog"]') || document.body;
                        const labels = Array.from(dialog.querySelectorAll('label, input[type="radio"], div.border-b'));
                        for (const l of labels) {
                            const txt = (l.innerText || '' + l.id || '').toLowerCase();
                            if (txt.includes(target) || txt.includes(targetName) || l.htmlFor === target || l.id === target) {
                                l.click();
                                return l.innerText ? l.innerText.trim() : target;
                            }
                        }
                        return null;
                    }""", {"target": target, "targetName": target_name})
                    if clicked_payout_text:
                        print(f"[+] Clicked outlet radio via JS evaluation: '{clicked_payout_text}'")
                        name, res_id = self._parse_outlet_label(clicked_payout_text)
                        if name:
                            self.extracted_restaurant_name = name
                        if res_id:
                            self.extracted_restaurant_id = res_id
                        self.page.wait_for_timeout(800)

                # Click Apply button in Payouts dialog
                apply_payout_selectors = [
                    "//div[@role='dialog']//button[normalize-space()='Apply' or contains(., 'Apply')]",
                    "//div[contains(@class, 'max-h-[720px]')]//button[contains(., 'Apply')]",
                    "//button[contains(@class, 'h-12') and contains(., 'Apply')]",
                    "//button[normalize-space()='Apply']",
                ]
                apply_btn = self._find_clickable(apply_payout_selectors, timeout_ms=2500)
                if apply_btn:
                    try:
                        apply_btn.click()
                        print("[+] Clicked 'Apply' in Payouts dialog.")
                        self.page.wait_for_timeout(3500)
                        return True
                    except Exception as e:
                        print(f"[!] Error clicking Payouts Apply button: {e}")
                else:
                    applied = self.page.evaluate("""() => {
                        const dialog = document.querySelector('div[role="dialog"]') || document.body;
                        const btns = Array.from(dialog.querySelectorAll('button, div[role="button"]'));
                        for (const b of btns) {
                            if ((b.innerText || '').trim().toLowerCase() === 'apply') {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if applied:
                        print("[+] Clicked 'Apply' in Payouts dialog via JS evaluation.")
                        self.page.wait_for_timeout(3500)
                        return True

            # -------------------------------------------------------------
            # CASE B: REPORTING TAB FILTER MODAL ('#modal')
            # -------------------------------------------------------------
            # Inside the Filter modal, make sure 'Outlet' category on the left sidebar is selected
            outlet_tab_selectors = [
                "//div[@id='modal']//div[contains(@class, 'css-12zjku')]//span[text()='Outlet']",
                "//div[@id='modal']//span[normalize-space()='Outlet']",
                "//div[@id='modal']//*[normalize-space()='Outlet' and not(contains(., 'Subzone'))]",
                "//span[text()='Outlet']",
            ]
            outlet_tab = self._find_clickable(outlet_tab_selectors, timeout_ms=2000)
            if outlet_tab:
                try:
                    outlet_tab.click()
                    print("[+] Selected 'Outlet' tab on filter sidebar.")
                    self.page.wait_for_timeout(600)
                except Exception as e:
                    print(f"[!] Error clicking Outlet tab: {e}")
            else:
                self.page.evaluate("""() => {
                    const modal = document.querySelector('#modal') || document.body;
                    const tabs = Array.from(modal.querySelectorAll('span, div'));
                    for (const t of tabs) {
                        if (t.innerText && t.innerText.trim() === 'Outlet') {
                            t.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                self.page.wait_for_timeout(600)

            # Clear previous selections if 'Clear all' / 'Clear' is present in modal
            self.page.evaluate("""() => {
                const modal = document.querySelector('#modal') || document.body;
                const buttons = Array.from(modal.querySelectorAll('button, span, a, div[role="button"]'));
                for (const b of buttons) {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    if (txt === 'clear all' || txt === 'clear filters' || txt === 'deselect all') {
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            self.page.wait_for_timeout(400)

            # Search box in Reporting modal
            search_query = str(restaurant_name_or_id or DEFAULT_RESTAURANT_ID).strip()
            search_box = self._find_clickable([
                "#modal input[placeholder='Search']",
                "#modal input[type='text']",
                "//div[@id='modal']//input",
                "//input[@placeholder='Search']",
            ], timeout_ms=2000)

            if search_box:
                try:
                    search_box.fill("")
                    self.page.wait_for_timeout(200)
                    search_box.fill(search_query)
                    print(f"[*] Typed '{search_query}' in outlet filter search box.")
                    self.page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"[!] Error typing in search box: {e}")
            else:
                self.page.evaluate("""(query) => {
                    const input = document.querySelector('#modal input') || document.querySelector('input[placeholder="Search"]');
                    if (input) {
                        input.value = query;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", search_query)
                self.page.wait_for_timeout(1000)

            # Click matching outlet row / checkbox
            option_found = False
            item_selectors = [
                f"//div[@id='modal']//div[contains(@class, 'css-1mwie36')][contains(., '{target}')]",
                f"//div[@id='modal']//*[contains(@class, 'css-gj25qc')][contains(., '{target}')]",
                f"//div[@id='modal']//*[contains(text(), '{target}')]",
                f"//div[@id='modal']//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target}')]",
                f"//div[@id='modal']//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target_name}')]",
            ]

            target_elem = self._find_clickable(item_selectors, timeout_ms=2500)
            if target_elem:
                try:
                    elem_text = target_elem.inner_text().strip()
                    target_elem.click()
                    print(f"[+] Clicked matching outlet option: '{elem_text}'")
                    name, res_id = self._parse_outlet_label(elem_text)
                    if name:
                        self.extracted_restaurant_name = name
                    if res_id:
                        self.extracted_restaurant_id = res_id
                    option_found = True
                    self.page.wait_for_timeout(800)
                except Exception as e:
                    print(f"[!] Error clicking target outlet element: {e}")

            if not option_found:
                clicked_js = self.page.evaluate("""({ target, targetName }) => {
                    const modal = document.querySelector('#modal') || document.body;
                    const items = Array.from(modal.querySelectorAll('[class*="css-1mwie36"], [class*="css-gj25qc"], [data-test-id="virtuoso-item-list"] > div, label'));
                    for (const it of items) {
                        const txt = (it.innerText || '').toLowerCase();
                        if ((txt.includes(target) || txt.includes(targetName)) && !txt.includes('clear all') && !txt.includes('apply')) {
                            it.click();
                            return it.innerText.trim();
                        }
                    }
                    return null;
                }""", {"target": target, "targetName": target_name})
                if clicked_js:
                    print(f"[+] Clicked matching outlet via JS evaluation: '{clicked_js}'")
                    name, res_id = self._parse_outlet_label(clicked_js)
                    if name:
                        self.extracted_restaurant_name = name
                    if res_id:
                        self.extracted_restaurant_id = res_id
                    option_found = True
                    self.page.wait_for_timeout(800)

            # Click Apply button in Filter modal
            apply_btn_selectors = [
                "//div[@id='modal']//button[normalize-space()='Apply' or contains(., 'Apply')]",
                "//div[@id='modal']//*[normalize-space()='Apply' or text()='Apply']",
                "//button[normalize-space()='Apply']",
                "//button[contains(., 'Apply')]",
                "//*[text()='Apply']/ancestor::button",
                "//div[@role='button'][contains(., 'Apply')]",
                "//*[normalize-space()='Apply']",
            ]
            apply_btn = self._find_clickable(apply_btn_selectors, timeout_ms=2500)
            if apply_btn:
                try:
                    apply_btn.click()
                    print("[+] Clicked 'Apply' button in Filter modal.")
                    self.page.wait_for_timeout(4000)
                    return True
                except Exception as e:
                    print(f"[!] Error clicking Apply button: {e}")
            else:
                applied_js = self.page.evaluate("""() => {
                    const modal = document.querySelector('#modal') || document.body;
                    const elements = Array.from(modal.querySelectorAll('button, div, span, a'));
                    for (const el of elements) {
                        const txt = (el.innerText || '').trim().toLowerCase();
                        if (txt === 'apply') {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if applied_js:
                    print("[+] Clicked 'Apply' via JS evaluation.")
                    self.page.wait_for_timeout(4000)
                    return True
                else:
                    print("[!] Apply button not found in modal.")

        except Exception as e:
            print(f"[!] Error in outlet selection: {e}")

        return False

    def _close_all_drawers_and_modals(self):
        """Closes any open side-drawers, modals, or dialog backdrops."""
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    f.evaluate("""() => {
                        const closeBtns = Array.from(document.querySelectorAll('[aria-label="close"], [aria-label="Close"], button[class*="close"], [class*="close-icon"], [class*="CloseIcon"], svg[class*="close"]'));
                        for (const b of closeBtns) {
                            try { b.click(); } catch(e) {}
                        }
                    }""")
                except Exception:
                    pass
            self.page.wait_for_timeout(300)
        except Exception:
            pass

    # -------------------------------------------------------------
    # 1. REPORTING TAB EXTRACTION (BUSINESS REPORTS MATRIX TABLE)
    # -------------------------------------------------------------
    def navigate_and_extract_reporting_tab(
        self, start_date: datetime, end_date: datetime, date_label: Optional[str] = None, restaurant_name: Optional[str] = None, restaurant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Navigates to Reporting -> Business reports, selects the outlet,
        selects weekly view, and extracts funnel/operational metrics from the weekly matrix table.
        """
        data: Dict[str, Any] = {}
        print("\n" + "-" * 50)
        print("[1] Navigating to REPORTING tab (Business reports)...")
        print("-" * 50)

        try:
            self._close_all_drawers_and_modals()

            # Always navigate directly to Reporting page URL to ensure fresh and clean state
            print(f"[*] Navigating directly to Reporting URL: {ZOMATO_REPORTS_URL}")
            self.page.goto(ZOMATO_REPORTS_URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)

            # Step 2: Ensure Business reports section is active
            biz_tab_selectors = [
                "//span[contains(text(), 'Business reports')]",
                "//button[contains(., 'Business reports')]",
                "//div[@role='tab'][contains(., 'Business reports')]",
                "//a[contains(., 'Business reports')]",
                "//*[text()='Business reports']",
            ]
            biz_tab = self._find_clickable(biz_tab_selectors, timeout_ms=3000)
            if biz_tab:
                try:
                    biz_tab.click()
                    print("[+] Clicked 'Business reports' tab.")
                    self.page.wait_for_timeout(3000)
                except Exception:
                    pass

            # Step 3: Select the outlet (restaurant)
            self.select_restaurant_outlet(restaurant_id or restaurant_name)
            self.page.wait_for_timeout(3000)

            # Step 4: Select Weekly view
            self.select_weekly_view()
            self.page.wait_for_timeout(3000)

            # Step 5: Wait for actual table rows to render (poll up to 12 seconds)
            for _ in range(12):
                has_table_rows = False
                for f in self.page.frames:
                    try:
                        row_cnt = f.evaluate("""() => {
                            const trs = document.querySelectorAll('table tbody tr, table tr, [role="table"] [role="row"], [role="grid"] [role="row"]');
                            return trs ? trs.length : 0;
                        }""")
                        if row_cnt >= 3:
                            has_table_rows = True
                            break
                    except Exception:
                        pass
                if has_table_rows:
                    break
                self.page.wait_for_timeout(1000)

            # Step 5b: Expand collapsible row chevrons (e.g. Menu to order -> Cart to order)
            self._expand_reporting_table_accordions()

            # Step 5c: Scroll table horizontally to reveal older columns (e.g. 10-16 Aug)
            self._scroll_reporting_table_to_reveal_columns()

            # Step 6: Extract table headers and cells via DOM traversal across all frames
            table_data = {"headers": [], "rows": [], "rawText": ""}

            for f in self.page.frames:
                try:
                    f_data = f.evaluate("""() => {
                        const result = {
                            headers: [],
                            rows: [],
                            rawText: document.body ? document.body.innerText : ''
                        };

                        // Strategy 1: Look for table or grid elements
                        const tables = document.querySelectorAll('table, [role="table"], [role="grid"]');
                        for (const t of tables) {
                            // Find the header row in the table
                            let ths = [];
                            const theadRow = t.querySelector('thead tr, tr:first-child');
                            if (theadRow) {
                                ths = Array.from(theadRow.querySelectorAll('th, td, [role="columnheader"]')).map(el => (el.innerText || '').trim().replace(/\\s+/g, ' '));
                            }
                            if (ths.length === 0) {
                                ths = Array.from(t.querySelectorAll('th, [role="columnheader"]')).map(el => (el.innerText || '').trim().replace(/\\s+/g, ' '));
                            }
                            if (ths.length > result.headers.length) {
                                result.headers = ths;
                            }
                            const trs = Array.from(t.querySelectorAll('tbody tr, tr[role="row"]'));
                            for (const row of trs) {
                                const cellElements = Array.from(row.querySelectorAll('td, th, [role="cell"], [role="columnheader"]'));
                                const cells = cellElements.map(el => (el.innerText || '').trim());
                                if (cells.length > 1 && cells[0]) {
                                    const headerMap = {};
                                    for (let c = 0; c < ths.length && c < cells.length; c++) {
                                        if (ths[c]) {
                                            headerMap[ths[c]] = cells[c];
                                        }
                                    }
                                    result.rows.push({
                                        metricName: cells[0],
                                        cells: cells,
                                        headerMap: headerMap
                                    });
                                }
                            }
                        }

                        // Strategy 2: Look for Div-based row structures (common in React/Emotion tables)
                        if (result.rows.length === 0) {
                            const potentialRows = Array.from(document.querySelectorAll('div[class*="row"], div[class*="Row"], div[class*="grid"], div[role="row"]'));
                            for (const r of potentialRows) {
                                const cells = Array.from(r.children).map(c => (c.innerText || '').trim()).filter(Boolean);
                                if (cells.length >= 3) {
                                    if (cells.some(c => c.toLowerCase().includes('week') || /\\d+\\s*-\\s*\\d+\\s*[A-Za-z]+/.test(c))) {
                                        if (cells.length > result.headers.length) {
                                            result.headers = cells;
                                        }
                                    } else if (cells[0] && cells[0].length < 40 && !cells[0].includes('\\n')) {
                                        result.rows.push({
                                            metricName: cells[0],
                                            cells: cells,
                                            headerMap: {}
                                        });
                                    }
                                }
                            }
                        }

                        return result;
                    }""")
                    if len(f_data.get("rows", [])) > len(table_data.get("rows", [])):
                        table_data = f_data
                    elif not table_data.get("rawText") and f_data.get("rawText"):
                        table_data["rawText"] = f_data.get("rawText")
                except Exception:
                    continue

            headers = table_data.get("headers", [])
            rows = table_data.get("rows", [])
            body_text = table_data.get("rawText", "")

            # If 0 table rows found on first attempt, retry clicking Business reports and Weekly view
            if len(rows) == 0:
                print("[!] 0 table rows found on initial scan. Retrying tab navigation and table load...")
                biz_tab = self._find_clickable(biz_tab_selectors, timeout_ms=2000)
                if biz_tab:
                    try:
                        biz_tab.click()
                        self.page.wait_for_timeout(2000)
                    except Exception:
                        pass
                self.select_restaurant_outlet(restaurant_id or restaurant_name)
                self.select_weekly_view()
                self.page.wait_for_timeout(3000)
                self._expand_reporting_table_accordions()
                self._scroll_reporting_table_to_reveal_columns()

                # Re-scan frames for table data
                for f in self.page.frames:
                    try:
                        f_data = f.evaluate("""() => {
                            const result = { headers: [], rows: [], rawText: document.body ? document.body.innerText : '' };
                            const tables = document.querySelectorAll('table, [role="table"], [role="grid"]');
                            for (const t of tables) {
                                let ths = [];
                                const theadRow = t.querySelector('thead tr, tr:first-child');
                                if (theadRow) {
                                    ths = Array.from(theadRow.querySelectorAll('th, td, [role="columnheader"]')).map(el => (el.innerText || '').trim().replace(/\\s+/g, ' '));
                                }
                                if (ths.length === 0) {
                                    ths = Array.from(t.querySelectorAll('th, [role="columnheader"]')).map(el => (el.innerText || '').trim().replace(/\\s+/g, ' '));
                                }
                                if (ths.length > result.headers.length) {
                                    result.headers = ths;
                                }
                                const trs = Array.from(t.querySelectorAll('tbody tr, tr[role="row"]'));
                                for (const row of trs) {
                                    const cellElements = Array.from(row.querySelectorAll('td, th, [role="cell"], [role="columnheader"]'));
                                    const cells = cellElements.map(el => (el.innerText || '').trim());
                                    if (cells.length > 1 && cells[0]) {
                                        const headerMap = {};
                                        for (let c = 0; c < ths.length && c < cells.length; c++) {
                                            if (ths[c]) {
                                                headerMap[ths[c]] = cells[c];
                                            }
                                        }
                                        result.rows.push({
                                            metricName: cells[0],
                                            cells: cells,
                                            headerMap: headerMap
                                        });
                                    }
                                }
                            }
                            return result;
                        }""")
                        if len(f_data.get("rows", [])) > len(table_data.get("rows", [])):
                            table_data = f_data
                    except Exception:
                        continue

                headers = table_data.get("headers", [])
                rows = table_data.get("rows", [])
                body_text = table_data.get("rawText", "")

            # If headers not extracted cleanly, scan text for week headers e.g. "Week 33 10 - 16 Aug 2026"
            if not headers or len(headers) < 3:
                week_matches = re.findall(r"(?:Week\s*\d+[\s\S]*?\d+\s*-\s*\d+\s*[A-Za-z]+(?:\s*\d{4})?|Week\s*\d+)", body_text)
                if week_matches:
                    headers = ["Metric", "Trend"] + [w.strip() for w in week_matches]

            print(f"[*] Discovered {len(headers)} columns and {len(rows)} table rows in Reporting.")
            if headers:
                print(f"[*] Column Headers: {[h.replace(chr(10), ' ') for h in headers]}")

            # 6. Find target column index for this date range
            target_col_idx = self._find_target_column_index(headers, start_date, end_date, date_label)
            header_name = headers[target_col_idx].replace("\n", " ") if target_col_idx < len(headers) else "N/A"
            print(f"[*] Target column index: {target_col_idx} (Header: '{header_name}')")

            # 7. Extract from structured rows
            if rows:
                extracted = self._extract_metrics_from_table_rows(rows, target_col_idx, start_date, end_date, date_label)
                data.update(extracted)

            # 8. Text matrix fallback parser over full body text
            extracted_fallback = self._parse_reporting_text_matrix(body_text, target_col_idx, headers, start_date, end_date)
            for k, v in extracted_fallback.items():
                if k not in data or data[k] is None or data[k] == 0:
                    data[k] = v

            # 9. Additional search for C2O / Cart to order in page widgets only if not yet set
            if "c2o" not in data or not data["c2o"]:
                m_c2o = re.search(r"(?:Cart to order|Menu to cart|Cart conversion|C2O)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%", body_text, re.I)
                if m_c2o:
                    data["c2o"] = clean_number(m_c2o.group(1))

            print("[✓] Extracted from Reporting tab:", {k: v for k, v in data.items() if v is not None})

        except Exception as e:
            print(f"[!] Error in Reporting tab extraction: {e}")

        return data

    def _scroll_reporting_table_to_reveal_columns(self):
        """Scrolls table containers horizontally across all frames to ensure older weeks (e.g. 10-16 Aug) are rendered."""
        print("[*] Scrolling Business reports table horizontally to reveal earlier weekly columns...")
        for f in [self.page.main_frame] + self.page.frames:
            try:
                f.evaluate("""() => {
                    const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
                        return (el.scrollWidth > el.clientWidth) && (el.clientWidth > 250);
                    });
                    for (const s of scrollables) {
                        s.scrollLeft = 0; // scroll to earliest columns on the left
                    }
                }""")
            except Exception:
                pass
        self.page.wait_for_timeout(800)

    def _parse_reporting_text_matrix(
        self, body_text: str, target_col_idx: int, headers: List[str], start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Robustly parses metric sequences from raw page text.
        Filters out comparison/trend delta badges (e.g., '▲ +9%', '▼ -3%', '-17.3%')
        and maps weekly metric columns strictly to the target week.
        """
        metrics: Dict[str, Any] = {}
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]

        # Identify all week columns present in body_text or headers
        week_headers = []
        for h in headers:
            h_clean = h.replace("\n", " ").strip()
            if any(k in h_clean.lower() for k in ["metric", "trend", "vs", "comparison"]) and not re.search(r"\bweek\b|\d+\s*-\s*\d+", h_clean, re.I):
                continue
            if re.search(r"week\s*\d+|\d+\s*-\s*\d+\s*[A-Za-z]+", h_clean, re.I):
                week_headers.append(h_clean)

        if not week_headers:
            week_headers = re.findall(r"(?:Week\s*\d+(?:\s*[\(\[]?[^\n\r\)\]]+[\)\]]?)?|\d+\s*-\s*\d+\s*[A-Za-z]+)", body_text, re.I)

        target_week_offset = None
        if start_date and end_date and week_headers:
            s_day = start_date.strftime("%d").lstrip("0")
            e_day = end_date.strftime("%d").lstrip("0")
            m_abbr = start_date.strftime("%b").lower()
            cal_week = start_date.isocalendar()[1]

            for w_idx, wh in enumerate(week_headers):
                wh_low = wh.lower()
                if (s_day in wh_low and e_day in wh_low and m_abbr in wh_low) or (f"week {cal_week}" in wh_low or f"week{cal_week}" in wh_low):
                    target_week_offset = w_idx
                    break

        def extract_clean_sequence(line_idx: int, is_pct_conversion: bool = False) -> Optional[float]:
            raw_tokens = []
            for j in range(line_idx + 1, min(line_idx + 40, len(lines))):
                val_str = lines[j]
                if any(k.lower() == val_str.lower() or val_str.lower().startswith(k.lower()) for k in [
                    "sales overview", "customer experience", "funnel", "sales", "delivered orders", "orders",
                    "average order value", "average rating", "bad orders", "total complaints", "online %",
                    "kitchen preparation", "impressions", "impressions to menu", "menu to order", "cart to order",
                    "new users", "lost sales", "rejections", "compare performance", "gross sales"
                ]):
                    break
                # Match numbers, currencies, percentages, minutes
                if re.search(r"^[-+▲▼]?\s*₹?\s*[\d,]+(?:\.\d+)?\s*(?:%|mins|min)?$", val_str):
                    raw_tokens.append(val_str)

            if not raw_tokens:
                return None

            # Filter tokens: separate trend badges (e.g. +9%, -3%, ▲5%) vs absolute values
            first_is_trend = False
            first_val = raw_tokens[0].strip()
            if (
                first_val.startswith("+")
                or first_val.startswith("▲")
                or first_val.startswith("▼")
                or (first_val.startswith("-") and is_pct_conversion)
                or (len(raw_tokens) > len(week_headers) and len(week_headers) > 0)
            ):
                first_is_trend = True

            pure_values = []
            for idx, tok in enumerate(raw_tokens):
                if idx == 0 and first_is_trend:
                    continue
                num = clean_number(tok)
                # Funnel conversion rates are strictly non-negative
                if is_pct_conversion and num < 0:
                    continue
                pure_values.append(num)

            if not pure_values:
                return None

            # If target_week_offset is determined relative to weekly headers
            if target_week_offset is not None and target_week_offset < len(pure_values):
                return pure_values[target_week_offset]

            # If target_col_idx in headers table
            if len(headers) > 2 and target_col_idx >= 2:
                col_offset = target_col_idx - 2
                if col_offset < len(pure_values):
                    return pure_values[col_offset]

            # Default fallback: 2nd from end if latest is in progress
            if len(pure_values) >= 2:
                return pure_values[-2]
            return pure_values[-1]

        for i, line in enumerate(lines):
            l_lower = line.lower()

            # 1. Delivered orders / Orders
            if ("delivered orders" in l_lower or (l_lower == "orders" and "average" not in l_lower and "bad" not in l_lower)) and "orders" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["orders"] = val
                    metrics["reporting_orders"] = val
                    metrics["delivered_orders"] = val

            # 2. Sales
            elif l_lower == "sales" and "sales" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["sales"] = val
                    metrics["subtotal"] = val

            # 3. Average Order Value
            elif ("average order value" in l_lower or l_lower == "aov") and "net_order_value" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["net_order_value"] = val
                    metrics["aov"] = val

            # 4. Average Rating
            elif "average rating" in l_lower and "avg_rating" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["avg_rating"] = val

            # 5. Bad Orders
            elif "bad order" in l_lower and "bad_orders" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["bad_orders"] = val

            # 6. Total Complaints
            elif ("total complaints" in l_lower or l_lower == "complaints") and "total_complaints" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["total_complaints"] = val

            # 7. Online % / Visibility
            elif ("online %" in l_lower or "visibility" in l_lower) and "visibility" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["visibility"] = val

            # 8. Kitchen prep time
            elif ("kitchen preparation" in l_lower or "kitchen prep" in l_lower or l_lower == "kpt") and "kpt" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["kpt"] = val

            # 9. Impressions
            elif l_lower == "impressions" and "impressions" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["impressions"] = val

            # 10. Impressions to menu (I2M)
            elif ("impressions to menu" in l_lower or "impression to menu" in l_lower or l_lower == "i2m") and "i2m" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["i2m"] = val

            # 11. Menu to order (M2O)
            elif ("menu to order" in l_lower or l_lower == "m2o") and "m2o" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["m2o"] = val

            # 12. Cart to order (C2O)
            elif ("cart to order" in l_lower or l_lower == "c2o" or "menu to cart" in l_lower) and "c2o" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["c2o"] = val

            # 13. New users
            elif "new user" in l_lower and "new_users" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["new_users"] = val

            # 14. Rejections
            elif ("rejection" in l_lower or "rejected" in l_lower) and "mx_rejections" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["mx_rejections"] = val

        return metrics

    def _find_target_column_index(
        self, headers: List[str], start_date: datetime, end_date: datetime, date_label: Optional[str]
    ) -> int:
        """
        Finds which column index corresponds to the requested date range.
        Handles headers like:
        - 'Week 33\\n10 - 16 Aug 2026'
        - 'Week 34\\n17 - 23 Aug 2026'
        - '10 Aug - 16 Aug'
        """
        if not headers or len(headers) <= 1:
            return 1

        start_day = start_date.strftime("%d").lstrip("0")
        end_day = end_date.strftime("%d").lstrip("0")
        start_day_padded = start_date.strftime("%d")
        end_day_padded = end_date.strftime("%d")
        month_abbr = start_date.strftime("%b").lower()
        month_abbr_end = end_date.strftime("%b").lower()
        cal_week = start_date.isocalendar()[1]

        # Step A: Check each header against exact start day, end day, and month
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in ["trend", "vs", "comparison"]) and not re.search(r"\bweek\b|\d+\s*-\s*\d+", h_lower):
                continue

            # Exact date span match (e.g. "10 - 16 Aug" or "10-16 Aug" or "10 Aug - 16 Aug")
            if re.search(rf"\b0?{start_day}\b[^\d\n\r]*\b0?{end_day}\b[^\n\r]*{month_abbr}", h_lower) is not None:
                return idx

            has_start = (re.search(rf"\b0?{start_day}\b", h_lower) is not None) or (start_day in h_lower) or (start_day_padded in h_lower)
            has_end = (re.search(rf"\b0?{end_day}\b", h_lower) is not None) or (end_day in h_lower) or (end_day_padded in h_lower)
            has_month = (month_abbr in h_lower) or (month_abbr_end in h_lower)

            if has_start and has_end and has_month:
                return idx

            if date_label and (date_label.lower() in h_lower or h_lower in date_label.lower()):
                return idx

        # Step B: Week number match if present
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if f"week {cal_week}" in h_lower or f"week{cal_week}" in h_lower:
                return idx

        # Step C: Relative week offset calculation
        valid_indices = []
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in ["trend", "metric", "vs", "total", "comparison"]) and not re.search(r"\bweek\b|\d+", h_lower):
                continue
            if "week" in h_lower or any(m in h_lower for m in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
                valid_indices.append(idx)

        # If we know the weeks count and the current target week
        today = datetime.now()
        weeks_ago = max(1, int((today - start_date).days / 7))
        if len(valid_indices) >= weeks_ago:
            target_idx_pos = -(weeks_ago + 1)
            if abs(target_idx_pos) <= len(valid_indices):
                return valid_indices[target_idx_pos]

        if len(valid_indices) >= 2:
            return valid_indices[-2]
        elif valid_indices:
            return valid_indices[-1]

        return len(headers) - 1

    def _extract_metrics_from_table_rows(
        self,
        rows: List[Dict[str, Any]],
        target_col_idx: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date_label: Optional[str] = None
    ) -> Dict[str, Any]:
        """Maps table rows to internal metric keys using headerMap or column index."""
        extracted: Dict[str, Any] = {}

        start_day = start_date.strftime("%d").lstrip("0") if start_date else ""
        end_day = end_date.strftime("%d").lstrip("0") if end_date else ""
        start_day_padded = start_date.strftime("%d") if start_date else ""
        end_day_padded = end_date.strftime("%d") if end_date else ""
        month_abbr = start_date.strftime("%b").lower() if start_date else ""
        cal_week = start_date.isocalendar()[1] if start_date else 0

        for row_data in rows:
            metric_name = row_data.get("metricName", "").strip().lower()
            cells = row_data.get("cells", [])
            header_map = row_data.get("headerMap", {})

            cell_val = None
            # 1. First priority: match exact column header key in headerMap
            if header_map and start_date and end_date:
                for h_key, h_val in header_map.items():
                    k_low = h_key.lower()
                    if any(k in k_low for k in ["trend", "vs", "comparison"]) and not re.search(r"\bweek\b|\d+\s*-\s*\d+", k_low):
                        continue
                    if re.search(rf"\b0?{start_day}\b[^\d\n\r]*\b0?{end_day}\b[^\n\r]*{month_abbr}", k_low) is not None:
                        cell_val = h_val
                        break
                    if (start_day in k_low or start_day_padded in k_low) and (end_day in k_low or end_day_padded in k_low) and month_abbr in k_low:
                        cell_val = h_val
                        break
                    if cal_week > 0 and (f"week {cal_week}" in k_low or f"week{cal_week}" in k_low):
                        cell_val = h_val
                        break
                    if date_label and date_label.lower() in k_low:
                        cell_val = h_val
                        break

            # 2. Second priority: use positional index in cells
            if cell_val is None:
                if target_col_idx < len(cells):
                    cell_val = cells[target_col_idx]
                elif cells:
                    cell_val = cells[-1]
                else:
                    cell_val = ""

            # 1. Sales
            if metric_name == "sales" or metric_name == "total sales":
                extracted["sales"] = clean_number(cell_val)
                extracted["subtotal"] = clean_number(cell_val)
                extracted["sales_after_discount"] = clean_number(cell_val)

            # 2. Delivered / Total Orders in reporting table
            elif "delivered" in metric_name or metric_name == "orders" or "total orders" in metric_name:
                extracted["orders"] = clean_number(cell_val)
                extracted["reporting_orders"] = clean_number(cell_val)
                extracted["delivered_orders"] = clean_number(cell_val)

            # 3. Average Order Value
            elif "average order value" in metric_name or "aov" in metric_name:
                extracted["net_order_value"] = clean_number(cell_val)
                extracted["aov"] = clean_number(cell_val)

            # 4. Average rating
            elif "average rating" in metric_name or "rating" in metric_name:
                extracted["avg_rating"] = clean_number(cell_val)

            # 5. Bad orders
            elif "bad order" in metric_name:
                extracted["bad_orders"] = clean_number(cell_val)

            # 6. Total complaints
            elif "complaint" in metric_name:
                extracted["total_complaints"] = clean_number(cell_val)

            # 7. Lost sales
            elif "lost sales" in metric_name:
                extracted["lost_sales"] = clean_number(cell_val)

            # 8. Online % / Visibility
            elif ("online" in metric_name and "%" in metric_name) or "visibility" in metric_name:
                extracted["visibility"] = clean_number(cell_val)

            # 9. Kitchen preparation time (KPT)
            elif "kitchen" in metric_name or "prep" in metric_name or "kpt" in metric_name:
                extracted["kpt"] = clean_number(cell_val)

            # 10. Impressions to menu (I2M)
            elif ("impression" in metric_name or "i2m" in metric_name) and "menu" in metric_name:
                extracted["i2m"] = clean_number(cell_val)

            # 11. Impressions (Total impressions)
            elif "impression" in metric_name and "menu" not in metric_name:
                extracted["impressions"] = clean_number(cell_val)

            # 12. Menu to order (M2O)
            elif ("menu" in metric_name or "m2o" in metric_name) and "order" in metric_name:
                extracted["m2o"] = clean_number(cell_val)

            # 13. Cart to order (C2O)
            elif "cart to order" in metric_name or "cart" in metric_name:
                extracted["c2o"] = clean_number(cell_val)

            # 14. New users
            elif "new user" in metric_name:
                extracted["new_users"] = clean_number(cell_val)

            # 15. Sales from Ads
            elif "sales from ads" in metric_name or "ad sales" in metric_name:
                extracted["sales_from_ads"] = clean_number(cell_val)

            # 16. Gross sales from offers
            elif "gross sales from offers" in metric_name or "offers sales" in metric_name:
                extracted["gross_sales_from_offers"] = clean_number(cell_val)

            # 17. Rejections
            elif "rejection" in metric_name or "rejected" in metric_name:
                extracted["mx_rejections"] = clean_number(cell_val)

        return extracted

    def _expand_reporting_table_accordions(self):
        """Expands collapsible row chevrons in the Business reports table (e.g., Menu to order -> Cart to order) without toggle flipping."""
        print("[*] Checking and expanding table accordions in Business reports (e.g. 'Menu to order' -> 'Cart to order')...")
        
        try:
            # Check if Cart to order is already in the DOM
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    is_expanded = f.evaluate("""() => {
                        const bodyTxt = document.body ? document.body.innerText.toLowerCase() : '';
                        return bodyTxt.includes('cart to order') || bodyTxt.includes('menu to cart');
                    }""")
                    if is_expanded:
                        print("[+] 'Cart to order' accordion is already expanded.")
                        return
                except Exception:
                    pass

            # If not expanded, click the chevron/row once
            clicked = False
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    clicked = f.evaluate("""() => {
                        const rows = Array.from(document.querySelectorAll('tr, [role="row"], div'));
                        for (const r of rows) {
                            const txt = (r.innerText || '').toLowerCase().trim();
                            if (txt.includes('menu to order') && !txt.includes('cart to order')) {
                                const btn = r.querySelector('svg, button, [role="button"], i, [class*="chevron"], [class*="arrow"]') || r;
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if clicked:
                        print("[+] Clicked 'Menu to order' chevron to expand Cart to order.")
                        break
                except Exception:
                    pass

            if not clicked:
                # Playwright fallback
                m2o_btn = self._find_clickable([
                    "//tr[contains(., 'Menu to order')]//svg",
                    "//tr[contains(., 'Menu to order')]//button",
                    "//tr[contains(., 'Menu to order')]",
                    "//*[contains(text(), 'Menu to order')]/..",
                ], timeout_ms=1500)
                if m2o_btn:
                    m2o_btn.click()
                    print("[+] Clicked 'Menu to order' button via Playwright locator.")

            self.page.wait_for_timeout(1500)
        except Exception as e:
            print(f"[!] Warning expanding reporting table accordions: {e}")

    # -------------------------------------------------------------
    # 2. PAYOUT TAB (UNDER FINANCE) EXTRACTION
    # -------------------------------------------------------------
    def navigate_and_extract_payout_tab(
        self, start_date: datetime, end_date: datetime, date_label: Optional[str] = None, restaurant_name: Optional[str] = None, restaurant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Navigates to Finance -> Payouts, selects the restaurant,
        finds and clicks the target date range cycle row, expands the drawer,
        and extracts settlement fields across frames.
        """
        data: Dict[str, Any] = {}
        print("\n" + "-" * 50)
        print("[2] Navigating to PAYOUT tab (under Finance)...")
        print("-" * 50)

        try:
            self._close_all_drawers_and_modals()

            # Step 1: Navigate to Finance -> Payouts directly
            current_url = self.page.url.lower()
            if "payouts" not in current_url:
                print(f"[*] Navigating directly to Payouts URL: {ZOMATO_FINANCE_URL}")
                self.page.goto(ZOMATO_FINANCE_URL, wait_until="domcontentloaded", timeout=30000)
                self.page.wait_for_timeout(3000)

            # Step 2: Select restaurant outlet if selector present
            self.select_restaurant_outlet(restaurant_id or restaurant_name)

            # Step 3: Wait for Payouts page to load
            self.page.wait_for_timeout(2000)

            # Step 4: Find and click the cycle row matching the target dates
            self._select_payout_cycle_row(start_date, end_date, date_label)
            self.page.wait_for_timeout(3000)

            # Step 5: Expand accordion dropdowns inside the Payout details side drawer
            self._expand_payout_drawer_accordions()
            self.page.wait_for_timeout(1500)

            # Step 6: Extract all data fields across frames
            extracted = {}
            for f in self.page.frames:
                try:
                    f_res = f.evaluate("""() => {
                        const res = {};
                        const drawer = document.querySelector('[class*="drawer"], [class*="modal"], [class*="sheet"], [class*="sidebar"], [class*="details"]') || document.body;
                        res.drawerText = drawer ? drawer.innerText : '';
                        res.allText = document.body ? document.body.innerText : '';

                        const headerElem = drawer ? drawer.querySelector('h1, h2, h3, [class*="header"], [class*="title"]') : null;
                        if (headerElem) {
                            res.headerTitle = headerElem.innerText;
                        }
                        return res;
                    }""")
                    total_len = len(f_res.get("drawerText", "")) + len(f_res.get("allText", ""))
                    cur_len = len(extracted.get("drawerText", "")) + len(extracted.get("allText", ""))
                    if total_len > cur_len:
                        extracted = f_res
                except Exception:
                    continue

            drawer_text = extracted.get("drawerText", "")
            all_text = extracted.get("allText", "")
            combined_text = drawer_text + "\n" + all_text

            # Extract Restaurant Name
            m_res = re.search(r">\s*([A-Za-z0-9\s]+?)(?:\.\.\.|\n|$)", drawer_text)
            if m_res:
                data["restaurant_name"] = m_res.group(1).strip()

            # 1. Delivered orders (payout page)
            m_orders = re.search(r"(?:Delivered orders|Total orders|Orders delivered)\s*[:\n\r]*\s*([\d,]+)", combined_text, re.I)
            if m_orders:
                data["payout_delivered_orders"] = clean_number(m_orders.group(1))

            # 2. Net order value (A) / Sales after discount
            m_nov = re.search(r"Net order value\s*(?:\(A\))?\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_nov:
                data["net_order_value_amount"] = clean_number(m_nov.group(1))

            # 3. Item subtotal (under Net Order Value)
            m_subtotal = re.search(r"(?:Item Subtotal|Item Total|Gross Sales)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_subtotal:
                data["subtotal"] = clean_number(m_subtotal.group(1))

            # 4. Total Discounts (hardcoded formula as requested):
            #    Total Discount = Restaurant discount (Promos)
            #                   + Restaurant discount (Flat offs, Freebies, Gold, relisted orders and others)
            #                   + Delivery charge discount (0 if not exists)
            lines = [l.strip() for l in combined_text.splitlines() if l.strip()]

            def get_item_discount(keywords: List[str]) -> float:
                for idx, l in enumerate(lines):
                    l_low = l.lower().strip()
                    if all(kw.lower() in l_low for kw in keywords):
                        # Check for - ₹ amount on the same line
                        m_neg = re.findall(r'[-–—]\s*₹?\s*([\d,]+(?:\.\d+)?)', l)
                        if m_neg:
                            val = abs(clean_number(m_neg[-1]))
                            if val > 0:
                                return val
                        # Check next 1-2 lines for ₹ amount
                        for j in range(idx + 1, min(idx + 3, len(lines))):
                            next_l = lines[j]
                            if any(k in next_l.lower() for k in ["gst", "subtotal", "net order", "additions", "packaging", "order level", "delivery charge", "restaurant discount"]):
                                break
                            m_next = re.search(r'[-–—]?\s*₹\s*([\d,]+(?:\.\d+)?)', next_l)
                            if m_next:
                                val = abs(clean_number(m_next.group(1)))
                                if val > 0:
                                    return val
                                break
                return 0.0

            # Item 1: Restaurant discount (Promos)
            disc_promos = get_item_discount(["restaurant discount", "promos"])
            if disc_promos == 0.0:
                disc_promos = get_item_discount(["promos"])
            if disc_promos == 0.0:
                m_p = re.search(r"(?:Restaurant discount\s*\(Promos\)|Promos(?:\s*discount)?)\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
                if m_p:
                    disc_promos = abs(clean_number(m_p.group(1)))

            # Item 2: Restaurant discount (Flat offs, Freebies, Gold, relisted orders and others)
            disc_flat_offs = get_item_discount(["flat offs"])
            if disc_flat_offs == 0.0:
                disc_flat_offs = get_item_discount(["freebies"])
            if disc_flat_offs == 0.0:
                disc_flat_offs = get_item_discount(["gold", "discount"])
            if disc_flat_offs == 0.0:
                disc_flat_offs = get_item_discount(["relisted"])
            if disc_flat_offs == 0.0:
                m_f = re.search(r"(?:Restaurant discount\s*\([^)]*(?:flat off|freebie|gold|relisted)[^)]*\)|Flat offs[^\n\r]*?discount)\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
                if m_f:
                    disc_flat_offs = abs(clean_number(m_f.group(1)))

            # Item 3: Delivery charge discount (0 if not exists)
            disc_delivery = get_item_discount(["delivery", "discount"])
            if disc_delivery == 0.0:
                m_d = re.search(r"(?:Delivery charge discount|Delivery fee discount|Delivery discount)\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
                if m_d:
                    disc_delivery = abs(clean_number(m_d.group(1)))

            total_discount = round(disc_promos + disc_flat_offs + disc_delivery, 2)
            data["discount_promos"] = disc_promos
            data["discount_flat_offs"] = disc_flat_offs
            data["discount_delivery"] = disc_delivery
            data["total_discount"] = total_discount
            print(f"[*] Discounts: Promos = ₹{disc_promos}, Flat offs/Freebies/Gold = ₹{disc_flat_offs}, Delivery = ₹{disc_delivery} -> Total Discount = ₹{total_discount}")

            # 5. Packaging Charges
            m_pack = re.search(r"(?:Packaging Charges?|Packaging Fee)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            data["packaging_charges"] = clean_number(m_pack.group(1)) if m_pack else 0.0

            # 6. Additions (B)
            m_add = re.search(r"Additions\s*(?:\(B\))?\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_add:
                data["additions"] = clean_number(m_add.group(1))

            # 7. Order level deductions (C)
            m_order_ded = re.search(r"Order level deductions?\s*(?:\(C\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_order_ded:
                data["order_level_deductions"] = clean_number(m_order_ded.group(1))

            # 8. Tax deductions (D) total & specific GST on service and payment mechanism fees @18%
            m_gst_18 = re.search(r"GST on service and payment mechanism fees\s*@\s*18%\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_gst_18:
                data["gst_fee_18"] = clean_number(m_gst_18.group(1))

            m_tax_ded = re.search(r"Tax deductions?\s*(?:\(D\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_tax_ded:
                data["tax_deductions"] = clean_number(m_tax_ded.group(1))

            # Commission = Order level deductions + GST on service and payment mechanism fees @18%
            order_ded = data.get("order_level_deductions", 0.0)
            gst_fee = data.get("gst_fee_18", 0.0)
            if order_ded and gst_fee:
                data["commission"] = round(order_ded + gst_fee, 2)
            elif order_ded and "tax_deductions" in data:
                data["commission"] = round(order_ded + data["tax_deductions"], 2)

            # 9. Investments in growth (E) / Ads
            m_ads = re.search(r"Investments? in growth\s*(?:\(E\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_ads:
                data["ads"] = clean_number(m_ads.group(1))

            # 10. Hyperpure spend (F)
            m_hyper = re.search(r"Hyperpure spend\s*(?:\(F\))?\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_hyper:
                data["hyperpure_spend"] = clean_number(m_hyper.group(1))

            # 11. Est payout / Net payout -> Cash in Bank
            m_payout = re.search(r"(?:Est\.?\s*payout|Estimated payout|Net payout|Amount Settled)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_payout:
                data["est_payout"] = clean_number(m_payout.group(1))
                data["cash_in_bank"] = clean_number(m_payout.group(1))

            # 12. Rejected orders (under payout section)
            m_rej = re.search(r"(?:Rejected orders|Rejections|Mx Rejections)\s*[:\n\r]*\s*([\d,]+)", combined_text, re.I)
            if m_rej:
                data["rejected_orders"] = clean_number(m_rej.group(1))
                data["mx_rejections"] = clean_number(m_rej.group(1))

            print("[✓] Extracted from Payout tab:", {k: v for k, v in data.items() if v is not None})

        except Exception as e:
            print(f"[!] Error in Payout tab extraction: {e}")
        finally:
            self._close_all_drawers_and_modals()

        return data

    def _select_payout_cycle_row(
        self, start_date: datetime, end_date: datetime, date_label: Optional[str]
    ):
        """Finds and clicks the target payout cycle row in Past cycles table."""
        start_day = start_date.strftime("%d")
        start_day_unpadded = start_date.strftime("%d").lstrip("0")
        end_day = end_date.strftime("%d")
        end_day_unpadded = end_date.strftime("%d").lstrip("0")
        month_abbr = start_date.strftime("%b")
        short_range = f"{start_day} {month_abbr} - {end_day} {month_abbr}"

        print(f"[*] Locating payout cycle row for: {short_range} / {start_day_unpadded} - {end_day_unpadded} {month_abbr}...")

        # Selectors matching date in table row
        cycle_selectors = [
            f"//tr[contains(., '{start_day}') and contains(., '{end_day}') and contains(., '{month_abbr}')]",
            f"//tr[contains(., '{start_day_unpadded}') and contains(., '{end_day_unpadded}') and contains(., '{month_abbr}')]",
            f"//div[contains(@class, 'row') or contains(@class, 'card') or contains(@class, 'item')][contains(., '{start_day}') and contains(., '{end_day}')]",
            f"//*[contains(text(), '{start_day} {month_abbr}') and contains(text(), '{end_day} {month_abbr}')]",
            f"//*[contains(text(), '{short_range}')]",
        ]

        row_elem = self._find_clickable(cycle_selectors, timeout_ms=2500)
        if row_elem:
            try:
                row_elem.click()
                print(f"[+] Clicked matching payout cycle row for: {short_range}")
                return
            except Exception:
                pass

        # JS evaluation across all frames to find and click the row containing the date range
        for f in [self.page.main_frame] + self.page.frames:
            try:
                clicked = f.evaluate("""({ sDay, eDay, mAbbr }) => {
                    const rows = Array.from(document.querySelectorAll('tr, [role="row"], div[class*="row"], div[class*="item"], div[class*="card"]'));
                    for (const r of rows) {
                        const txt = (r.innerText || '').toLowerCase();
                        if (txt.includes(mAbbr.toLowerCase()) && (txt.includes(sDay) || txt.includes(parseInt(sDay, 10).toString())) && (txt.includes(eDay) || txt.includes(parseInt(eDay, 10).toString()))) {
                            r.click();
                            return true;
                        }
                    }
                    return false;
                }""", {"sDay": start_day, "eDay": end_day, "mAbbr": month_abbr})
                if clicked:
                    print(f"[+] Clicked matching payout cycle row via frame evaluation for: {short_range}")
                    return
            except Exception:
                pass

        # Fallback: Click the first row in "Past cycles" table
        fallback_selectors = [
            "//div[contains(., 'Past cycles')]/following::tr[1]",
            "//table//tbody/tr[1]",
            "//div[contains(@class, 'table-body')]//div[contains(@class, 'row')][1]",
        ]
        fallback_elem = self._find_clickable(fallback_selectors, timeout_ms=2000)
        if fallback_elem:
            try:
                fallback_elem.click()
                print("[+] Clicked first available row in Past cycles table.")
            except Exception:
                pass

    def _expand_payout_drawer_accordions(self):
        """Expands collapsible chevrons inside the Payout details drawer (e.g., Net order value)."""
        print("[*] Expanding accordions in Payout side drawer (Net order value & Tax deductions)...")
        try:
            accordions = [
                "//div[contains(., 'Net order value')]/following-sibling::*[1]",
                "//*[contains(text(), 'Net order value')]/..",
                "//div[contains(., 'Tax deductions')]/following-sibling::*[1]",
                "//*[contains(text(), 'Tax deductions')]/..",
                "//button[contains(@aria-expanded, 'false')]",
                "//*[contains(@class, 'accordion')]//*[contains(@class, 'chevron')]",
                "//*[contains(text(), 'Total orders')]/..",
            ]
            for sel in accordions:
                try:
                    elems = self.page.locator(sel)
                    for i in range(min(elems.count(), 2)):
                        elems.nth(i).click(timeout=800)
                        self.page.wait_for_timeout(200)
                except Exception:
                    pass
            for f in self.page.frames:
                try:
                    f.evaluate("""() => {
                        const drawer = document.querySelector('[class*="drawer"], [class*="modal"], [class*="sheet"], [class*="sidebar"], [class*="details"]') || document.body;
                        const clickables = Array.from(drawer.querySelectorAll('svg, button, [role="button"], [class*="chevron"], [class*="arrow"], [class*="accordion"], [aria-expanded="false"], i'));
                        for (const el of clickables) {
                            try { el.click(); } catch(e) {}
                        }
                    }""")
                except Exception:
                    pass
        except Exception:
            pass
        self.page.wait_for_timeout(1000)

    def extract_restaurant_info(self) -> Dict[str, str]:
        """Extracts restaurant name and ID if displayed."""
        info = {}
        try:
            for f in [self.page.main_frame] + self.page.frames:
                page_text = f.evaluate("() => document.body ? document.body.innerText : ''")
                m_id = re.search(r"(?:Id|Res Id|Restaurant ID)\s*[:#]?\s*(\d{6,10})", page_text, re.I)
                if m_id:
                    info["restaurant_id"] = m_id.group(1)
                    break

            res_elem = self._find_clickable([
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
        self, start_date: datetime, end_date: datetime, date_label: Optional[str] = None, restaurant_name: Optional[str] = None, restaurant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes complete sequential extraction from:
        1. Reporting Tab (Business Reports matrix table)
        2. Payout Tab (Finance -> Payout details side drawer)
        """
        reporting_data = self.navigate_and_extract_reporting_tab(start_date, end_date, date_label, restaurant_name, restaurant_id)
        payout_data = self.navigate_and_extract_payout_tab(start_date, end_date, date_label, restaurant_name, restaurant_id)
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
