"""
Zomato Scraper Module (Facade)
Forwards calls and re-exports the modular architecture from `scrapers.zomato`.
"""

from scrapers.zomato import (
    BaseZomatoScraper,
    ZomatoAuth,
    OutletSelector,
    ReportingParser,
    ReportingScraper,
    PayoutParser,
    PayoutScraper,
    ZomatoScraper,
)

__all__ = [
    "BaseZomatoScraper",
    "ZomatoAuth",
    "OutletSelector",
    "ReportingParser",
    "ReportingScraper",
    "PayoutParser",
    "PayoutScraper",
    "ZomatoScraper",
]
