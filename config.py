import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Browser profile directory for persistent Google login and sessions
USER_DATA_DIR = BASE_DIR / ".user_data" / "chrome_profile"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Zomato Partner Portal URLs
ZOMATO_BASE_URL = "https://www.zomato.com/partners/onlineordering"
ZOMATO_LOGIN_URL = "https://www.zomato.com/partners/onlineordering"
ZOMATO_DASHBOARD_URL = "https://www.zomato.com/partners/onlineordering/reporting"
ZOMATO_FINANCE_URL = "https://www.zomato.com/partners/onlineordering/finance/payouts"
ZOMATO_REPORTS_URL = "https://www.zomato.com/partners/onlineordering/reporting"

# Swiggy Partner Portal URLs (for future expansion)
SWIGGY_BASE_URL = "https://partner.swiggy.com"
SWIGGY_LOGIN_URL = "https://partner.swiggy.com/login"

# Default restaurant info (if not extracted dynamically)
DEFAULT_RESTAURANT_NAME = "Biryani Lovers"
DEFAULT_RESTAURANT_ID = "22317789"

# Google Sheets Integration
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1KLnQnbQhOwb11W-kmT_UxHJPaCjQuUQinp-lYZs_zRE/edit?usp=sharing"
SPREADSHEET_ID = "1KLnQnbQhOwb11W-kmT_UxHJPaCjQuUQinp-lYZs_zRE"
SERVICE_ACCOUNT_FILE = BASE_DIR / "service_account.json"
DEFAULT_WORKSHEET_NAME = "Automated Reports"
