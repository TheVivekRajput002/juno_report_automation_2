import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import gspread
from google.oauth2.service_account import Credentials
from processors.metric_calculator import PlatformMetrics
from config import (
    BASE_DIR,
    DEFAULT_RESTAURANT_NAME,
    DEFAULT_RESTAURANT_ID,
    GOOGLE_SHEET_URL,
    SPREADSHEET_ID,
    SERVICE_ACCOUNT_FILE,
    DEFAULT_WORKSHEET_NAME,
)


def hex_to_rgb_dict(hex_str: str) -> Dict[str, float]:
    """Converts HEX color string (e.g. 'CCA9C2') to Google Sheets RGB dictionary (0.0 - 1.0)."""
    hex_str = hex_str.lstrip("#")
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    return {"red": r, "green": g, "blue": b}


class GoogleSheetsReportGenerator:
    """Generates styled report tables directly into Google Sheets matching user template."""

    # Colors
    COLOR_TITLE_BG = hex_to_rgb_dict("CCA9C2")        # Light mauve / pink
    COLOR_REPORT_TYPE_BG = hex_to_rgb_dict("434343")  # Dark grey
    COLOR_REPORT_TYPE_TXT = hex_to_rgb_dict("FFFFFF") # White text
    COLOR_LINE_ITEMS_BG = hex_to_rgb_dict("8EA6B4")   # Muted teal/blue
    COLOR_ZOMATO_BG = hex_to_rgb_dict("D32F2F")       # Zomato Red
    COLOR_SWIGGY_BG = hex_to_rgb_dict("E69138")       # Swiggy Orange
    COLOR_ZS_BG = hex_to_rgb_dict("A9D18E")           # Light Green
    COLOR_HIGHLIGHT_ROW = hex_to_rgb_dict("F9CB9C")   # Peach / Light Orange
    COLOR_BORDER = hex_to_rgb_dict("000000")          # Black

    def __init__(
        self,
        service_account_path: Path = SERVICE_ACCOUNT_FILE,
        spreadsheet_id: str = SPREADSHEET_ID,
    ):
        self.service_account_path = Path(service_account_path)
        self.spreadsheet_id = spreadsheet_id
        self._client = None
        self._spreadsheet = None

    def _get_client(self) -> gspread.Client:
        if not self._client:
            if not self.service_account_path.exists():
                raise FileNotFoundError(f"Service account file not found at: {self.service_account_path}")
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(self.service_account_path), scopes=scopes)
            self._client = gspread.authorize(creds)
        return self._client

    def _get_spreadsheet(self) -> gspread.Spreadsheet:
        if not self._spreadsheet:
            gc = self._get_client()
            self._spreadsheet = gc.open_by_key(self.spreadsheet_id)
        return self._spreadsheet

    def get_or_create_worksheet(self, worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> gspread.Worksheet:
        """Finds or creates the target worksheet."""
        sh = self._get_spreadsheet()
        try:
            ws = sh.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            print(f"[*] Creating new tab '{worksheet_name}' in Google Sheet...")
            ws = sh.add_worksheet(title=worksheet_name, rows=50, cols=50)
        return ws

    def _find_next_start_column(self, ws: gspread.Worksheet) -> int:
        """Finds next available 0-indexed column block to insert a table (leaving 1 column gap)."""
        values = ws.get_all_values()
        if not values or not any(values):
            return 0  # Start at Column A (index 0)

        # Check max columns with content in the first 25 rows
        max_col_used = 0
        for row in values[:25]:
            for col_idx in range(len(row) - 1, -1, -1):
                if row[col_idx].strip():
                    if col_idx + 1 > max_col_used:
                        max_col_used = col_idx + 1
                    break

        if max_col_used == 0:
            return 0
        # Leave 1 blank column gap between tables
        return max_col_used + 1

    def generate_report(
        self,
        zomato_metrics: PlatformMetrics,
        swiggy_metrics: Optional[PlatformMetrics] = None,
        restaurant_name: str = DEFAULT_RESTAURANT_NAME,
        restaurant_id: str = DEFAULT_RESTAURANT_ID,
        date_range_label: str = "24 - 30 Aug'26",
        report_title: str = "Weekly Report",
        worksheet_name: str = DEFAULT_WORKSHEET_NAME,
        start_col: Optional[int] = None,
    ) -> str:
        """
        Inserts and formats the report table in the designated Google Sheet tab.
        Returns the direct URL to the sheet tab.
        """
        sh = self._get_spreadsheet()
        ws = self.get_or_create_worksheet(worksheet_name)

        if start_col is None:
            start_col = self._find_next_start_column(ws)

        end_col = start_col + 4  # 4 columns for table (Line Items, Zomato, Swiggy, Z+S)

        # Ensure sheet has enough columns
        if ws.col_count < end_col + 2:
            ws.add_cols((end_col + 2) - ws.col_count)

        sheet_id = ws.id

        def fmt_pct(val: float) -> str:
            if not val:
                return "0.00%"
            v = float(val)
            if 0 < v <= 1.0:
                v = v * 100.0
            return f"{v:.2f}%"

        # Calculate Z+S combined metrics
        if swiggy_metrics:
            zs_orders = zomato_metrics.orders + swiggy_metrics.orders
            zs_subtotal = zomato_metrics.subtotal + swiggy_metrics.subtotal
            zs_total_discount = zomato_metrics.total_discount + swiggy_metrics.total_discount
            zs_sales_after_discount = round(zs_subtotal - zs_total_discount, 2)
            zs_net_order_value = round(zs_sales_after_discount / zs_orders, 2) if zs_orders > 0 else 0.0
            zs_packaging = zomato_metrics.packaging_charges + swiggy_metrics.packaging_charges
            zs_commission = zomato_metrics.commission + swiggy_metrics.commission
            zs_ads = zomato_metrics.ads + swiggy_metrics.ads
            zs_cash_in_bank = zomato_metrics.cash_in_bank + swiggy_metrics.cash_in_bank
            zs_discount_pct = fmt_pct((zs_total_discount / zs_subtotal * 100) if zs_subtotal > 0 else 0.0)
            zs_commission_pct = fmt_pct((zs_commission / zs_sales_after_discount * 100) if zs_sales_after_discount > 0 else 0.0)
            zs_ads_pct = fmt_pct((zs_ads / zs_subtotal * 100) if zs_subtotal > 0 else 0.0)
            zs_payout_pct = fmt_pct((zs_cash_in_bank / zs_subtotal * 100) if zs_subtotal > 0 else 0.0)
            zs_visibility = fmt_pct(zomato_metrics.visibility)
            zs_kpt = round((zomato_metrics.kpt + swiggy_metrics.kpt) / 2, 1) if (zomato_metrics.kpt > 0 and swiggy_metrics.kpt > 0) else (zomato_metrics.kpt or swiggy_metrics.kpt)
            zs_impressions = zomato_metrics.impressions + swiggy_metrics.impressions
            zs_i2m = fmt_pct(zomato_metrics.i2m)
            zs_menu_opens = zomato_metrics.menu_opens + swiggy_metrics.menu_opens
            zs_c2o = fmt_pct(zomato_metrics.c2o)
            zs_m2o = fmt_pct(zomato_metrics.m2o)
            zs_mx_rejections = zomato_metrics.mx_rejections + swiggy_metrics.mx_rejections
        else:
            zs_orders = zomato_metrics.orders
            zs_subtotal = zomato_metrics.subtotal
            zs_total_discount = zomato_metrics.total_discount
            zs_sales_after_discount = zomato_metrics.sales_after_discount
            zs_net_order_value = zomato_metrics.net_order_value
            zs_packaging = zomato_metrics.packaging_charges
            zs_commission = zomato_metrics.commission
            zs_ads = zomato_metrics.ads
            zs_cash_in_bank = zomato_metrics.cash_in_bank
            zs_discount_pct = fmt_pct(zomato_metrics.discount_pct)
            zs_commission_pct = fmt_pct(zomato_metrics.commission_pct)
            zs_ads_pct = fmt_pct(zomato_metrics.ads_pct)
            zs_payout_pct = fmt_pct(zomato_metrics.payout_pct)
            zs_visibility = fmt_pct(zomato_metrics.visibility)
            zs_kpt = zomato_metrics.kpt
            zs_impressions = zomato_metrics.impressions
            zs_i2m = fmt_pct(zomato_metrics.i2m)
            zs_menu_opens = zomato_metrics.menu_opens
            zs_c2o = fmt_pct(zomato_metrics.c2o)
            zs_m2o = fmt_pct(zomato_metrics.m2o)
            zs_mx_rejections = zomato_metrics.mx_rejections

        # Row Definitions
        rows_config = [
            {"name": "Orders", "z_val": str(zomato_metrics.orders), "zs_val": str(zs_orders), "highlight": False, "bold": False},
            {"name": "Subtotal", "z_val": str(zomato_metrics.subtotal), "zs_val": str(zs_subtotal), "highlight": False, "bold": False},
            {"name": "Total Discount", "z_val": str(zomato_metrics.total_discount), "zs_val": str(zs_total_discount), "highlight": False, "bold": False},
            {"name": "Sales after discount", "z_val": str(zomato_metrics.sales_after_discount), "zs_val": str(zs_sales_after_discount), "highlight": False, "bold": False},
            {"name": "Net order value", "z_val": str(zomato_metrics.net_order_value), "zs_val": str(zs_net_order_value), "highlight": False, "bold": False},
            {"name": "Packaging Charges", "z_val": str(zomato_metrics.packaging_charges), "zs_val": str(zs_packaging), "highlight": False, "bold": False},
            {"name": "Commission", "z_val": str(zomato_metrics.commission), "zs_val": str(zs_commission), "highlight": False, "bold": False},
            {"name": "ads", "z_val": str(zomato_metrics.ads), "zs_val": str(zs_ads), "highlight": False, "bold": False},
            {"name": "Cash in Bank", "z_val": str(zomato_metrics.cash_in_bank), "zs_val": str(zs_cash_in_bank), "highlight": True, "bold": True},
            {"name": "Discount %", "z_val": fmt_pct(zomato_metrics.discount_pct), "zs_val": zs_discount_pct, "highlight": False, "bold": False},
            {"name": "Commission %", "z_val": fmt_pct(zomato_metrics.commission_pct), "zs_val": zs_commission_pct, "highlight": False, "bold": False},
            {"name": "Ads %", "z_val": fmt_pct(zomato_metrics.ads_pct), "zs_val": zs_ads_pct, "highlight": False, "bold": False},
            {"name": "Payout %", "z_val": fmt_pct(zomato_metrics.payout_pct), "zs_val": zs_payout_pct, "highlight": True, "bold": True},
            {"name": "Visibility", "z_val": fmt_pct(zomato_metrics.visibility), "zs_val": zs_visibility, "highlight": False, "bold": False},
            {"name": "KPT", "z_val": str(zomato_metrics.kpt), "zs_val": str(zs_kpt), "highlight": False, "bold": False},
            {"name": "Impressions", "z_val": str(zomato_metrics.impressions), "zs_val": str(zs_impressions), "highlight": False, "bold": False},
            {"name": "I2M", "z_val": fmt_pct(zomato_metrics.i2m), "zs_val": zs_i2m, "highlight": False, "bold": False},
            {"name": "Menu Opens", "z_val": str(zomato_metrics.menu_opens), "zs_val": str(zs_menu_opens), "highlight": False, "bold": False},
            {"name": "C2O", "z_val": fmt_pct(zomato_metrics.c2o), "zs_val": zs_c2o, "highlight": False, "bold": False},
            {"name": "M2O", "z_val": fmt_pct(zomato_metrics.m2o), "zs_val": zs_m2o, "highlight": False, "bold": True},
            {"name": "Mx Rejections", "z_val": str(zomato_metrics.mx_rejections), "zs_val": str(zs_mx_rejections), "highlight": False, "bold": False},
        ]

        title_text = f"{restaurant_name} (ZID: {restaurant_id})"

        # Prepare grid data for batch update
        table_values = [
            [title_text, "", "", ""],
            [date_range_label, "", "", ""],
            [report_title, "", "", ""],
            ["Line Items", "Zomato", "Swiggy", "Z+S"],
        ]

        for item in rows_config:
            swiggy_val = ""
            if swiggy_metrics:
                swiggy_val = str(getattr(swiggy_metrics, item["name"].lower().replace(" ", "_"), ""))
            table_values.append([item["name"], item["z_val"], swiggy_val, item["zs_val"]])

        # Write cell values using gspread update
        def col_idx_to_a1(c_idx: int) -> str:
            result = ""
            c_idx += 1
            while c_idx > 0:
                c_idx, remainder = divmod(c_idx - 1, 26)
                result = chr(65 + remainder) + result
            return result

        start_col_a1 = col_idx_to_a1(start_col)
        end_col_a1 = col_idx_to_a1(end_col - 1)
        cell_range = f"{start_col_a1}1:{end_col_a1}25"
        ws.update(range_name=cell_range, values=table_values)

        # Build formatting requests
        requests = []

        # 1. Merges for Row 1, Row 2, Row 3
        for r_idx in range(3):
            requests.append({
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": r_idx,
                        "endRowIndex": r_idx + 1,
                        "startColumnIndex": start_col,
                        "endColumnIndex": end_col,
                    },
                    "mergeType": "MERGE_ALL",
                }
            })

        # 2. Border style for all cells in table
        thin_border = {
            "style": "SOLID",
            "width": 1,
            "color": self.COLOR_BORDER,
        }
        requests.append({
            "updateBorders": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 25,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "top": thin_border,
                "bottom": thin_border,
                "left": thin_border,
                "right": thin_border,
                "innerHorizontal": thin_border,
                "innerVertical": thin_border,
            }
        })

        # 3. Format Row 1 & 2 (Title & Date Range)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 2,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": self.COLOR_TITLE_BG,
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {
                            "fontSize": 11,
                            "bold": True,
                        },
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)",
            }
        })

        # 4. Format Row 3 (Report Title / "Weekly Report")
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 2,
                    "endRowIndex": 3,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": self.COLOR_REPORT_TYPE_BG,
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {
                            "fontSize": 11,
                            "bold": True,
                            "foregroundColor": self.COLOR_REPORT_TYPE_TXT,
                        },
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)",
            }
        })

        # 5. Format Row 4 (Headers)
        headers_bg = [
            self.COLOR_LINE_ITEMS_BG,
            self.COLOR_ZOMATO_BG,
            self.COLOR_SWIGGY_BG,
            self.COLOR_ZS_BG,
        ]
        for c_offset, bg_color in enumerate(headers_bg):
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 3,
                        "endRowIndex": 4,
                        "startColumnIndex": start_col + c_offset,
                        "endColumnIndex": start_col + c_offset + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": bg_color,
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {
                                "bold": True,
                                "italic": True,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)",
                }
            })

        # 6. Format Data Rows (Rows 5-25, 0-indexed rows 4-25)
        # Default data cells formatting (center alignment, normal font)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 4,
                    "endRowIndex": 25,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {
                            "fontSize": 10,
                            "bold": False,
                        },
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat)",
            }
        })

        # Specific highlighted/bold rows
        for idx, item in enumerate(rows_config):
            r_num = 4 + idx  # 0-indexed row
            if item["highlight"]:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": r_num,
                            "endRowIndex": r_num + 1,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": self.COLOR_HIGHLIGHT_ROW,
                                "textFormat": {
                                    "bold": True,
                                },
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                })
            elif item["bold"]:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": r_num,
                            "endRowIndex": r_num + 1,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True,
                                },
                            }
                        },
                        "fields": "userEnteredFormat(textFormat)",
                    }
                })

        # 7. Set Column Dimensions (Widths)
        # Line items column width: 170px
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": start_col,
                    "endIndex": start_col + 1,
                },
                "properties": {"pixelSize": 170},
                "fields": "pixelSize",
            }
        })
        # Data columns (Zomato, Swiggy, Z+S) width: 110px
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": start_col + 1,
                    "endIndex": end_col,
                },
                "properties": {"pixelSize": 110},
                "fields": "pixelSize",
            }
        })

        # Spacer column width (if next column exists): 30px
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": end_col,
                    "endIndex": end_col + 1,
                },
                "properties": {"pixelSize": 30},
                "fields": "pixelSize",
            }
        })

        # Execute batch update
        sh.batch_update({"requests": requests})

        tab_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit#gid={sheet_id}"
        print(f"\n[+] Successfully updated Google Sheet tab '{worksheet_name}': {tab_url}")
        return tab_url
