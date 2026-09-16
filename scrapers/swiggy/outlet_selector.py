import re
from typing import Optional, Tuple, List
from playwright.sync_api import Page
from config import DEFAULT_RESTAURANT_NAME, DEFAULT_SWIGGY_ID
from scrapers.swiggy.base import BaseSwiggyScraper
from scrapers.swiggy.network_capture import SwiggyNetworkCapture


class SwiggyOutletSelector(BaseSwiggyScraper):
    """
    Handles outlet selection across Swiggy Partner Portal:
    1. Top-Left Global Outlet Selector Dropdown (for Finance / Payouts).
    2. Business Reports Filter Modal ("Filter by outlets" -> unselect all -> search ID -> select target -> Apply).
    """

    def __init__(self, page: Optional[Page] = None, network_capture: Optional[SwiggyNetworkCapture] = None):
        super().__init__(page, network_capture=network_capture)
        self.extracted_restaurant_name: Optional[str] = None
        self.extracted_restaurant_id: Optional[str] = None

    @staticmethod
    def get_search_terms(restaurant_name_or_id: Optional[str] = None, restaurant_name: Optional[str] = None) -> Tuple[str, str, List[str]]:
        """
        Extracts target ID, clean primary name, and keyword tokens for robust matching.
        Example:
        - ('1234511', 'Kasra Biryani-E-Hind') -> ('1234511', 'Kasra Biryani', ['kasra', 'biryani'])
        - ('261628', 'Yaaran Da Adda, Tatibandh, Raipur') -> ('261628', 'Yaaran Da Adda', ['yaaran', 'da', 'adda'])
        """
        target_id = ""
        raw_name = ""

        if restaurant_name_or_id:
            s = str(restaurant_name_or_id).strip()
            if s.isdigit():
                target_id = s
            else:
                raw_name = s

        if restaurant_name:
            raw_name = str(restaurant_name).strip()

        if not target_id:
            target_id = DEFAULT_SWIGGY_ID
        if not raw_name:
            raw_name = DEFAULT_RESTAURANT_NAME

        # Clean primary name: remove suffixes like ", Raipur", "-E-Hind", "(ID: ...)"
        clean = re.sub(r"\(.*?\)", "", raw_name)
        clean = clean.split(",")[0].strip()
        clean = re.sub(r"\s*[-–—]\s*(?:e\s*[-–—]?\s*hind|raipur|nagpur|shankar\s*nagar|tatibandh|civil\s*lines|mowa|lakadganj).*$", "", clean, flags=re.I).strip()
        clean = re.sub(r"\s*[-–—]\s*\d+.*$", "", clean).strip()
        if not clean:
            clean = raw_name.split(",")[0].strip()

        # Tokenize significant words
        words = re.findall(r"\b[A-Za-z0-9]+\b", clean.lower())
        stopwords = {"the", "and", "of", "in", "at", "for", "by", "pure", "veg", "non", "restaurant", "hotel"}
        keywords = [w for w in words if w not in stopwords]
        if not keywords:
            keywords = words

        return target_id.lower(), clean, keywords

    def select_global_outlet(self, restaurant_name_or_id: Optional[str] = None, restaurant_name: Optional[str] = None) -> bool:
        """
        Selects target outlet from the top-left dropdown in Swiggy Partner portal (Finance/Payouts page).
        Finds the top-left header element (showing restaurant name, ID & chevron), opens dropdown,
        searches the target outlet ID/name, and clicks the matching outlet.
        """
        if not self.page:
            return False

        target_id, clean_name, keywords = self.get_search_terms(restaurant_name_or_id, restaurant_name)
        display_target = f"{clean_name} (ID: {target_id})"
        print(f"[*] Selecting Swiggy outlet from top-left corner for: '{display_target}'...")

        try:
            # 1. Inspect current top-left outlet header
            is_already_active = False
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    current_header = f.evaluate("""() => {
                        const candidates = Array.from(document.querySelectorAll('header, nav, [class*="header"], [class*="topbar"], div[class*="Header"], div[class*="top-nav"]'));
                        for (const h of candidates) {
                            const clickables = Array.from(h.querySelectorAll('div[class*="cursor-pointer"], div[role="button"], button, div[class*="outlet"], div[class*="select"], div[class*="restaurant"]'));
                            for (const c of clickables) {
                                const txt = (c.innerText || '').trim();
                                if (txt.length > 2 && (c.querySelector('svg') || txt.includes('(') || txt.includes('\\n'))) {
                                    return txt;
                                }
                            }
                        }
                        const allDivs = Array.from(document.querySelectorAll('div, button'));
                        for (const d of allDivs) {
                            const rect = d.getBoundingClientRect();
                            if (rect.top >= 0 && rect.top < 120 && rect.left >= 0 && rect.left < 450 && rect.width > 50 && rect.height > 20) {
                                const txt = (d.innerText || '').trim();
                                if (txt.length > 3 && (d.querySelector('svg') || txt.includes('('))) {
                                    return txt;
                                }
                            }
                        }
                        return null;
                    }""")

                    if current_header:
                        c_low = current_header.lower()
                        match = (
                            (target_id and target_id in c_low) or
                            (clean_name and clean_name.lower() in c_low) or
                            (keywords and len(keywords) >= 2 and all(k in c_low for k in keywords[:2]))
                        )
                        if match and "all outlet" not in c_low:
                            print(f"[+] Swiggy outlet '{current_header.replace(chr(10), ' ')}' is already active in top-left corner.")
                            name, res_id = self.parse_outlet_label(current_header)
                            if name:
                                self.extracted_restaurant_name = name
                            if res_id:
                                self.extracted_restaurant_id = res_id
                            return True
                except Exception:
                    pass

            # 2. Open the top-left outlet selector dropdown by clicking the header element / chevron
            dropdown_opened = False

            # Try Playwright mouse click on the top-left element bounding box
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    rect = f.evaluate("""() => {
                        function isOutletTrigger(el) {
                            const txt = (el.innerText || '').trim();
                            if (txt.length < 5 || txt.length > 120) return false;
                            const hasId = /\\(\\d{4,10}\\)/.test(txt) || /\\bID:?\\s*\\d{4,10}/i.test(txt);
                            if (!hasId) return false;
                            const tLow = txt.toLowerCase();
                            const navWords = ['orders', 'growth', 'buddy', 'complaints', 'ratings', 'reports', 'finance', 'help', 'manage outlets', 'profile', 'menu'];
                            const navHits = navWords.filter(w => tLow.includes(w)).length;
                            if (navHits >= 2) return false;
                            return true;
                        }
                        const allDivs = Array.from(document.querySelectorAll(
                            '[data-testid*="outlet"], [class*="outlet-selector"], header div, nav div, div[role="button"], button'
                        ));
                        for (const d of allDivs) {
                            const r = d.getBoundingClientRect();
                            if (r.top >= 0 && r.top < 120 && r.left >= 0 && r.left < 450 && r.width > 40 && r.height > 18) {
                                const txt = (d.innerText || '').trim();
                                if (isOutletTrigger(d)) {
                                    return { x: r.left + r.width / 2, y: r.top + r.height / 2, text: txt };
                                }
                            }
                        }
                        return null;
                    }""")
                    if rect:
                        print(f"[*] Clicking top-left outlet dropdown trigger at ({rect['x']:.0f}, {rect['y']:.0f}): '{rect.get('text', '').replace(chr(10), ' ')}'")
                        self.page.mouse.click(rect["x"], rect["y"])
                        self.page.wait_for_timeout(1000)
                        dropdown_opened = True
                        break
                except Exception:
                    pass

            if not dropdown_opened:
                # Playwright selector fallbacks
                trigger_selectors = [
                    "//header//div[contains(@class, 'cursor-pointer')]",
                    "//header//div[contains(., '(') and contains(., ')')]",
                    "//div[contains(@class, 'topbar') or contains(@class, 'header')]//div[contains(@class, 'cursor-pointer')]",
                    "//header//button",
                    "[data-testid*='outlet-selector']",
                    "[data-testid*='outlet-dropdown']",
                ]
                trigger_btn = self.find_clickable(trigger_selectors, timeout_ms=2000)
                if trigger_btn:
                    trigger_btn.click()
                    print("[+] Clicked top-left outlet selector via Playwright locator.")
                    self.page.wait_for_timeout(1000)
                    dropdown_opened = True

            # 3. Search and select the target outlet in the opened dropdown
            search_input = self.find_clickable([
                "//div[@role='dialog' or contains(@class, 'modal') or contains(@class, 'dropdown') or contains(@class, 'popover') or contains(@class, 'menu')]//input",
                "//input[@placeholder='Search' or contains(@placeholder, 'Search') or contains(@placeholder, 'outlet') or contains(@placeholder, 'restaurant')]",
                "input[placeholder*='Search']",
                "input[type='text']",
            ], timeout_ms=2000)

            queries_to_try = []
            if target_id:
                queries_to_try.append(target_id)
            if clean_name and clean_name != target_id:
                queries_to_try.append(clean_name)
            if keywords and keywords[0] != clean_name.lower():
                queries_to_try.append(keywords[0])

            selected_option = None

            js_find_and_click_option = """({ tgtId, cleanNm, kwList }) => {
                const candidates = Array.from(document.querySelectorAll('li, div[role="option"], div[role="menuitem"], div[class*="item"], div[class*="row"], div[class*="outlet"], div[class*="option"], label'));

                function isMatch(txt) {
                    if (!txt) return false;
                    const t = txt.toLowerCase();
                    if (t.includes('all outlet') || t.length > 200 || t.length < 3) return false;
                    if (tgtId && tgtId.length >= 4 && (t.includes(tgtId) || t.includes('(' + tgtId + ')') || t.includes('id: ' + tgtId) || t.includes('rid: ' + tgtId))) return true;
                    if (cleanNm && t.includes(cleanNm.toLowerCase())) return true;
                    if (kwList && kwList.length >= 2 && kwList.slice(0, 2).every(k => t.includes(k))) return true;
                    if (kwList && kwList.length === 1 && kwList[0].length >= 4 && t.includes(kwList[0])) return true;
                    return false;
                }

                for (const el of candidates) {
                    const txt = (el.innerText || '').trim();
                    if (isMatch(txt)) {
                        const r = el.getBoundingClientRect();
                        el.click();
                        return { text: txt, x: r.left + r.width / 2, y: r.top + r.height / 2 };
                    }
                }
                return null;
            }"""

            for q in queries_to_try:
                print(f"[*] Searching top-left dropdown for '{q}'...")
                if search_input:
                    try:
                        search_input.fill("")
                        self.page.wait_for_timeout(200)
                        search_input.fill(q)
                        self.page.wait_for_timeout(800)
                    except Exception:
                        pass
                else:
                    for f in [self.page.main_frame] + self.page.frames:
                        try:
                            f.evaluate("""(val) => {
                                const inps = Array.from(document.querySelectorAll('input[type="text"], input[placeholder*="Search"]'));
                                for (const inp of inps) {
                                    inp.value = val;
                                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }""", q)
                        except Exception:
                            pass
                    self.page.wait_for_timeout(800)

                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        res = f.evaluate(js_find_and_click_option, {"tgtId": target_id, "cleanNm": clean_name, "kwList": keywords})
                        if res:
                            selected_option = res.get("text")
                            if res.get("x") and res.get("y"):
                                self.page.mouse.click(res["x"], res["y"])
                            print(f"[+] Selected outlet from top-left dropdown: '{selected_option.replace(chr(10), ' | ')}'")
                            name, res_id = self.parse_outlet_label(selected_option)
                            if name:
                                self.extracted_restaurant_name = name
                            if res_id:
                                self.extracted_restaurant_id = res_id
                            self.page.wait_for_timeout(3000)
                            return True
                    except Exception:
                        pass

                if selected_option:
                    break

            # Fallback: scan without search filter if search didn't match
            if not selected_option:
                print("[*] Fallback: Clearing dropdown search to scan all outlets in list...")
                if search_input:
                    search_input.fill("")
                    self.page.wait_for_timeout(500)

                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        res = f.evaluate(js_find_and_click_option, {"tgtId": target_id, "cleanNm": clean_name, "kwList": keywords})
                        if res:
                            selected_option = res.get("text")
                            if res.get("x") and res.get("y"):
                                self.page.mouse.click(res["x"], res["y"])
                            print(f"[+] Selected outlet from full dropdown list: '{selected_option.replace(chr(10), ' | ')}'")
                            name, res_id = self.parse_outlet_label(selected_option)
                            if name:
                                self.extracted_restaurant_name = name
                            if res_id:
                                self.extracted_restaurant_id = res_id
                            self.page.wait_for_timeout(3000)
                            return True
                    except Exception:
                        pass

            if selected_option:
                return True

            print(f"[!] Warning: Could not find matching outlet for '{display_target}' in top-left dropdown.")
            return False
        except Exception as e:
            print(f"[!] Warning in top-left Swiggy outlet selection: {e}")
            return False

    def select_outlet_in_filter_modal(self, restaurant_name_or_id: Optional[str] = None, restaurant_name: Optional[str] = None) -> bool:
        """
        Handles Swiggy Business Reports Filter modal (exact step-by-step requested by user):
        1. Opens Filter modal on Reports page.
        2. Clicks 'Filter by outlets' tab on the left sidebar.
        3. FIRST unselects all outlets (clicks 'Clear all' and ensures 'Select All' checkbox is unchecked).
        4. Searches the target outlet ID (or clean name) in the Search box.
        5. Selects ONLY the target outlet checkbox from the filtered list.
        6. Clicks the orange 'Apply' button.
        """
        if not self.page:
            return False

        target_id, clean_name, keywords = self.get_search_terms(restaurant_name_or_id, restaurant_name)
        display_target = f"{clean_name} (ID: {target_id})"
        print(f"[*] Configuring Business Reports Filter Modal for: '{display_target}'...")

        try:
            # 1. Check if Filter Modal is already open; if not, open it
            is_modal_open = False
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    is_modal_open = f.evaluate("() => Boolean(document.querySelector('[role=\"dialog\"], [class*=\"modal\"], [class*=\"drawer\"], [data-testid*=\"filter-modal\"], [class*=\"FilterDrawer\"], [class*=\"filter-modal\"]'))")
                    if is_modal_open:
                        break
                except Exception:
                    pass

            if not is_modal_open:
                filter_btn_selectors = [
                    "//button[contains(., 'Filter') or contains(., 'Outlets')]",
                    "//div[@role='button'][contains(., 'Filter') or contains(., 'Outlets')]",
                    "[data-testid*='filter']",
                    "//button[contains(@class, 'filter') or contains(@class, 'Filter')]",
                    "//*[text()='Filter' or text()='Filters' or contains(text(), 'Outlets')]",
                    "//span[contains(text(), 'Filter')]",
                ]
                filter_btn = self.find_clickable(filter_btn_selectors, timeout_ms=2000)
                if filter_btn:
                    filter_btn.click()
                    print("[+] Clicked Filter button to open modal.")
                    self.page.wait_for_timeout(1500)
                else:
                    for f in [self.page.main_frame] + self.page.frames:
                        try:
                            f.evaluate("""() => {
                                const btns = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                                for (const b of btns) {
                                    const txt = (b.innerText || '').trim().toLowerCase();
                                    if (txt === 'filter' || txt === 'filters' || txt.includes('outlets')) {
                                        b.click();
                                        return true;
                                    }
                                }
                                return false;
                            }""")
                            self.page.wait_for_timeout(1500)
                            break
                        except Exception:
                            pass

            # 2. Click 'Filter by outlets' tab on the left sidebar
            outlet_tab_selectors = [
                "//div[normalize-space()='Filter by outlets']",
                "//span[normalize-space()='Filter by outlets']",
                "//button[contains(., 'Filter by outlets') or contains(., 'Outlets')][not(contains(., 'Brand'))]",
                "//div[@role='tab'][contains(., 'Filter by outlets') or contains(., 'Outlets')][not(contains(., 'Brand'))]",
                "//*[text()='Filter by outlets']",
            ]
            outlet_tab = self.find_clickable(outlet_tab_selectors, timeout_ms=2000)
            if outlet_tab:
                outlet_tab.click()
                print("[+] Selected 'Filter by outlets' tab on left sidebar.")
                self.page.wait_for_timeout(800)
            else:
                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        f.evaluate("""() => {
                            const tabs = Array.from(document.querySelectorAll('button, div, span, label, [role="tab"]'));
                            for (const t of tabs) {
                                const txt = (t.innerText || '').trim().toLowerCase();
                                if (txt === 'filter by outlets' || txt === 'outlets') {
                                    t.click();
                                    return true;
                                }
                            }
                            return false;
                        }""")
                    except Exception:
                        pass
                self.page.wait_for_timeout(800)

            # 3. STEP 1: FIRST UNSELECT ALL OUTLETS
            print("[*] Step 1: Unselecting all outlets in 'Filter by outlets' tab...")

            # 3a. Click 'Clear all' button (orange text button at bottom left)
            clear_clicked = False
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    res = f.evaluate("""() => {
                        const dialog = document.querySelector('[role="dialog"], [class*="modal"], [class*="drawer"]') || document.body;
                        const clickables = Array.from(dialog.querySelectorAll('span, button, a, div[role="button"]'));
                        for (const el of clickables) {
                            const txt = (el.innerText || '').trim().toLowerCase();
                            if (txt === 'clear all' || txt === 'clear filters' || txt === 'deselect all' || txt === 'reset') {
                                el.click();
                                return txt;
                            }
                        }
                        return null;
                    }""")
                    if res:
                        print(f"[+] Clicked '{res}' button to unselect all.")
                        clear_clicked = True
                        self.page.wait_for_timeout(500)
                        break
                except Exception:
                    pass

            # 3b. Deselect 'Select All' checkbox if still checked
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    f.evaluate("""() => {
                        const dialog = document.querySelector('[role="dialog"], [class*="modal"], [class*="drawer"]') || document.body;
                        const allBoxes = Array.from(dialog.querySelectorAll('input[type="checkbox"], [role="checkbox"], [class*="checkbox"], [class*="Checkbox"]'));
                        for (const b of allBoxes) {
                            const p = b.closest('label, tr, li, div[class*="row"], div[class*="item"], div') || b;
                            const pTxt = (p.innerText || '').toLowerCase();
                            if (pTxt.includes('select all') || pTxt.includes('all outlet')) {
                                const isChecked = b.checked || b.getAttribute('aria-checked') === 'true' ||
                                                  b.className.includes('checked') ||
                                                  p.querySelector('svg[class*="check"], svg[class*="tick"], [data-testid*="check"]') !== null;
                                if (isChecked) {
                                    b.click();
                                }
                            }
                        }
                    }""")
                except Exception:
                    pass
            self.page.wait_for_timeout(400)

            # 4. STEP 2: SEARCH THE TARGET OUTLET ID IN SEARCH BOX
            print(f"[*] Step 2: Searching target Swiggy Outlet ID '{target_id}' in filter search box...")

            search_input = self.find_clickable([
                "//div[@role='dialog' or contains(@class, 'modal') or contains(@class, 'drawer')]//input[@placeholder='Search' or contains(@placeholder, 'Search') or @type='text']",
                "//input[@placeholder='Search']",
                "input[placeholder*='Search']",
                "input[type='text']",
            ], timeout_ms=2000)

            search_success = False
            searches_to_attempt = []
            if target_id:
                searches_to_attempt.append(("ID", target_id))
            if clean_name and clean_name != target_id:
                searches_to_attempt.append(("Name", clean_name))
            if keywords and keywords[0] != clean_name.lower():
                searches_to_attempt.append(("Keyword", keywords[0]))

            selected_target_text = None

            for search_type, search_query in searches_to_attempt:
                print(f"[*] Typing search query ({search_type}): '{search_query}'...")
                if search_input:
                    try:
                        search_input.fill("")
                        self.page.wait_for_timeout(200)
                        search_input.fill(search_query)
                        self.page.wait_for_timeout(800)
                    except Exception:
                        pass
                else:
                    for f in [self.page.main_frame] + self.page.frames:
                        try:
                            f.evaluate("""(q) => {
                                const inp = document.querySelector('input[placeholder*="Search"], input[type="text"]');
                                if (inp) {
                                    inp.value = q;
                                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }""", search_query)
                        except Exception:
                            pass
                    self.page.wait_for_timeout(800)

                # 5. STEP 3: SELECT THE TARGET OUTLET CHECKBOX IN FILTERED LIST
                js_check_target = """({ tgtId, cleanNm, kwList }) => {
                    const dialog = document.querySelector('[role="dialog"], [class*="modal"], [class*="drawer"]') || document.body;
                    const rows = Array.from(dialog.querySelectorAll('li, tr, div[class*="row"], div[class*="item"], div[class*="outlet"], label'));

                    function isMatch(txt) {
                        if (!txt) return false;
                        const t = txt.toLowerCase();
                        if (tgtId && tgtId.length >= 4 && (t.includes(tgtId) || t.includes('rid: ' + tgtId) || t.includes('rid:' + tgtId))) return true;
                        if (cleanNm && t.includes(cleanNm.toLowerCase())) return true;
                        if (kwList && kwList.length >= 2 && kwList.slice(0, 2).every(k => t.includes(k))) return true;
                        return false;
                    }

                    for (const r of rows) {
                        const txt = (r.innerText || '').toLowerCase();
                        if (txt.includes('apply') || txt.includes('clear') || txt === 'brand' || txt === 'outlet' || txt.includes('select all')) continue;

                        if (isMatch(txt)) {
                            const chk = r.querySelector('input[type="checkbox"], input[type="radio"], [role="checkbox"], [class*="checkbox"], [class*="Checkbox"]') || (r.tagName === 'INPUT' ? r : r);
                            const isChecked = (chk && chk.checked) || (chk && chk.getAttribute('aria-checked') === 'true') ||
                                              (chk && chk.className && chk.className.includes('checked')) ||
                                              (r.className && r.className.includes('checked')) ||
                                              r.querySelector('svg[class*="check"], svg[class*="tick"], [data-testid*="check"]') !== null;
                            if (!isChecked && chk) {
                                chk.click();
                            }
                            return r.innerText.trim();
                        }
                    }
                    return null;
                }"""

                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        res = f.evaluate(js_check_target, {"tgtId": target_id, "cleanNm": clean_name, "kwList": keywords})
                        if res:
                            selected_target_text = res
                            print(f"[+] Step 3: Checked target outlet checkbox: '{selected_target_text.replace(chr(10), ' | ')}'")
                            name, res_id = self.parse_outlet_label(selected_target_text)
                            if name:
                                self.extracted_restaurant_name = name
                            if res_id:
                                self.extracted_restaurant_id = res_id
                            search_success = True
                            self.page.wait_for_timeout(600)
                            break
                    except Exception:
                        pass

                if search_success:
                    break

            # 6. Fallback if search failed: clear search to show all 38 outlets, scroll & check target
            if not selected_target_text:
                print("[*] Fallback: Clearing search to scan full outlet list directly...")
                if search_input:
                    search_input.fill("")
                    self.page.wait_for_timeout(500)

                for f in [self.page.main_frame] + self.page.frames:
                    try:
                        res = f.evaluate(js_check_target, {"tgtId": target_id, "cleanNm": clean_name, "kwList": keywords})
                        if res:
                            selected_target_text = res
                            print(f"[+] Checked target outlet from full list: '{selected_target_text.replace(chr(10), ' | ')}'")
                            break
                    except Exception:
                        pass

            # 7. STEP 4: CLICK APPLY BUTTON
            print("[*] Step 4: Clicking Apply button in Filter modal...")
            apply_selectors = [
                "//button[normalize-space()='Apply' or contains(., 'Apply')]",
                "//button[normalize-space()='Save' or contains(., 'Save')]",
                "//div[@role='dialog']//button[contains(@class, 'primary') or contains(@class, 'apply') or contains(., 'Apply')]",
                "//*[text()='Apply']/ancestor-or-self::button",
            ]
            apply_btn = self.find_clickable(apply_selectors, timeout_ms=2500)
            if apply_btn:
                apply_btn.click()
                print("[+] Clicked orange 'Apply' button in Filter modal.")
                self.page.wait_for_timeout(3000)
                return True

            for f in [self.page.main_frame] + self.page.frames:
                try:
                    clicked = f.evaluate("""() => {
                        const dialog = document.querySelector('[role="dialog"], [class*="modal"], [class*="drawer"]') || document.body;
                        const btns = Array.from(dialog.querySelectorAll('button, div[role="button"]'));
                        for (const b of btns) {
                            const txt = (b.innerText || '').trim().toLowerCase();
                            if (txt === 'apply') {
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if clicked:
                        print("[+] Clicked 'Apply' via frame evaluation.")
                        self.page.wait_for_timeout(3000)
                        return True
                except Exception:
                    pass

            return True
        except Exception as e:
            print(f"[!] Warning in Filter modal outlet selection: {e}")
            return False
