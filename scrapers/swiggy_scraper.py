"""
Swiggy Scraper Module (Facade)
Forwards calls and re-exports the modular architecture from `scrapers.swiggy`.
"""

from scrapers.swiggy import (
    BaseSwiggyScraper,
    SwiggyAuth,
    SwiggyOutletSelector,
    SwiggyPerformanceParser,
    SwiggyPerformanceScraper,
    SwiggyPayoutParser,
    SwiggyPayoutScraper,
    SwiggyScraper,
    SwiggyNetworkCapture,
    SwiggySessionManager,
    SwiggyApiDiscovery,
    SwiggyApiClient,
    SwiggyGraphQLClient,
    bootstrap_swiggy_api_auth,
)

__all__ = [
    "BaseSwiggyScraper",
    "SwiggyAuth",
    "SwiggyOutletSelector",
    "SwiggyPerformanceParser",
    "SwiggyPerformanceScraper",
    "SwiggyPayoutParser",
    "SwiggyPayoutScraper",
    "SwiggyScraper",
    "SwiggyNetworkCapture",
    "SwiggySessionManager",
    "SwiggyApiDiscovery",
    "SwiggyApiClient",
    "SwiggyGraphQLClient",
    "bootstrap_swiggy_api_auth",
]
