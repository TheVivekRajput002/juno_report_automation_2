# Restaurant Report Automation (Zomato & Swiggy)

Automated tool to scrape business, financial, and funnel performance data from the **Zomato Restaurant Partner** dashboard and generate formatted Excel reports matching the exact required template.

---

## 📁 Project Structure

```
report_automation/
│
├── config.py                 # Configuration (URLs, directories, persistent profiles)
├── main.py                   # Orchestrator & CLI interface
│
├── scrapers/
│   ├── browser_manager.py    # Playwright browser manager with Google Login & session persistence
│   └── zomato_scraper.py     # Navigation, date range selection & metrics extraction
│
├── processors/
│   └── metric_calculator.py  # Business logic, derived metrics & formula calculations
│
├── exporters/
│   └── excel_generator.py    # Generates pixel-perfect styled Excel (.xlsx) reports
│
├── reports/                  # Generated Excel reports output directory
└── requirements.txt          # Project dependencies
```

---

## 🚀 Quick Start Guide

### 1. One-Time Google Login Setup
Because Google authentication cannot use OTP automation directly, run the setup once to save your session cookies in `.user_data/chrome_profile`:

```bash
python main.py --setup-login
```
- A Chrome browser window will open to the Zomato Partner login page.
- Click **"Sign in with Google"** and complete your authentication.
- Return to your terminal and press **ENTER** to save the session.
- *Subsequent automated runs will automatically reuse this session.*

---

### 2. Generate Weekly Report(s)
You can generate reports for the previous week or specify the number of previous weeks to process:

- **Previous 1 week (default):**
  ```bash
  python main.py --weekly
  ```
- **Previous N weeks (e.g., 2, 3, 4 weeks):**
  ```bash
  python main.py --weeks 2
  # or
  python main.py --weekly 3
  ```
This automatically calculates the completed weekly date ranges (Monday to Sunday), extracts the performance and finance metrics for each week sequentially within the same browser session, and saves individual formatted Excel reports in `reports/`.

---

### 3. Generate Custom Date Range Report
```bash
python main.py --start-date 2026-08-24 --end-date 2026-08-30
```

---

### 4. Interactive Menu
You can also run the script without flags to open an interactive menu:
```bash
python main.py
```

---

### 5. Generate Test / Verification Report
```bash
python main.py --test-sample
```

---

## 📊 Extracted Metrics & Formulas

| Line Item | Source / Formula |
| :--- | :--- |
| **Orders** | Delivered orders from reporting tab |
| **Subtotal** | Item subtotal under Net Order Value (payout page) |
| **Total Discount** | Sum of discounts under Net Order Value (payout page) |
| **Sales after discount** | Formula: `= Subtotal - Total Discount` |
| **Net order value** | Formula: `= Sales after discount / Orders` |
| **Packaging Charges** | Packaging charges or `0` |
| **Commission** | Order level deductions + GST on service and payment mechanism fees @18% (1st part of tax deductions block) |
| **ads** | Investment in Growth |
| **Cash in Bank** | Est payout (highlighted row) |
| **Discount %** | Formula: `= Total Discount / Subtotal` |
| **Commission %** | Formula: `= Commission / Sales after discount` |
| **Ads %** | Formula: `= ads / Subtotal` |
| **Payout %** | Formula: `= Cash in Bank / Subtotal` (highlighted row) |
| **Visibility** | In percentage (in report section) |
| **KPT** | Kitchen Prep Time |
| **Impressions** | Impressions count |
| **I2M** | In percentage (in report section) |
| **Menu Opens** | Formula: `= Impressions * I2M` |
| **C2O** | Cart to Order (in percentage) |
| **M2O** | In percentage (in report section) |
| **Mx Rejections** | Rejected orders (under payout section) |
# juno_report_automation
# juno_report_automation_2
