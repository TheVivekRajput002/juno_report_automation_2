import re
from typing import Any, Dict, Optional, List, Tuple
from playwright.sync_api import Page, Locator

from scrapers.swiggy.network_capture import SwiggyNetworkCapture


class BaseSwiggyScraper:
    """
    Base class providing common utilities for Playwright DOM navigation,
    multi-frame querying, modal handling, and network interception across Swiggy Partner portal tabs.
    Network capture is delegated to SwiggyNetworkCapture (Swiggy-only module).
    """

    def __init__(self, page: Optional[Page] = None, network_capture: Optional[SwiggyNetworkCapture] = None):
        self.page = page
        self.network_capture = network_capture or SwiggyNetworkCapture()
        if self.page:
            self.network_capture.attach(self.page)

    @property
    def intercepted_data(self) -> Dict[str, Any]:
        """Backward-compatible alias for captured JSON responses."""
        return self.network_capture.intercepted_responses

    def find_clickable(self, candidates: List[str], timeout_ms: int = 2000) -> Optional[Locator]:
        """Tries multiple selectors safely across main page and all frames and returns the first visible one."""
        if not self.page:
            return None
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

    def close_all_drawers_and_modals(self):
        """Closes any open side-drawers, popups, modals, or dialog backdrops."""
        if not self.page:
            return
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    f.evaluate("""() => {
                        const closeBtns = Array.from(document.querySelectorAll('[aria-label="close"], [aria-label="Close"], button[class*="close"], [class*="close-icon"], [class*="CloseIcon"], svg[class*="close"], [data-testid*="close"]'));
                        for (const b of closeBtns) {
                            try { b.click(); } catch(e) {}
                        }
                    }""")
                except Exception:
                    pass
            self.page.wait_for_timeout(300)
        except Exception:
            pass

    @staticmethod
    def parse_outlet_label(text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parses restaurant name and numeric Swiggy ID from outlet labels like:
        - 'The Paneer Story (ID: 1394282)'
        - 'Biryani Lovers - Shankar Nagar | ID: 1263351'
        - 'The Spice Meridian (1363315)'
        """
        if not text:
            return None, None

        # Extract numeric ID (typically 5-8 digits for Swiggy outlets)
        res_id = None
        m_id = re.search(r"\b(?:[Ii][Dd]|Id|ID)[:\s#]+(\d{4,10})", text)
        if not m_id:
            m_id = re.search(r"\((\d{4,10})\)", text)
        if m_id:
            res_id = m_id.group(1).strip()

        # Extract clean name
        first_line = text.strip().split("\n")[0].strip()
        clean = re.sub(r"\s*\(?\b[Ii][Dd]\b:?\s*\d+\)?.*$", "", first_line, flags=re.I)
        clean = re.sub(r"\s*\(\d+\).*$", "", clean).strip()
        clean = re.sub(r"\s*\|.*$", "", clean).strip()
        clean = re.sub(r"\s*-\s*\d+.*$", "", clean).strip()
        if clean.endswith("(") or clean.endswith("-"):
            clean = clean[:-1].strip()

        name = clean if clean and not clean.isdigit() else None
        if not res_id and text.strip().isdigit():
            res_id = text.strip()

        return name, res_id
