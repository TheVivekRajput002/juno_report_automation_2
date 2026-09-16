# Multi-Platform Scraper Architecture & Modular Design (Zomato & Swiggy)

## 1. Overview & Architectural Goals

The report automation system extracts performance, operational, and financial settlement data across both **Zomato** and **Swiggy** restaurant partner portals:
1. **Zomato Partner Portal (`zomato.com/partners/onlineordering`)**:
   - **Reporting Portal (`/reporting`)**: Matrix table funnel & operations metrics.
   - **Finance Portal (`/finance/payouts`)**: Past weekly cycle drawers with itemized deductions.
2. **Swiggy Partner Portal (`partner.swiggy.com`)**:
   - **Business Reports Portal (`/business-metrics` or `/reports`)**: Outlet-level funnel metrics (Impressions, Menu Opens, I2M, M2O, C2O), Operational metrics (Online availability %, KPT), and Restaurant Cancelled Orders.
   - **Finance Portal (`/finance` or `/payouts`)**: Weekly payout cards and side-drawer breakdowns (Total Orders, Customer Paid (A), Total Fees (B), Taxes/TDS (D), Ads (E), and Net Payout).

### Core Architectural Goals:
- **Strict Decoupling & Isolation**: Zomato and Swiggy scrapers live in separate namespaces (`scrapers/zomato/` and `scrapers/swiggy/`). Changes to one platform never disrupt or break the other.
- **Single Responsibility Modules**: Separation of Navigation, Outlet Selection, DOM/Drawer interactions, and Pure Python Data Parsing.
- **Independent Unit Testing**: All parsers (`ReportingParser`, `PayoutParser`, `SwiggyPerformanceParser`, `SwiggyPayoutParser`) are pure Python classes without browser dependencies.
- **Direct Evaluated Values**: In compliance with `AGENTS.md`, numeric values are evaluated directly, and percentages are formatted as `"XX.XX%"` strings without openpyxl uncalculated formula dependencies.

---

## 2. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Orchestration Layer
        CLI[main.py CLI / Web UI] --> Runner[Automation Runner]
        Runner --> ZomatoCoord[ZomatoScraper (Coordinator)]
        Runner --> SwiggyCoord[SwiggyScraper (Coordinator)]
    end

    subgraph Browser & Session Management
        BM[BrowserManager (.user_data/chrome_profile)]
        ZomatoCoord --> BM
        SwiggyCoord --> BM
    end

    subgraph Zomato Pipeline
        ZomatoCoord --> ZAuth[ZomatoAuth]
        ZomatoCoord --> ZOutlet[OutletSelector]
        ZomatoCoord --> ZRepScraper[ReportingScraper]
        ZomatoCoord --> ZPayScraper[PayoutScraper]
        ZRepScraper --> ZRepParser[ReportingParser]
        ZPayScraper --> ZPayParser[PayoutParser]
    end

    subgraph Swiggy Pipeline
        SwiggyCoord --> SAuth[SwiggyAuth]
        SwiggyCoord --> SOutlet[SwiggyOutletSelector]
        SwiggyCoord --> SPerfScraper[SwiggyPerformanceScraper]
        SwiggyCoord --> SPayScraper[SwiggyPayoutScraper]
        SPerfScraper --> SPerfParser[SwiggyPerformanceParser]
        SPayScraper --> SPayParser[SwiggyPayoutParser]
    end

    subgraph Downstream Processing & Exporters
        ZomatoCoord --> Calc[MetricCalculator]
        SwiggyCoord --> Calc
        Calc --> ExcelGen[ExcelReportGenerator (Z, S, Z+S)]
        Calc --> SheetGen[GoogleSheetsReportGenerator (Z, S, Z+S)]
    end
```

---

## 3. Directory & Module Structure

```
scrapers/
├── browser_manager.py                  # Playwright browser lifecycle & persistent sessions
├── zomato_scraper.py                   # Facade & backward compatibility export
├── swiggy_scraper.py                   # Facade & backward compatibility export for Swiggy
├── zomato/
│   ├── __init__.py                     # Package exports (ZomatoScraper, parsers, sub-scrapers)
│   ├── base.py                         # Base class with safe DOM locators & frame traversal
│   ├── auth.py                         # Zomato login status checker & session verification
│   ├── outlet_selector.py              # Zomato outlet selection modal & dialog handler
│   ├── reporting_parser.py             # Pure parser for Reporting matrix table & fallback text
│   ├── reporting_scraper.py            # Business Reports tab scraper & table navigator
│   ├── payout_parser.py                # Pure parser for Payout side-drawer text & discount formulas
│   ├── payout_scraper.py               # Finance -> Payouts scraper & cycle row navigator
│   └── coordinator.py                  # ZomatoScraper orchestrator
└── swiggy/
    ├── __init__.py                     # Package exports (SwiggyScraper, parsers, sub-scrapers)
    ├── base.py                         # Base class with safe DOM locators & frame traversal
    ├── auth.py                         # Swiggy login status checker & session verification
    ├── outlet_selector.py              # Swiggy outlet dropdown/modal selector by Swiggy ID
    ├── performance_parser.py           # Pure parser for Swiggy Business Reports / Funnel metrics
    ├── performance_scraper.py          # Business Reports tab scraper (Filter modal, dates, metrics)
    ├── payout_parser.py                # Pure parser for Swiggy Finance & Settlement drawer
    ├── payout_scraper.py               # Finance tab scraper (Irregular cycle date matching, drawer)
    └── coordinator.py                  # SwiggyScraper orchestrator
```

---

## 4. Swiggy Scraper Extraction & Calculation Rules

### 1. Date Matching Rule
- **Payout Cycles**: Swiggy payout cycles can be irregular (e.g., `23rd Aug-31st Aug`, `16th Aug-22nd Aug`). The system dynamically evaluates and selects the payout card with the maximum overlap / closest matching date range to the target week.

### 2. Finance Page Extraction (Payout Details)
**Before extracting**: Select target outlet from the top-left dropdown, navigate to Past Payouts / Current Payout, select target week card, and click `See details ->`.

**Field Extractions**:
- **Orders**: `Total Orders` (under past payout card header).
- **Subtotal**: `Item Total` (under `(A) Total Customer Paid`).
- **Total Discount**: Sum of `Restaurant Discounts (Coupon based)` + `Restaurant Discounts (Trade Discounts, Freebies and others)` (under `(A) Total Customer Paid`).
- **Sales after discount**: `Subtotal - Total Discount`
- **Net order value**: `Sales after discount / Orders` (Numeric, rounded to 2 decimal places).
- **Packaging Charges**: `Packaging Charges` (under Finance tab, or `0` if absent).
- **Commission**: `(B) Total Fees` + `TDS` (under `(D) Total Taxes`).
- **Ads**: `(E) Growth Investments in Ads`.
- **Cash in Bank**: `Net Payout` (`Net Payout (A+B+C+D+E+F)`).

### 3. Business Reports Tab Extraction (Performance Metrics)
**Before extracting**: In the Filter modal, select "Filter by outlets" (not Brands), select specific outlet ID, and apply the custom target date range.

**Field Extractions**:
- **Visibility**: `Online availability` (under Operations section).
- **KPT**: `Kitchen Prep Time` (under Operations section).
- **Impressions**: `Impressions` (under Funnel section).
- **I2M**: `Menu opens percentage` (under Funnel section).
- **Menu Opens**: `Menu opens count` (under Funnel section).
- **C2O**: `Orders placed percentage` (under Funnel section).
- **M2O**: Calculated as `Cart builds % × Orders placed %` (from Funnel section).
- **Mx Rejections**: `Restaurant Cancelled Orders` (under Sales section).

### 4. Swiggy Percentage Metric Calculations
All percentage metrics are formatted as strings with 2 decimal places and the `%` sign:
- **Discount %**: `(Total Discount / Subtotal) * 100` $\rightarrow$ `"XX.XX%"`
- **Commission %**: `(Commission / Sales after discount) * 100` $\rightarrow$ `"XX.XX%"`
- **Ads %**: `(Ads / Subtotal) * 100` $\rightarrow$ `"XX.XX%"`
- **Payout %**: `(Cash in Bank / Subtotal) * 100` $\rightarrow$ `"XX.XX%"`
- **Visibility, I2M, C2O, M2O**: Formatted directly as percentage strings (e.g., `"98.90%"`).

---

## 5. Zomato Scraper Extraction & Calculation Rules

### 5.1 Business Reports Tab Extraction
- Navigation: `/partners/onlineordering/reporting` $\rightarrow$ Select Outlet $\rightarrow$ Select Weekly granularity.
- Metrics: `Sales`, `Delivered Orders`, `Average Order Value`, `Online %` (Visibility), `Kitchen Prep Time` (KPT), `Impressions`, `I2M` (Impression to Menu %), `M2O` (Menu to Order %), `C2O` (Cart to Order %), `Rejections`.

### 5.2 Finance / Payouts Tab Extraction
- Navigation: `/partners/onlineordering/finance/payouts` $\rightarrow$ Select Outlet $\rightarrow$ Click Past Cycle Row $\rightarrow$ Expand Drawer.
- Metrics:
  - `Subtotal`: Item Subtotal under Net Order Value.
  - `Total Discount`: Promos + Flat offs/Freebies/Gold + Delivery Discount.
  - `Sales after discount`: `Subtotal - Total Discount`.
  - `Net order value`: `Sales after discount / Orders`.
  - `Commission`: Order level deductions (C) + GST @18% (D).
  - `Ads`: Investments in growth (E).
  - `Cash in Bank`: Estimated payout / Net payout.

---

## 6. Combined (Z+S) Metric Derivation Rules

When both platforms are scraped or when generating the multi-platform report, the **Z+S** combined column is evaluated as follows:
- $\text{Orders}_{ZS} = \text{Orders}_Z + \text{Orders}_S$
- $\text{Subtotal}_{ZS} = \text{Subtotal}_Z + \text{Subtotal}_S$
- $\text{Total Discount}_{ZS} = \text{Total Discount}_Z + \text{Total Discount}_S$
- $\text{Sales after discount}_{ZS} = \text{Subtotal}_{ZS} - \text{Total Discount}_{ZS}$
- $\text{Net order value}_{ZS} = \text{Sales after discount}_{ZS} / \text{Orders}_{ZS}$
- $\text{Packaging Charges}_{ZS} = \text{Packaging}_Z + \text{Packaging}_S$
- $\text{Commission}_{ZS} = \text{Commission}_Z + \text{Commission}_S$
- $\text{Ads}_{ZS} = \text{Ads}_Z + \text{Ads}_S$
- $\text{Cash in Bank}_{ZS} = \text{Cash in Bank}_Z + \text{Cash in Bank}_S$
- $\text{Discount \%}_{ZS} = (\text{Total Discount}_{ZS} / \text{Subtotal}_{ZS}) \times 100 \rightarrow \text{"XX.XX\%"}$
- $\text{Commission \%}_{ZS} = (\text{Commission}_{ZS} / \text{Sales after discount}_{ZS}) \times 100 \rightarrow \text{"XX.XX\%"}$
- $\text{Ads \%}_{ZS} = (\text{Ads}_{ZS} / \text{Subtotal}_{ZS}) \times 100 \rightarrow \text{"XX.XX\%"}$
- $\text{Payout \%}_{ZS} = (\text{Cash in Bank}_{ZS} / \text{Subtotal}_{ZS}) \times 100 \rightarrow \text{"XX.XX\%"}$
- $\text{Impressions}_{ZS} = \text{Impressions}_Z + \text{Impressions}_S$
- $\text{Menu Opens}_{ZS} = \text{Menu Opens}_Z + \text{Menu Opens}_S$
- $\text{KPT}_{ZS} = \text{Average}(\text{KPT}_Z, \text{KPT}_S)$
- Funnel Percentages ($\text{Visibility}_{ZS}, \text{I2M}_{ZS}, \text{C2O}_{ZS}, \text{M2O}_{ZS}$): Derived or formatted consistently.

---

## 7. How to Debug Each Step Independently

### 1. Debugging Swiggy Payout Drawer Parsing (No browser needed)
```python
from scrapers.swiggy.payout_parser import SwiggyPayoutParser

raw_drawer_text = """
Total Orders: 74
(A) Total Customer Paid: ₹ 22,450.00
Item Total: ₹ 22,450.00
Restaurant Discounts (Coupon based): - ₹ 3,100.00
Restaurant Discounts (Trade Discounts, Freebies and others): - ₹ 650.00
(B) Total Fees: ₹ 4,200.00
(D) Total Taxes:
TDS: ₹ 224.50
(E) Growth Investments in Ads: ₹ 6,500.00
Net Payout (A+B+C+D+E+F): ₹ 7,775.50
"""

parser = SwiggyPayoutParser()
result = parser.parse_payout_text(raw_drawer_text)
print(result)
```

### 2. Debugging Swiggy Irregular Cycle Date Matcher (No browser needed)
```python
from datetime import datetime
from scrapers.swiggy.payout_scraper import SwiggyPayoutScraper

cards = [
    {"label": "23 Aug - 31 Aug", "start": datetime(2026, 8, 23), "end": datetime(2026, 8, 31)},
    {"label": "16 Aug - 22 Aug", "start": datetime(2026, 8, 16), "end": datetime(2026, 8, 22)},
    {"label": "09 Aug - 15 Aug", "start": datetime(2026, 8, 9), "end": datetime(2026, 8, 15)},
]
target_start = datetime(2026, 8, 24)
target_end = datetime(2026, 8, 30)

matched_card = SwiggyPayoutScraper.find_best_matching_cycle(cards, target_start, target_end)
print("Best match:", matched_card["label"]) # Expected: 23 Aug - 31 Aug
```

### 3. Debugging Swiggy Business Reports Performance Parser (No browser needed)
```python
from scrapers.swiggy.performance_parser import SwiggyPerformanceParser

raw_funnel_text = """
Operations:
Online availability: 98.50%
Kitchen Prep Time: 12 mins
Funnel:
Impressions: 14,500
Menu opens: 1,885 (13.00%)
Cart builds: 45.00%
Orders placed: 32.00%
Sales:
Restaurant Cancelled Orders: 1
"""

parser = SwiggyPerformanceParser()
result = parser.parse_performance_text(raw_funnel_text)
print(result)
```

### 4. Running Full Swiggy Extraction in Browser
```python
from datetime import datetime
from scrapers.browser_manager import BrowserManager
from scrapers.swiggy import SwiggyScraper

with BrowserManager(headless=False) as bm:
    page = bm.get_page()
    scraper = SwiggyScraper(page)
    
    data = scraper.scrape_all(
        start_date=datetime(2026, 8, 24),
        end_date=datetime(2026, 8, 30),
        restaurant_id="1394282"
    )
    print("Swiggy extracted data:", data)
```
