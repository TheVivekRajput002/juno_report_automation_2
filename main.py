import argparse
import sys
from datetime import datetime, timedelta
from typing import Tuple, Optional

from config import (
    DEFAULT_RESTAURANT_NAME,
    DEFAULT_RESTAURANT_ID,
    ZOMATO_LOGIN_URL,
    ZOMATO_DASHBOARD_URL,
)
from scrapers.browser_manager import BrowserManager
from scrapers.zomato_scraper import ZomatoScraper
from processors.metric_calculator import MetricCalculator
from exporters.excel_generator import ExcelReportGenerator


def get_last_week_dates() -> Tuple[datetime, datetime, str]:
    """Returns previous week's Monday, Sunday, and formatted label."""
    today = datetime.now()
    # Find most recent Monday
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    
    # Format label like "24 - 30 Aug'26"
    label = f"{last_monday.strftime('%d')} - {last_sunday.strftime('%d %b')}'{last_sunday.strftime('%y')}"
    return last_monday, last_sunday, label


def get_custom_dates(start_str: str, end_str: str) -> Tuple[datetime, datetime, str]:
    """Parses custom start and end date strings (YYYY-MM-DD)."""
    start_date = datetime.strptime(start_str.strip(), "%Y-%m-%d")
    end_date = datetime.strptime(end_str.strip(), "%Y-%m-%d")
    label = f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}'{end_date.strftime('%y')}"
    return start_date, end_date, label


def setup_google_login():
    """Runs interactive login setup so the user can sign in with Google once."""
    with BrowserManager(headless=False) as bm:
        bm.interactive_login(ZOMATO_LOGIN_URL)


def run_automation(
    start_date: datetime,
    end_date: datetime,
    date_label: str,
    restaurant_name: Optional[str] = None,
    restaurant_id: Optional[str] = None
):
    """Executes the complete scraper, calculator, and report generator pipeline."""
    target_display_name = restaurant_name or (f"ID: {restaurant_id}" if restaurant_id else DEFAULT_RESTAURANT_NAME)
    target_display_id = restaurant_id or (DEFAULT_RESTAURANT_ID if not restaurant_name else "")

    print("=" * 60)
    print(f"  ZOMATO REPORT AUTOMATION: {date_label}")
    if target_display_id and target_display_name != f"ID: {restaurant_id}":
        print(f"  Target Restaurant: {target_display_name} (ID: {target_display_id})")
    else:
        print(f"  Target Restaurant: {target_display_name}")
    print("=" * 60)

    with BrowserManager(headless=False) as bm:
        page = bm.get_page()
        scraper = ZomatoScraper(page)

        print("[*] Checking login status...")
        is_logged_in = scraper.check_login_status()

        if not is_logged_in:
            print("\n[!] Not logged in yet or session expired.")
            print("[*] Please complete Google Login in the opened browser window...")
            input(">>> After logging in to the dashboard, press ENTER here to continue extraction... ")

        print(f"\n[*] Starting data extraction for: {date_label}")
        extracted_data = scraper.scrape_all(
            start_date,
            end_date,
            date_label,
            restaurant_name=restaurant_name,
            restaurant_id=restaurant_id
        )

        res_name = extracted_data.get("restaurant_name") or restaurant_name or (f"Restaurant_{restaurant_id}" if restaurant_id else DEFAULT_RESTAURANT_NAME)
        res_id = extracted_data.get("restaurant_id") or restaurant_id or DEFAULT_RESTAURANT_ID

        print("\n[*] Extracted Raw Metrics:")
        pct_metrics = {"visibility", "i2m", "c2o", "m2o", "discount_pct", "commission_pct", "ads_pct", "payout_pct"}
        for k, v in extracted_data.items():
            if k in pct_metrics and isinstance(v, (int, float)):
                print(f"    - {k}: {v:.2f}%")
            else:
                print(f"    - {k}: {v}")

        # Compute all derived formulas and business rules
        metrics = MetricCalculator.calculate_zomato_metrics(extracted_data)

        # Generate styled Excel Report
        generator = ExcelReportGenerator()
        report_file = generator.generate_report(
            zomato_metrics=metrics,
            restaurant_name=res_name,
            restaurant_id=res_id,
            date_range_label=date_label,
            report_title="Weekly Report"
        )

        print("\n" + "=" * 60)
        print(f"[✓] Automation Completed Successfully!")
        print(f"[✓] Output Report File: {report_file}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Automate Zomato Partner Report Generation into Excel.")
    parser.add_argument("--setup-login", action="store_true", help="Launch browser to perform initial Google login")
    parser.add_argument("--weekly", action="store_true", help="Run report for the previous completed week (Mon-Sun)")
    parser.add_argument("--start-date", type=str, help="Custom start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Custom end date (YYYY-MM-DD)")
    parser.add_argument("--restaurant", "-r", type=str, default=None, help="Target restaurant name for outlet selector")
    parser.add_argument("--restaurant-id", "--res-id", "-i", type=str, default=None, help="Target restaurant ID for outlet selector")
    parser.add_argument("--test-sample", action="store_true", help="Generate sample verification report with test data")

    args = parser.parse_args()
    target_restaurant = args.restaurant
    target_id = args.restaurant_id

    if args.setup_login:
        setup_google_login()
        return

    if args.test_sample:
        from processors.metric_calculator import MetricCalculator
        from exporters.excel_generator import ExcelReportGenerator
        sample_data = {
            "orders": 58,
            "subtotal": 14465,
            "total_discount": 3071,
            "packaging_charges": 0,
            "commission": 3760,
            "ads": 7933,
            "cash_in_bank": 0,
            "visibility": 85.50,
            "kpt": 6,
            "impressions": 10216,
            "i2m": 9.30,
            "c2o": 28,
            "m2o": 6.40,
            "mx_rejections": 2,
        }
        metrics = MetricCalculator.calculate_zomato_metrics(sample_data)
        gen = ExcelReportGenerator()
        gen.generate_report(
            zomato_metrics=metrics,
            restaurant_name=target_restaurant or DEFAULT_RESTAURANT_NAME,
            restaurant_id=target_id or DEFAULT_RESTAURANT_ID,
            date_range_label="24 - 30 Aug'26",
            filename="Sample_Weekly_Report.xlsx"
        )
        return

    if args.weekly:
        start_date, end_date, date_label = get_last_week_dates()
        run_automation(start_date, end_date, date_label, restaurant_name=target_restaurant, restaurant_id=target_id)
        return

    if args.start_date and args.end_date:
        start_date, end_date, date_label = get_custom_dates(args.start_date, args.end_date)
        run_automation(start_date, end_date, date_label, restaurant_name=target_restaurant, restaurant_id=target_id)
        return

    # Interactive CLI Menu if no arguments passed
    print("\n" + "=" * 50)
    print("      RESTAURANT REPORT AUTOMATION")
    print("=" * 50)
    print("1. Run Weekly Report (Previous Monday - Sunday)")
    print("2. Run Custom Date Range (Start Date - End Date)")
    print("3. Google Login Setup (Save persistent session)")
    print("4. Generate Sample Report from template data")
    print("5. Exit")
    print("-" * 50)

    choice = input("Select an option (1-5): ").strip()
    if choice in ["1", "2"]:
        res_input = input(f"Enter Restaurant ID or Name [Default: {DEFAULT_RESTAURANT_NAME} / {DEFAULT_RESTAURANT_ID}]: ").strip()
        if res_input:
            if res_input.isdigit():
                target_id = res_input
                target_restaurant = None
            else:
                target_restaurant = res_input
                target_id = None
        else:
            target_restaurant = DEFAULT_RESTAURANT_NAME
            target_id = DEFAULT_RESTAURANT_ID

        if choice == "1":
            start_date, end_date, date_label = get_last_week_dates()
            run_automation(start_date, end_date, date_label, restaurant_name=target_restaurant, restaurant_id=target_id)
        elif choice == "2":
            start_str = input("Enter start date (YYYY-MM-DD): ").strip()
            end_str = input("Enter end date (YYYY-MM-DD): ").strip()
            start_date, end_date, date_label = get_custom_dates(start_str, end_str)
            run_automation(start_date, end_date, date_label, restaurant_name=target_restaurant, restaurant_id=target_id)
    elif choice == "3":
        setup_google_login()
    elif choice == "4":
        main_test_sample = argparse.Namespace(setup_login=False, weekly=False, start_date=None, end_date=None, test_sample=True, restaurant=None, restaurant_id=None)
        main()
    else:
        print("Exiting.")


if __name__ == "__main__":
    main()
