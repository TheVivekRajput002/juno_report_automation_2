import argparse
import sys
from datetime import datetime, timedelta
from typing import Tuple, Optional, List, Union

from config import (
    DEFAULT_RESTAURANT_NAME,
    DEFAULT_RESTAURANT_ID,
    DEFAULT_SWIGGY_ID,
    ZOMATO_LOGIN_URL,
    ZOMATO_DASHBOARD_URL,
    SWIGGY_LOGIN_URL,
    SWIGGY_DASHBOARD_URL,
    DEFAULT_WORKSHEET_NAME,
    GOOGLE_SHEET_URL,
)
from scrapers.browser_manager import BrowserManager
from scrapers.zomato_scraper import ZomatoScraper
from scrapers.swiggy_scraper import SwiggyScraper
from processors.metric_calculator import MetricCalculator
from exporters.excel_generator import ExcelReportGenerator
from exporters.google_sheets_generator import GoogleSheetsReportGenerator


def format_date_range_label(start_date: datetime, end_date: datetime) -> str:
    """Formats start and end dates into a clean label (e.g. '24 - 30 Aug\\'26' or '28 Jul - 03 Aug\\'26')."""
    if start_date.year != end_date.year:
        return f"{start_date.strftime('%d %b')}'{start_date.strftime('%y')} - {end_date.strftime('%d %b')}'{end_date.strftime('%y')}"
    elif start_date.month != end_date.month:
        return f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}'{end_date.strftime('%y')}"
    else:
        return f"{start_date.strftime('%d')} - {end_date.strftime('%d %b')}'{end_date.strftime('%y')}"


def get_weekly_date_ranges(num_weeks: int = 1) -> List[Tuple[datetime, datetime, str]]:
    """
    Returns list of (start_date, end_date, formatted_label) tuples for the past `num_weeks` completed weeks.
    Ordered chronologically from earliest to most recent.
    """
    today = datetime.now()
    ranges = []
    # Loop backwards from num_weeks to 1 so the reports are chronologically ordered
    for w in range(num_weeks, 0, -1):
        monday = today - timedelta(days=today.weekday() + 7 * w)
        sunday = monday + timedelta(days=6)
        label = format_date_range_label(monday, sunday)
        ranges.append((monday, sunday, label))
    return ranges


def get_last_week_dates() -> Tuple[datetime, datetime, str]:
    """Returns previous completed week's Monday, Sunday, and formatted label."""
    return get_weekly_date_ranges(num_weeks=1)[0]


def get_custom_dates(start_str: str, end_str: str) -> Tuple[datetime, datetime, str]:
    """Parses custom start and end date strings (YYYY-MM-DD)."""
    start_date = datetime.strptime(start_str.strip(), "%Y-%m-%d")
    end_date = datetime.strptime(end_str.strip(), "%Y-%m-%d")
    label = format_date_range_label(start_date, end_date)
    return start_date, end_date, label


def setup_google_login():
    """Runs interactive login setup so the user can sign in to Zomato once."""
    with BrowserManager(headless=False) as bm:
        bm.interactive_login(ZOMATO_LOGIN_URL)


def setup_swiggy_login():
    """Runs interactive login setup so the user can sign in to Swiggy Partner once."""
    with BrowserManager(headless=False) as bm:
        bm.interactive_login(SWIGGY_LOGIN_URL)


def run_automation(
    date_ranges: Union[Tuple[datetime, datetime, str], List[Tuple[datetime, datetime, str]], datetime],
    end_date: Optional[datetime] = None,
    date_label: Optional[str] = None,
    restaurant_name: Optional[str] = None,
    restaurant_id: Optional[str] = None,
    swiggy_id: Optional[str] = None,
    platform: str = "zomato",
    worksheet_name: str = DEFAULT_WORKSHEET_NAME,
    export_excel: bool = False,
    export_sheets: bool = True,
):
    """Executes scraper, calculator, and report generator pipeline for one or multiple date ranges."""
    # Normalize date_ranges input for backwards-compatibility
    if isinstance(date_ranges, datetime):
        if end_date is None or date_label is None:
            raise ValueError("end_date and date_label must be provided when start_date is passed as first argument.")
        ranges: List[Tuple[datetime, datetime, str]] = [(date_ranges, end_date, date_label)]
    elif isinstance(date_ranges, tuple):
        ranges = [date_ranges]
    else:
        ranges = list(date_ranges)

    target_display_name = restaurant_name or (f"ID: {restaurant_id}" if restaurant_id else DEFAULT_RESTAURANT_NAME)
    target_z_id = restaurant_id or (DEFAULT_RESTAURANT_ID if not restaurant_name else "")
    target_s_id = swiggy_id or DEFAULT_SWIGGY_ID

    plat_mode = platform.lower().strip()
    run_zomato = plat_mode in ["both", "all", "zs", "zomato", "z"]
    run_swiggy = plat_mode in ["both", "all", "zs", "swiggy", "s"]

    print("=" * 60)
    print(f"  REPORT AUTOMATION [{plat_mode.upper()}]: {len(ranges)} Report(s) Scheduled")
    print(f"  Target Outlet: {target_display_name}")
    if run_zomato:
        print(f"  - Zomato ID: {target_z_id or 'Auto'}")
    if run_swiggy:
        print(f"  - Swiggy ID: {target_s_id or 'Auto'}")
    if export_sheets:
        print(f"  Target Google Sheet Tab: '{worksheet_name}'")
    print("=" * 60)

    generated_excel_reports = []
    generated_sheet_urls = []

    with BrowserManager(headless=False) as bm:
        z_page = bm.get_named_page("zomato") if run_zomato else None
        s_page = bm.get_named_page("swiggy") if run_swiggy else None

        z_scraper = ZomatoScraper(z_page) if z_page else None
        s_scraper = SwiggyScraper(s_page) if s_page else None

        if z_scraper:
            print("[*] Checking Zomato login status...")
            if not z_scraper.check_login_status():
                print("\n[!] Zomato session not detected or expired.")
                print("[*] Please complete Google Login in the opened browser window...")
                try:
                    if sys.stdin and sys.stdin.isatty():
                        input(">>> After logging in to Zomato dashboard, press ENTER here to continue... ")
                    else:
                        z_scraper.auth.wait_for_login(timeout_sec=60)
                except (EOFError, KeyboardInterrupt):
                    z_scraper.auth.wait_for_login(timeout_sec=60)

        if s_scraper:
            print("[*] Checking Swiggy login status...")
            if not s_scraper.check_login_status():
                print("\n[!] Swiggy session not detected or expired.")
                print("[*] Please sign in to Swiggy Partner portal (mobile + OTP) in the opened browser window...")
                try:
                    if sys.stdin and sys.stdin.isatty():
                        input(">>> After logging in to Swiggy dashboard, press ENTER here to continue... ")
                    else:
                        s_scraper.auth.wait_for_login(timeout_sec=60)
                except (EOFError, KeyboardInterrupt):
                    s_scraper.auth.wait_for_login(timeout_sec=60)

        total_reports = len(ranges)
        for idx, (s_date, e_date, d_label) in enumerate(ranges, 1):
            print("\n" + "=" * 60)
            print(f"  PROCESSING REPORT [{idx}/{total_reports}]: {d_label}")
            print(f"  Date Range: {s_date.strftime('%Y-%m-%d')} to {e_date.strftime('%Y-%m-%d')}")
            print("=" * 60)

            z_metrics = None
            s_metrics = None

            # 1. Scrape Zomato
            if z_scraper:
                print(f"\n[*] Starting Zomato extraction for: {d_label}")
                z_raw = z_scraper.scrape_all(
                    s_date,
                    e_date,
                    d_label,
                    restaurant_name=restaurant_name,
                    restaurant_id=restaurant_id,
                )
                z_metrics = MetricCalculator.calculate_zomato_metrics(z_raw)
                print(f"[✓] Zomato calculated metrics: Orders={z_metrics.orders}, Sales={z_metrics.sales_after_discount}, Payout={z_metrics.cash_in_bank}")

            # 2. Scrape Swiggy
            if s_scraper:
                print(f"\n[*] Starting Swiggy extraction for: {d_label}")
                s_raw = s_scraper.scrape_all(
                    s_date,
                    e_date,
                    d_label,
                    restaurant_name=restaurant_name,
                    restaurant_id=target_s_id,
                )
                s_metrics = MetricCalculator.calculate_swiggy_metrics(s_raw)
                print(f"[✓] Swiggy calculated metrics: Orders={s_metrics.orders}, Sales={s_metrics.sales_after_discount}, Payout={s_metrics.cash_in_bank}")

            res_name = restaurant_name or (z_scraper.extracted_restaurant_name if z_scraper else None) or (s_scraper.extracted_restaurant_name if s_scraper else None) or DEFAULT_RESTAURANT_NAME
            res_id = (restaurant_id if restaurant_id else None) or (target_s_id if run_swiggy and not run_zomato else target_z_id) or DEFAULT_RESTAURANT_ID

            # 3. Generate styled Excel Report (optional)
            if export_excel:
                excel_gen = ExcelReportGenerator()
                report_file = excel_gen.generate_report(
                    zomato_metrics=z_metrics,
                    swiggy_metrics=s_metrics,
                    restaurant_name=res_name,
                    restaurant_id=res_id,
                    date_range_label=d_label,
                    report_title="Weekly Report",
                )
                generated_excel_reports.append(report_file)

            # 4. Insert and format table in Google Sheet tab
            if export_sheets:
                try:
                    sheets_gen = GoogleSheetsReportGenerator()
                    sheet_tab_url = sheets_gen.generate_report(
                        zomato_metrics=z_metrics,
                        swiggy_metrics=s_metrics,
                        restaurant_name=res_name,
                        restaurant_id=res_id,
                        date_range_label=d_label,
                        report_title="Weekly Report",
                        worksheet_name=worksheet_name,
                    )
                    generated_sheet_urls.append(sheet_tab_url)
                except Exception as e:
                    print(f"[!] Warning: Could not update Google Sheet: {e}")

    print("\n" + "=" * 60)
    print(f"[✓] Automation Completed Successfully!")
    if generated_sheet_urls:
        print(f"[+] Updated Google Sheet Tab '{worksheet_name}':")
        print(f"    - {generated_sheet_urls[-1]}")
    if generated_excel_reports:
        print(f"[+] Generated {len(generated_excel_reports)} Excel report(s):")
        for r in generated_excel_reports:
            print(f"    - {r}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Automate Zomato & Swiggy Partner Report Generation into Google Sheets.")
    parser.add_argument("--ui", "--web", action="store_true", help="Launch the Web UI in your browser")
    parser.add_argument("--port", type=int, default=8501, help="Port for the Web UI (default: 8501)")
    parser.add_argument("--platform", "-p", type=str, default="zomato", choices=["both", "zomato", "swiggy", "z", "s", "all"], help="Delivery platform to scrape (default: zomato)")
    parser.add_argument("--setup-login", action="store_true", help="Launch browser to perform initial Zomato Google login")
    parser.add_argument("--setup-login-swiggy", action="store_true", help="Launch browser to perform initial Swiggy Partner login")
    parser.add_argument("--weekly", nargs="?", const=1, type=int, default=None, help="Generate weekly report(s) for previous N weeks (default: 1)")
    parser.add_argument("--weeks", "-w", type=int, default=None, help="Number of previous weeks to generate reports for (e.g. 1, 2, 3...)")
    parser.add_argument("--start-date", type=str, help="Custom start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Custom end date (YYYY-MM-DD)")
    parser.add_argument("--restaurant", "-r", type=str, default=None, help="Target restaurant name for outlet selector")
    parser.add_argument("--restaurant-id", "--res-id", "-i", type=str, default=None, help="Target restaurant ID (Zomato) for outlet selector")
    parser.add_argument("--swiggy-id", "-s", type=str, default=None, help="Target Swiggy outlet ID")
    parser.add_argument("--tab", "--worksheet", type=str, default=DEFAULT_WORKSHEET_NAME, help="Target Google Sheet Tab name (default: Automated Reports)")
    parser.add_argument("--excel", action="store_true", help="Also generate local Excel (.xlsx) file in reports/")
    parser.add_argument("--no-sheets", action="store_true", help="Skip Google Sheets export")
    parser.add_argument("--test-sample", action="store_true", help="Generate sample verification report with test data for Zomato & Swiggy")

    args = parser.parse_args()
    target_restaurant = args.restaurant
    target_id = args.restaurant_id
    target_swiggy_id = args.swiggy_id
    worksheet_name = args.tab
    export_excel = args.excel
    export_sheets = not args.no_sheets
    platform = args.platform

    if args.ui:
        import uvicorn
        print(f"\n🚀 Launching Report Automation Web UI on http://localhost:{args.port}\n")
        uvicorn.run("server:app", host="0.0.0.0", port=args.port, reload=False)
        return

    if args.setup_login:
        setup_google_login()
        return

    if args.setup_login_swiggy:
        setup_swiggy_login()
        return

    if args.test_sample:
        zomato_sample = {
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
        swiggy_sample = {
            "orders": 74,
            "subtotal": 22450,
            "discount_coupons": 3100,
            "discount_trade": 650,
            "total_discount": 3750,
            "packaging_charges": 0,
            "total_fees_B": 4200,
            "tds_amount": 224.50,
            "commission": 4424.50,
            "ads": 6500,
            "cash_in_bank": 7775.50,
            "visibility": 98.50,
            "kpt": 12,
            "impressions": 14500,
            "i2m": 13.00,
            "menu_opens": 1885,
            "c2o": 32.00,
            "cart_builds_pct": 45.00,
            "m2o": 14.40,
            "mx_rejections": 1,
        }
        z_metrics = MetricCalculator.calculate_zomato_metrics(zomato_sample)
        s_metrics = MetricCalculator.calculate_swiggy_metrics(swiggy_sample)

        if export_excel:
            gen = ExcelReportGenerator()
            gen.generate_report(
                zomato_metrics=z_metrics,
                swiggy_metrics=s_metrics,
                restaurant_name=target_restaurant or DEFAULT_RESTAURANT_NAME,
                restaurant_id=target_id or DEFAULT_RESTAURANT_ID,
                date_range_label="24 - 30 Aug'26",
                filename="Sample_Weekly_Report.xlsx",
            )
        if export_sheets:
            s_gen = GoogleSheetsReportGenerator()
            s_gen.generate_report(
                zomato_metrics=z_metrics,
                swiggy_metrics=s_metrics,
                restaurant_name=target_restaurant or DEFAULT_RESTAURANT_NAME,
                restaurant_id=target_id or DEFAULT_RESTAURANT_ID,
                date_range_label="24 - 30 Aug'26",
                report_title="Weekly Report",
                worksheet_name=worksheet_name,
            )
        return

    num_weeks = args.weeks if args.weeks is not None else args.weekly
    if num_weeks is not None:
        if isinstance(num_weeks, bool):
            num_weeks = 1
        num_weeks = max(1, int(num_weeks))
        date_ranges = get_weekly_date_ranges(num_weeks)
        run_automation(
            date_ranges,
            restaurant_name=target_restaurant,
            restaurant_id=target_id,
            swiggy_id=target_swiggy_id,
            platform=platform,
            worksheet_name=worksheet_name,
            export_excel=export_excel,
            export_sheets=export_sheets,
        )
        return

    if args.start_date and args.end_date:
        start_date, end_date, date_label = get_custom_dates(args.start_date, args.end_date)
        run_automation(
            [(start_date, end_date, date_label)],
            restaurant_name=target_restaurant,
            restaurant_id=target_id,
            swiggy_id=target_swiggy_id,
            platform=platform,
            worksheet_name=worksheet_name,
            export_excel=export_excel,
            export_sheets=export_sheets,
        )
        return

    # Interactive CLI Menu if no arguments passed
    print("\n" + "=" * 50)
    print("      RESTAURANT REPORT AUTOMATION")
    print("=" * 50)
    print("1. Launch Web UI (Browser Control Panel) [Recommended]")
    print("2. Run Weekly Reports (Specify number of previous weeks)")
    print("3. Run Custom Date Range (Start Date - End Date)")
    print("4. Zomato Google Login Setup (Save persistent session)")
    print("5. Swiggy Partner Login Setup (Save persistent session)")
    print("6. Generate Sample Report from template data")
    print("7. Exit")
    print("-" * 50)

    choice = input("Select an option (1-7): ").strip()
    if choice == "1":
        import uvicorn
        print(f"\n🚀 Launching Report Automation Web UI on http://localhost:8501\n")
        uvicorn.run("server:app", host="0.0.0.0", port=8501, reload=False)
        return
    elif choice in ["2", "3"]:
        plat_input = input("Select Platform ([1] Both, [2] Zomato, [3] Swiggy) [Default: 2]: ").strip()
        if plat_input == "1":
            selected_plat = "both"
        elif plat_input == "3":
            selected_plat = "swiggy"
        else:
            selected_plat = "zomato"

        res_input = input(f"Enter Restaurant ID or Name [Default: {DEFAULT_RESTAURANT_NAME}]: ").strip()
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

        if choice == "2":
            weeks_input = input("Enter number of previous weeks to generate [Default: 1]: ").strip()
            num_weeks = int(weeks_input) if weeks_input.isdigit() and int(weeks_input) > 0 else 1
            date_ranges = get_weekly_date_ranges(num_weeks)
            print(f"\n[*] Selected {num_weeks} week(s) to process:")
            for s, e, lbl in date_ranges:
                print(f"    - {lbl} ({s.strftime('%Y-%m-%d')} to {e.strftime('%Y-%m-%d')})")
            run_automation(
                date_ranges,
                restaurant_name=target_restaurant,
                restaurant_id=target_id,
                swiggy_id=target_swiggy_id,
                platform=selected_plat,
                worksheet_name=worksheet_name,
                export_excel=export_excel,
                export_sheets=export_sheets,
            )
        elif choice == "3":
            start_str = input("Enter start date (YYYY-MM-DD): ").strip()
            end_str = input("Enter end date (YYYY-MM-DD): ").strip()
            start_date, end_date, date_label = get_custom_dates(start_str, end_str)
            run_automation(
                [(start_date, end_date, date_label)],
                restaurant_name=target_restaurant,
                restaurant_id=target_id,
                swiggy_id=target_swiggy_id,
                platform=selected_plat,
                worksheet_name=worksheet_name,
                export_excel=export_excel,
                export_sheets=export_sheets,
            )
    elif choice == "4":
        setup_google_login()
    elif choice == "5":
        setup_swiggy_login()
    elif choice == "6":
        zomato_sample = {
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
        swiggy_sample = {
            "orders": 74,
            "subtotal": 22450,
            "discount_coupons": 3100,
            "discount_trade": 650,
            "total_discount": 3750,
            "packaging_charges": 0,
            "total_fees_B": 4200,
            "tds_amount": 224.50,
            "commission": 4424.50,
            "ads": 6500,
            "cash_in_bank": 7775.50,
            "visibility": 98.50,
            "kpt": 12,
            "impressions": 14500,
            "i2m": 13.00,
            "menu_opens": 1885,
            "c2o": 32.00,
            "cart_builds_pct": 45.00,
            "m2o": 14.40,
            "mx_rejections": 1,
        }
        z_metrics = MetricCalculator.calculate_zomato_metrics(zomato_sample)
        s_metrics = MetricCalculator.calculate_swiggy_metrics(swiggy_sample)
        s_gen = GoogleSheetsReportGenerator()
        s_gen.generate_report(
            zomato_metrics=z_metrics,
            swiggy_metrics=s_metrics,
            restaurant_name=DEFAULT_RESTAURANT_NAME,
            restaurant_id=DEFAULT_RESTAURANT_ID,
            date_range_label="24 - 30 Aug'26",
            report_title="Weekly Report",
            worksheet_name=worksheet_name,
        )
    else:
        print("Exiting.")


if __name__ == "__main__":
    main()
