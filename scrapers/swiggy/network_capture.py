import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from playwright.sync_api import Page, Request, Response


PERFORMANCE_URL_KEYWORDS = (
    "business-metrics",
    "business_metrics",
    "performance",
    "metric",
    "report",
    "funnel",
    "insights",
    "analytics",
)

PAYOUT_URL_KEYWORDS = (
    "settlement",
    "payout",
    "finance",
    "ledger",
    "invoice",
    "growth",
)

GENERIC_JSON_KEYWORDS = (
    "api",
    "graphql",
    "gql",
)


def categorize_swiggy_url(url: str) -> str:
    """Classifies a captured URL into performance, payout, or unknown."""
    lower = url.lower()
    if any(kw in lower for kw in PAYOUT_URL_KEYWORDS):
        return "payout"
    if any(kw in lower for kw in PERFORMANCE_URL_KEYWORDS):
        return "performance"
    if any(kw in lower for kw in GENERIC_JSON_KEYWORDS):
        return "api"
    return "unknown"


def _should_capture_url(url: str) -> bool:
    lower = url.lower()
    # Skip analytics noise
    if "bam.nr-data.net" in lower or "newrelic" in lower:
        return False
    if "partner.swiggy.com" not in lower and "swiggy.com" not in lower:
        return False
    skip_ext = (".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".ico", ".map")
    if any(lower.split("?")[0].endswith(ext) for ext in skip_ext):
        return False
    # vhc-composer GraphQL is always relevant
    if "vhc-composer.swiggy.com" in lower:
        return True
    keywords = GENERIC_JSON_KEYWORDS + PERFORMANCE_URL_KEYWORDS + PAYOUT_URL_KEYWORDS
    return any(kw in lower for kw in keywords)


def _categorize_graphql_url(url: str, request_body: Optional[str] = None) -> str:
    lower = url.lower()
    body = (request_body or "").lower()
    if "businessmetricsdetails" in lower or "businessmetricsdetails" in body:
        return "performance"
    if "getrestaurantpayoutdetails" in lower or "getrestaurantpayoutdetails" in body:
        return "payout"
    if "getfinancerestaurantpastpayouts" in lower or "getfinancerestaurantpastpayouts" in body:
        return "payout"
    if "getownerfinancedetails" in lower or "getownerfinancedetails" in body:
        return "api"
    return categorize_swiggy_url(url)


class SwiggyNetworkCapture:
    """
    Swiggy-only Playwright network listener.
    Captures JSON API requests/responses during portal navigation for endpoint discovery.
    Completely isolated from Zomato scrapers.
    """

    def __init__(self, page: Optional[Page] = None):
        self.page = page
        self.entries: List[Dict[str, Any]] = []
        self.intercepted_responses: Dict[str, Any] = {}
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._attached_pages: Set[int] = set()
        self.access_token: Optional[str] = None

    def attach(self, page: Page) -> None:
        page_id = id(page)
        if page_id in self._attached_pages:
            return
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        self._attached_pages.add(page_id)
        self.page = page

    def clear(self) -> None:
        self.entries.clear()
        self.intercepted_responses.clear()
        self._pending_requests.clear()

    def _on_request(self, request: Request) -> None:
        try:
            url = request.url
            if not _should_capture_url(url):
                return
            post_data = request.post_data
            headers = dict(request.headers)
            token = headers.get("access_token") or headers.get("Access-Token")
            if token and len(str(token)) > 10:
                self.access_token = str(token)
            category = _categorize_graphql_url(url, post_data)
            self._pending_requests[request.url] = {
                "url": url,
                "method": request.method,
                "resource_type": request.resource_type,
                "request_headers": headers,
                "request_body": post_data,
                "page_url": self.page.url if self.page else "",
                "captured_at": datetime.now().isoformat(),
                "category": category,
            }
        except Exception:
            pass

    def _on_response(self, response: Response) -> None:
        try:
            url = response.url
            if not _should_capture_url(url):
                return

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.lower():
                return

            response_json = response.json()
            self.intercepted_responses[url] = response_json

            req_meta = self._pending_requests.pop(url, {})
            entry = {
                **req_meta,
                "url": url,
                "method": req_meta.get("method") or response.request.method,
                "status": response.status,
                "response_headers": dict(response.headers),
                "response_json": response_json,
                "page_url": req_meta.get("page_url") or (self.page.url if self.page else ""),
                "captured_at": req_meta.get("captured_at") or datetime.now().isoformat(),
                "category": req_meta.get("category") or _categorize_graphql_url(url, req_meta.get("request_body")),
            }
            self.entries.append(entry)
            self._log_capture(entry)
        except Exception:
            pass

    @staticmethod
    def _log_capture(entry: Dict[str, Any]) -> None:
        method = entry.get("method", "?")
        status = entry.get("status", "?")
        category = entry.get("category", "unknown")
        parsed = urlparse(entry.get("url", ""))
        path = parsed.path or entry.get("url", "")
        print(f"[Swiggy API] {method} {status} [{category}] {path}")

    def get_responses_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [e for e in self.entries if e.get("category") == category and e.get("response_json")]

    def get_best_response_json(self, category: str) -> Optional[Dict[str, Any]]:
        matches = self.get_responses_by_category(category)
        if not matches:
            keywords = PERFORMANCE_URL_KEYWORDS if category == "performance" else PAYOUT_URL_KEYWORDS
            for entry in reversed(self.entries):
                body = (entry.get("request_body") or "").lower()
                url = entry.get("url", "").lower()
                if category == "performance" and "businessmetricsdetails" in body:
                    return entry.get("response_json")
                if category == "payout" and "getrestaurantpayoutdetails" in body:
                    return entry.get("response_json")
                if any(kw in url for kw in keywords):
                    return entry.get("response_json")
            return None
        return matches[-1].get("response_json")

    def summarize(self) -> Dict[str, Any]:
        unique_urls: Dict[str, Dict[str, Any]] = {}
        for entry in self.entries:
            url = entry.get("url", "")
            if not url:
                continue
            unique_urls[url] = {
                "url": url,
                "method": entry.get("method"),
                "category": entry.get("category"),
                "status": entry.get("status"),
                "has_request_body": bool(entry.get("request_body")),
            }
        by_category: Dict[str, int] = {}
        for entry in self.entries:
            cat = entry.get("category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
        return {
            "total_captures": len(self.entries),
            "unique_endpoints": len(unique_urls),
            "by_category": by_category,
            "endpoints": list(unique_urls.values()),
        }

    def print_summary(self) -> None:
        summary = self.summarize()
        print("\n" + "=" * 50)
        print("[Swiggy API Discovery Summary]")
        print(f"  Total JSON responses captured: {summary['total_captures']}")
        print(f"  Unique endpoints: {summary['unique_endpoints']}")
        for cat, count in summary.get("by_category", {}).items():
            print(f"  - {cat}: {count}")
        if summary.get("endpoints"):
            print("\n  Discovered endpoints:")
            for ep in summary["endpoints"]:
                print(f"    [{ep.get('category')}] {ep.get('method')} {ep.get('url')}")
        print("=" * 50 + "\n")
