import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page
from config import ZOMATO_REPORTS_URL
from processors.metric_calculator import clean_number
from scrapers.zomato.base import BaseZomatoScraper
from scrapers.zomato.outlet_selector import OutletSelector
from scrapers.zomato.reporting_parser import ReportingParser


class ReportingScraper(BaseZomatoScraper):
    """
    Automates data extraction from Zomato Partner Portal -> Reporting -> Business Reports tab.
    Extracts funnel and operational metrics (Impressions, I2M, M2O, C2O, KPT, Online %, Rejections, Orders, Sales).
    """

    def __init__(self, page: Optional[Page] = None, outlet_selector: Optional[OutletSelector] = None):
        super().__init__(page)
        self.outlet_selector = outlet_selector or OutletSelector(page)
        self.parser = ReportingParser()

    def select_weekly_view(self) -> bool:
        """Ensures the Weekly view / granularity is selected in Business reports."""
        if not self.page:
            return False
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
        weekly_btn = self.find_clickable(weekly_selectors, timeout_ms=2500)
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
                    opt = self.find_clickable(["//div[@role='option'][contains(., 'Weekly')]", "//li[contains(., 'Weekly')]"], timeout_ms=1500)
                    if opt:
                        opt.click()
                        print("[+] Selected 'Weekly' from view dropdown.")
                        self.page.wait_for_timeout(2500)
                        return True
            except Exception as e:
                print(f"[!] Notice selecting 'Weekly': {e}")

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

    def scroll_to_reveal_columns(self):
        """Scrolls table containers horizontally across all frames to ensure older weeks (e.g. 10-16 Aug) are rendered."""
        if not self.page:
            return
        print("[*] Scrolling Business reports table horizontally to reveal earlier weekly columns...")
        for f in [self.page.main_frame] + self.page.frames:
            try:
                f.evaluate("""() => {
                    const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
                        return (el.scrollWidth > el.clientWidth) && (el.clientWidth > 250);
                    });
                    for (const s of scrollables) {
                        s.scrollLeft = 0;
                    }
                }""")
            except Exception:
                pass
        self.page.wait_for_timeout(800)

    def expand_accordions(self):
        """Expands collapsible row chevrons in the Business reports table (e.g., Menu to order -> Cart to order)."""
        if not self.page:
            return
        print("[*] Checking and expanding table accordions in Business reports (e.g. 'Menu to order' -> 'Cart to order')...")
        try:
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
                m2o_btn = self.find_clickable([
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

    def _extract_table_dom(self) -> Dict[str, Any]:
        """Scans all frames to retrieve headers, structured rows, and body text."""
        table_data = {"headers": [], "rows": [], "rawText": ""}
        if not self.page:
            return table_data

        for f in self.page.frames:
            try:
                f_data = f.evaluate("""() => {
                    const result = {
                        headers: [],
                        rows: [],
                        rawText: document.body ? document.body.innerText : ''
                    };

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

        return table_data

    def extract_data(
        self,
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
        restaurant_name: Optional[str] = None,
        restaurant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Navigates to Reporting -> Business reports, selects outlet and weekly view,
        extracts table data and parses funnel/operational metrics.
        """
        data: Dict[str, Any] = {}
        if not self.page:
            return data

        print("\n" + "-" * 50)
        print("[1] Navigating to REPORTING tab (Business reports)...")
        print("-" * 50)

        try:
            self.close_all_drawers_and_modals()

            print(f"[*] Navigating directly to Reporting URL: {ZOMATO_REPORTS_URL}")
            self.page.goto(ZOMATO_REPORTS_URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)

            biz_tab_selectors = [
                "//span[contains(text(), 'Business reports')]",
                "//button[contains(., 'Business reports')]",
                "//div[@role='tab'][contains(., 'Business reports')]",
                "//a[contains(., 'Business reports')]",
                "//*[text()='Business reports']",
            ]
            biz_tab = self.find_clickable(biz_tab_selectors, timeout_ms=3000)
            if biz_tab:
                try:
                    biz_tab.click()
                    print("[+] Clicked 'Business reports' tab.")
                    self.page.wait_for_timeout(3000)
                except Exception:
                    pass

            self.outlet_selector.select_outlet(restaurant_id or restaurant_name)
            self.page.wait_for_timeout(3000)

            self.select_weekly_view()
            self.page.wait_for_timeout(3000)

            # Wait for table rows to render
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

            self.expand_accordions()
            self.scroll_to_reveal_columns()

            table_data = self._extract_table_dom()
            headers = table_data.get("headers", [])
            rows = table_data.get("rows", [])
            body_text = table_data.get("rawText", "")

            # Retry if 0 rows found
            if len(rows) == 0:
                print("[!] 0 table rows found on initial scan. Retrying tab navigation and table load...")
                biz_tab = self.find_clickable(biz_tab_selectors, timeout_ms=2000)
                if biz_tab:
                    try:
                        biz_tab.click()
                        self.page.wait_for_timeout(2000)
                    except Exception:
                        pass
                self.outlet_selector.select_outlet(restaurant_id or restaurant_name)
                self.select_weekly_view()
                self.page.wait_for_timeout(3000)
                self.expand_accordions()
                self.scroll_to_reveal_columns()

                table_data = self._extract_table_dom()
                headers = table_data.get("headers", [])
                rows = table_data.get("rows", [])
                body_text = table_data.get("rawText", "")

            if not headers or len(headers) < 3:
                week_matches = re.findall(r"(?:Week\s*\d+[\s\S]*?\d+\s*-\s*\d+\s*[A-Za-z]+(?:\s*\d{4})?|Week\s*\d+)", body_text)
                if week_matches:
                    headers = ["Metric", "Trend"] + [w.strip() for w in week_matches]

            print(f"[*] Discovered {len(headers)} columns and {len(rows)} table rows in Reporting.")
            if headers:
                print(f"[*] Column Headers: {[h.replace(chr(10), ' ') for h in headers]}")

            target_col_idx = self.parser.find_target_column_index(headers, start_date, end_date, date_label)
            header_name = headers[target_col_idx].replace("\n", " ") if target_col_idx < len(headers) else "N/A"
            print(f"[*] Target column index: {target_col_idx} (Header: '{header_name}')")

            if rows:
                extracted = self.parser.extract_metrics_from_rows(rows, target_col_idx, start_date, end_date, date_label)
                data.update(extracted)

            extracted_fallback = self.parser.parse_reporting_text_matrix(body_text, target_col_idx, headers, start_date, end_date)
            for k, v in extracted_fallback.items():
                if k not in data or data[k] is None or data[k] == 0:
                    data[k] = v

            if "c2o" not in data or not data["c2o"]:
                m_c2o = re.search(r"(?:Cart to order|Menu to cart|Cart conversion|C2O)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%", body_text, re.I)
                if m_c2o:
                    data["c2o"] = clean_number(m_c2o.group(1))

            print("[✓] Extracted from Reporting tab:", {k: v for k, v in data.items() if v is not None})

        except Exception as e:
            print(f"[!] Error in Reporting tab extraction: {e}")

        return data
