"""
Swiggy Scraper Modular Package
Provides decoupled classes for authentication, outlet selection,
performance parsing, payout extraction, and API discovery from the Swiggy Partner Portal.
All modules are isolated from Zomato scrapers.
"""

from scrapers.swiggy.base import BaseSwiggyScraper
from scrapers.swiggy.auth import SwiggyAuth
from scrapers.swiggy.outlet_selector import SwiggyOutletSelector
from scrapers.swiggy.performance_parser import SwiggyPerformanceParser
from scrapers.swiggy.performance_scraper import SwiggyPerformanceScraper
from scrapers.swiggy.payout_parser import SwiggyPayoutParser
from scrapers.swiggy.payout_scraper import SwiggyPayoutScraper
from scrapers.swiggy.coordinator import SwiggyScraper
from scrapers.swiggy.network_capture import SwiggyNetworkCapture
from scrapers.swiggy.session_manager import SwiggySessionManager
from scrapers.swiggy.api_discovery import SwiggyApiDiscovery
from scrapers.swiggy.api_client import SwiggyApiClient
from scrapers.swiggy.graphql_client import SwiggyGraphQLClient
from scrapers.swiggy.auth_bootstrap import bootstrap_swiggy_api_auth

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
