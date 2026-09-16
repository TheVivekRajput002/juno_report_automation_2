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
        zomato_metrics: Optional[PlatformMetrics] = None,
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

        def fmt_int(val: Any) -> Any:
            """Formats numeric values as rounded integers with no decimal places."""
            if val is None or val == "":
                return ""
            try:
                v = float(val)
                return int(round(v))
            except (ValueError, TypeError):
                return val

        has_z = zomato_metrics is not None
        has_s = swiggy_metrics is not None
        zm = zomato_metrics or PlatformMetrics()
        sm = swiggy_metrics or PlatformMetrics()

        # Calculate Z+S combined metrics
        if has_z and has_s:
            zs_orders = zm.orders + sm.orders
            zs_subtotal = round(zm.subtotal + sm.subtotal, 2)
            zs_total_discount = round(zm.total_discount + sm.total_discount, 2)
            zs_sales_after_discount = round(zs_subtotal - zs_total_discount, 2)
            zs_net_order_value = round(zs_sales_after_discount / zs_orders, 2) if zs_orders > 0 else 0.0
            zs_packaging = round(zm.packaging_charges + sm.packaging_charges, 2)
            zs_commission = round(zm.commission + sm.commission, 2)
            zs_ads = round(zm.ads + sm.ads, 2)
            zs_cash_in_bank = round(zm.cash_in_bank + sm.cash_in_bank, 2)
            zs_discount_pct = fmt_pct((zs_total_discount / zs_subtotal * 100) if zs_subtotal > 0 else 0.0)
            zs_commission_pct = fmt_pct((zs_commission / zs_sales_after_discount * 100) if zs_sales_after_discount > 0 else 0.0)
            zs_ads_pct = fmt_pct((zs_ads / zs_subtotal * 100) if zs_subtotal > 0 else 0.0)
            zs_payout_pct = fmt_pct((zs_cash_in_bank / zs_subtotal * 100) if zs_subtotal > 0 else 0.0)
            zs_visibility = fmt_pct((zm.visibility + sm.visibility) / 2 if (zm.visibility > 0 and sm.visibility > 0) else (zm.visibility or sm.visibility))
            zs_kpt = round((zm.kpt + sm.kpt) / 2, 1) if (zm.kpt > 0 and sm.kpt > 0) else (zm.kpt or sm.kpt)
            zs_impressions = zm.impressions + sm.impressions
            zs_i2m = fmt_pct((zm.i2m + sm.i2m) / 2 if (zm.i2m > 0 and sm.i2m > 0) else (zm.i2m or sm.i2m))
            zs_menu_opens = zm.menu_opens + sm.menu_opens
            zs_c2o = fmt_pct((zm.c2o + sm.c2o) / 2 if (zm.c2o > 0 and sm.c2o > 0) else (zm.c2o or sm.c2o))
            zs_m2o = fmt_pct((zm.m2o + sm.m2o) / 2 if (zm.m2o > 0 and sm.m2o > 0) else (zm.m2o or sm.m2o))
            zs_mx_rejections = zm.mx_rejections + sm.mx_rejections
        elif has_s:
            zs_orders = sm.orders
            zs_subtotal = sm.subtotal
            zs_total_discount = sm.total_discount
            zs_sales_after_discount = sm.sales_after_discount
            zs_net_order_value = sm.net_order_value
            zs_packaging = sm.packaging_charges
            zs_commission = sm.commission
            zs_ads = sm.ads
            zs_cash_in_bank = sm.cash_in_bank
            zs_discount_pct = fmt_pct(sm.discount_pct)
            zs_commission_pct = fmt_pct(sm.commission_pct)
            zs_ads_pct = fmt_pct(sm.ads_pct)
            zs_payout_pct = fmt_pct(sm.payout_pct)
            zs_visibility = fmt_pct(sm.visibility)
            zs_kpt = sm.kpt
            zs_impressions = sm.impressions
            zs_i2m = fmt_pct(sm.i2m)
            zs_menu_opens = sm.menu_opens
            zs_c2o = fmt_pct(sm.c2o)
            zs_m2o = fmt_pct(sm.m2o)
            zs_mx_rejections = sm.mx_rejections
        else:
            zs_orders = zm.orders
            zs_subtotal = zm.subtotal
            zs_total_discount = zm.total_discount
            zs_sales_after_discount = zm.sales_after_discount
            zs_net_order_value = zm.net_order_value
            zs_packaging = zm.packaging_charges
            zs_commission = zm.commission
            zs_ads = zm.ads
            zs_cash_in_bank = zm.cash_in_bank
            zs_discount_pct = fmt_pct(zm.discount_pct)
            zs_commission_pct = fmt_pct(zm.commission_pct)
            zs_ads_pct = fmt_pct(zm.ads_pct)
            zs_payout_pct = fmt_pct(zm.payout_pct)
            zs_visibility = fmt_pct(zm.visibility)
            zs_kpt = zm.kpt
            zs_impressions = zm.impressions
            zs_i2m = fmt_pct(zm.i2m)
            zs_menu_opens = zm.menu_opens
            zs_c2o = fmt_pct(zm.c2o)
            zs_m2o = fmt_pct(zm.m2o)
            zs_mx_rejections = zm.mx_rejections

        # Row Definitions (All numeric values formatted as pure integers with no decimal places)
        rows_config = [
            {"name": "Orders", "z_val": fmt_int(zm.orders) if has_z else "", "s_val": fmt_int(sm.orders) if has_s else "", "zs_val": fmt_int(zs_orders), "highlight": False, "bold": False},
            {"name": "Subtotal", "z_val": fmt_int(zm.subtotal) if has_z else "", "s_val": fmt_int(sm.subtotal) if has_s else "", "zs_val": fmt_int(zs_subtotal), "highlight": False, "bold": False},
            {"name": "Total Discount", "z_val": fmt_int(zm.total_discount) if has_z else "", "s_val": fmt_int(sm.total_discount) if has_s else "", "zs_val": fmt_int(zs_total_discount), "highlight": False, "bold": False},
            {"name": "Sales after discount", "z_val": fmt_int(zm.sales_after_discount) if has_z else "", "s_val": fmt_int(sm.sales_after_discount) if has_s else "", "zs_val": fmt_int(zs_sales_after_discount), "highlight": False, "bold": False},
            {"name": "Net order value", "z_val": fmt_int(zm.net_order_value) if has_z else "", "s_val": fmt_int(sm.net_order_value) if has_s else "", "zs_val": fmt_int(zs_net_order_value), "highlight": False, "bold": False},
            {"name": "Packaging Charges", "z_val": fmt_int(zm.packaging_charges) if has_z else "", "s_val": fmt_int(sm.packaging_charges) if has_s else "", "zs_val": fmt_int(zs_packaging), "highlight": False, "bold": False},
            {"name": "Commission", "z_val": fmt_int(zm.commission) if has_z else "", "s_val": fmt_int(sm.commission) if has_s else "", "zs_val": fmt_int(zs_commission), "highlight": False, "bold": False},
            {"name": "ads", "z_val": fmt_int(zm.ads) if has_z else "", "s_val": fmt_int(sm.ads) if has_s else "", "zs_val": fmt_int(zs_ads), "highlight": False, "bold": False},
            {"name": "Cash in Bank", "z_val": fmt_int(zm.cash_in_bank) if has_z else "", "s_val": fmt_int(sm.cash_in_bank) if has_s else "", "zs_val": fmt_int(zs_cash_in_bank), "highlight": True, "bold": True},
            {"name": "Discount %", "z_val": fmt_pct(zm.discount_pct) if has_z else "", "s_val": fmt_pct(sm.discount_pct) if has_s else "", "zs_val": zs_discount_pct, "highlight": False, "bold": False},
            {"name": "Commission %", "z_val": fmt_pct(zm.commission_pct) if has_z else "", "s_val": fmt_pct(sm.commission_pct) if has_s else "", "zs_val": zs_commission_pct, "highlight": False, "bold": False},
            {"name": "Ads %", "z_val": fmt_pct(zm.ads_pct) if has_z else "", "s_val": fmt_pct(sm.ads_pct) if has_s else "", "zs_val": zs_ads_pct, "highlight": False, "bold": False},
            {"name": "Payout %", "z_val": fmt_pct(zm.payout_pct) if has_z else "", "s_val": fmt_pct(sm.payout_pct) if has_s else "", "zs_val": zs_payout_pct, "highlight": True, "bold": True},
            {"name": "Visibility", "z_val": fmt_pct(zm.visibility) if has_z else "", "s_val": fmt_pct(sm.visibility) if has_s else "", "zs_val": zs_visibility, "highlight": False, "bold": False},
            {"name": "KPT", "z_val": fmt_int(zm.kpt) if has_z else "", "s_val": fmt_int(sm.kpt) if has_s else "", "zs_val": fmt_int(zs_kpt), "highlight": False, "bold": False},
            {"name": "Impressions", "z_val": fmt_int(zm.impressions) if has_z else "", "s_val": fmt_int(sm.impressions) if has_s else "", "zs_val": fmt_int(zs_impressions), "highlight": False, "bold": False},
            {"name": "I2M", "z_val": fmt_pct(zm.i2m) if has_z else "", "s_val": fmt_pct(sm.i2m) if has_s else "", "zs_val": zs_i2m, "highlight": False, "bold": False},
            {"name": "Menu Opens", "z_val": fmt_int(zm.menu_opens) if has_z else "", "s_val": fmt_int(sm.menu_opens) if has_s else "", "zs_val": fmt_int(zs_menu_opens), "highlight": False, "bold": False},
            {"name": "C2O", "z_val": fmt_pct(zm.c2o) if has_z else "", "s_val": fmt_pct(sm.c2o) if has_s else "", "zs_val": zs_c2o, "highlight": False, "bold": False},
            {"name": "M2O", "z_val": fmt_pct(zm.m2o) if has_z else "", "s_val": fmt_pct(sm.m2o) if has_s else "", "zs_val": zs_m2o, "highlight": False, "bold": True},
            {"name": "Mx Rejections", "z_val": fmt_int(zm.mx_rejections) if has_z else "", "s_val": fmt_int(sm.mx_rejections) if has_s else "", "zs_val": fmt_int(zs_mx_rejections), "highlight": False, "bold": False},
        ]

        title_text = f"{restaurant_name} (Id: {restaurant_id})"

        # Prepare grid data for batch update
        table_values = [
            [title_text, "", "", ""],
            [date_range_label, "", "", ""],
            [report_title, "", "", ""],
            ["Line Items", "Zomato", "Swiggy", "Z+S"],
        ]

        for item in rows_config:
            table_values.append([item["name"], item["z_val"], item["s_val"], item["zs_val"]])

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
