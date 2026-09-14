from typing import Optional, Tuple
from playwright.sync_api import Page
from config import DEFAULT_RESTAURANT_NAME, DEFAULT_RESTAURANT_ID
from scrapers.zomato.base import BaseZomatoScraper


class OutletSelector(BaseZomatoScraper):
    """
    Handles outlet (restaurant) selection across:
    1. Reporting page: 'All outlets' filter modal ('#modal')
    2. Payouts page: 'Show data for' dialog ('div[role="dialog"]' / '.z-10.max-h-[720px]')
    Matches by Restaurant ID (e.g. 22317789 / 21735067) or Name (e.g. Biryani Lovers).
    """

    def __init__(self, page: Optional[Page] = None):
        super().__init__(page)
        self.extracted_restaurant_name: Optional[str] = None
        self.extracted_restaurant_id: Optional[str] = None

    def select_outlet(self, restaurant_name_or_id: Optional[str] = None) -> bool:
        """
        Selects the specific restaurant outlet from Reporting Filter modal or Payouts dialog.
        """
        if not self.page:
            return False

        target = (str(restaurant_name_or_id).strip() if restaurant_name_or_id else DEFAULT_RESTAURANT_ID).lower()
        target_name = (str(restaurant_name_or_id).strip() if restaurant_name_or_id else DEFAULT_RESTAURANT_NAME).lower()
        display_target = restaurant_name_or_id or f"{DEFAULT_RESTAURANT_NAME} ({DEFAULT_RESTAURANT_ID})"
        print(f"[*] Selecting restaurant outlet for target: '{display_target}'...")

        try:
            # Check if modal/dialog is already open
            modal_already_open = False
            payout_dialog = self.find_clickable([
                "//div[@role='dialog']",
                "//div[contains(@class, 'max-h-[720px]')]",
                "//*[text()='Show data for']/ancestor::div[@role='dialog' or contains(@class, 'z-50') or contains(@class, 'z-10')]",
            ], timeout_ms=1000)

            reporting_modal = self.find_clickable([
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

                outlet_btn = self.find_clickable(outlet_btn_selectors, timeout_ms=2500)
                if not outlet_btn:
                    outlet_btn = self.find_clickable([
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
                        name, res_id = self.parse_outlet_label(btn_text)
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
            payout_dialog = self.find_clickable([
                "//div[@role='dialog']",
                "//div[contains(@class, 'max-h-[720px]')]",
                "//*[text()='Show data for']/ancestor::section",
            ], timeout_ms=1500)

            if payout_dialog:
                print("[*] Detected Payouts 'Show data for' dialog.")

                # Ensure 'Restaurant' tab is active
                res_tab = self.find_clickable([
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
                search_box = self.find_clickable([
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
                payout_item = self.find_clickable(payout_item_selectors, timeout_ms=2000)
                if payout_item:
                    try:
                        payout_text = payout_item.inner_text().strip()
                        payout_item.click()
                        print(f"[+] Clicked outlet radio option: '{payout_text or target}'")
                        name, res_id = self.parse_outlet_label(payout_text)
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
                        name, res_id = self.parse_outlet_label(clicked_payout_text)
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
                apply_btn = self.find_clickable(apply_payout_selectors, timeout_ms=2500)
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
            outlet_tab_selectors = [
                "//div[@id='modal']//div[contains(@class, 'css-12zjku')]//span[text()='Outlet']",
                "//div[@id='modal']//span[normalize-space()='Outlet']",
                "//div[@id='modal']//*[normalize-space()='Outlet' and not(contains(., 'Subzone'))]",
                "//span[text()='Outlet']",
            ]
            outlet_tab = self.find_clickable(outlet_tab_selectors, timeout_ms=2000)
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

            # Clear previous selections if 'Clear all' is present in modal
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
            search_box = self.find_clickable([
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

            target_elem = self.find_clickable(item_selectors, timeout_ms=2500)
            if target_elem:
                try:
                    elem_text = target_elem.inner_text().strip()
                    target_elem.click()
                    print(f"[+] Clicked matching outlet option: '{elem_text}'")
                    name, res_id = self.parse_outlet_label(elem_text)
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
                    name, res_id = self.parse_outlet_label(clicked_js)
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
            apply_btn = self.find_clickable(apply_btn_selectors, timeout_ms=2500)
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
