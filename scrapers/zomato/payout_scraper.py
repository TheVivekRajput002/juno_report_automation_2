from datetime import datetime
from typing import Dict, Any, Optional
from playwright.sync_api import Page
from config import ZOMATO_FINANCE_URL
from scrapers.zomato.base import BaseZomatoScraper
from scrapers.zomato.outlet_selector import OutletSelector
from scrapers.zomato.payout_parser import PayoutParser


class PayoutScraper(BaseZomatoScraper):
    """
    Automates data extraction from Zomato Partner Portal -> Finance -> Payouts tab.
    Extracts financial settlement breakdown from the weekly payout details side drawer.
    """

    def __init__(self, page: Optional[Page] = None, outlet_selector: Optional[OutletSelector] = None):
        super().__init__(page)
        self.outlet_selector = outlet_selector or OutletSelector(page)
        self.parser = PayoutParser()

    def select_payout_cycle_row(
        self, start_date: datetime, end_date: datetime, date_label: Optional[str] = None
    ):
        """Finds and clicks the target payout cycle row in Past cycles table."""
        if not self.page:
            return

        start_day = start_date.strftime("%d")
        start_day_unpadded = start_date.strftime("%d").lstrip("0")
        end_day = end_date.strftime("%d")
        end_day_unpadded = end_date.strftime("%d").lstrip("0")
        s_month = start_date.strftime("%b")
        e_month = end_date.strftime("%b")

        if s_month != e_month:
            display_range = f"{start_day_unpadded} {s_month} - {end_day_unpadded} {e_month}"
        else:
            display_range = f"{start_day_unpadded} - {end_day_unpadded} {s_month}"

        print(f"[*] Locating payout cycle row for: {display_range}...")

        cycle_selectors = [
            f"//tr[contains(., '{start_day}') and contains(., '{end_day}') and (contains(., '{s_month}') or contains(., '{e_month}'))]",
            f"//tr[contains(., '{start_day_unpadded}') and contains(., '{end_day_unpadded}') and (contains(., '{s_month}') or contains(., '{e_month}'))]",
            f"//div[contains(@class, 'row') or contains(@class, 'card') or contains(@class, 'item')][contains(., '{start_day_unpadded}') and contains(., '{end_day_unpadded}')]",
            f"//*[contains(text(), '{start_day_unpadded} {s_month}') and contains(text(), '{end_day_unpadded} {e_month}')]",
            f"//*[contains(text(), '{display_range}')]",
        ]

        row_elem = self.find_clickable(cycle_selectors, timeout_ms=2500)
        if row_elem:
            try:
                row_elem.click()
                print(f"[+] Clicked matching payout cycle row for: {display_range}")
                return
            except Exception:
                pass

        for f in [self.page.main_frame] + self.page.frames:
            try:
                clicked = f.evaluate("""({ sDay, eDay, sM, eM }) => {
                    const rows = Array.from(document.querySelectorAll('tr, [role="row"], div[class*="row"], div[class*="item"], div[class*="card"]'));
                    for (const r of rows) {
                        const txt = (r.innerText || '').toLowerCase();
                        const hasMonth = txt.includes(sM.toLowerCase()) || txt.includes(eM.toLowerCase());
                        const hasStart = txt.includes(sDay) || (new RegExp('\\\\b0?' + sDay + '\\\\b')).test(txt);
                        const hasEnd = txt.includes(eDay) || (new RegExp('\\\\b0?' + eDay + '\\\\b')).test(txt);
                        if (hasMonth && hasStart && hasEnd) {
                            r.click();
                            return true;
                        }
                    }
                    return false;
                }""", {"sDay": start_day_unpadded, "eDay": end_day_unpadded, "sM": s_month, "eM": e_month})
                if clicked:
                    print(f"[+] Clicked matching payout cycle row via frame evaluation for: {display_range}")
                    return
            except Exception:
                pass

        fallback_selectors = [
            "//div[contains(., 'Past cycles')]/following::tr[1]",
            "//table//tbody/tr[1]",
            "//div[contains(@class, 'table-body')]//div[contains(@class, 'row')][1]",
        ]
        fallback_elem = self.find_clickable(fallback_selectors, timeout_ms=2000)
        if fallback_elem:
            try:
                fallback_elem.click()
                print("[+] Clicked first available row in Past cycles table.")
            except Exception:
                pass

    def expand_drawer_accordions(self):
        """Expands collapsible chevrons inside the Payout details drawer (e.g., Net order value, Tax deductions)."""
        if not self.page:
            return
        print("[*] Expanding accordions in Payout side drawer (Net order value, Tax deductions, Deductions)...")
        try:
            for f in self.page.frames:
                try:
                    f.evaluate("""() => {
                        const drawer = document.querySelector('[class*="drawer"], [class*="modal"], [class*="sheet"], [class*="sidebar"], [role="dialog"], [class*="details"]') || document.body;
                        
                        // Click closed aria-expanded toggles
                        const ariaClosed = Array.from(drawer.querySelectorAll('[aria-expanded="false"]'));
                        for (const el of ariaClosed) {
                            try { el.click(); } catch(e) {}
                        }

                        // Target specific section containers / headers if item subtotal is not yet visible
                        const text = drawer.innerText || '';
                        if (!text.toLowerCase().includes('item subtotal')) {
                            const sectionElements = Array.from(drawer.querySelectorAll('div, button, span, p')).filter(el => {
                                const t = (el.innerText || '').trim();
                                return (t.startsWith('Net order value') || t.startsWith('Tax deductions') || t.startsWith('Order level') || t.startsWith('Additions')) && el.children.length < 4;
                            });
                            for (const el of sectionElements) {
                                try { el.click(); } catch(e) {}
                            }
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
        Navigates to Finance -> Payouts, selects restaurant,
        finds and clicks target cycle row, expands drawer, and extracts settlement metrics.
        """
        data: Dict[str, Any] = {}
        if not self.page:
            return data

        print("\n" + "-" * 50)
        print("[2] Navigating to PAYOUT tab (under Finance)...")
        print("-" * 50)

        try:
            self.close_all_drawers_and_modals()

            current_url = self.page.url.lower()
            if "payouts" not in current_url:
                print(f"[*] Navigating directly to Payouts URL: {ZOMATO_FINANCE_URL}")
                self.page.goto(ZOMATO_FINANCE_URL, wait_until="domcontentloaded", timeout=30000)
                self.page.wait_for_timeout(3000)

            self.outlet_selector.select_outlet(restaurant_id or restaurant_name)
            self.page.wait_for_timeout(2000)

            self.select_payout_cycle_row(start_date, end_date, date_label)
            self.page.wait_for_timeout(3000)

            self.expand_drawer_accordions()
            self.page.wait_for_timeout(1500)

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

            parsed = self.parser.parse_payout_text(drawer_text, all_text)
            data.update(parsed)

            print("[✓] Extracted from Payout tab:", {k: v for k, v in data.items() if v is not None})

        except Exception as e:
            print(f"[!] Error in Payout tab extraction: {e}")
        finally:
            self.close_all_drawers_and_modals()

        return data
