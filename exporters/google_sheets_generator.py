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
        date_range_label: str = "Weekly Report",
        report_title: str = "Weekly Report",
        worksheet_name: str = DEFAULT_WORKSHEET_NAME,
        start_col: Optional[int] = None,
        start_row: int = 0,
    ) -> str:
        """
        Generates and formats the weekly report table in the Google Sheet.
        Uses live spreadsheet formulas in the Z+S column referencing Zomato and Swiggy columns.
        """
        sh = self._get_spreadsheet()
        ws = self.get_or_create_worksheet(worksheet_name)
        sheet_id = ws.id

        if start_col is None:
            start_col = self._find_next_start_column(ws)

        end_col = start_col + 4  # 4 columns for table (Line Items, Zomato, Swiggy, Z+S)

        # Helper to convert 0-indexed column number to A1 notation
        def col_idx_to_a1(c_idx: int) -> str:
            result = ""
            c_idx += 1
            while c_idx > 0:
                c_idx, remainder = divmod(c_idx - 1, 26)
                result = chr(65 + remainder) + result
            return result

        # Ensure sheet has enough columns
        current_cols = ws.col_count
        if current_cols < end_col + 2:
            needed = (end_col + 5) - current_cols
            ws.add_cols(needed)

        has_z = zomato_metrics is not None
        has_s = swiggy_metrics is not None
        zm = zomato_metrics or PlatformMetrics()
        sm = swiggy_metrics or PlatformMetrics()

        def fmt_pct(val: float) -> str:
            if val == 0.0 or val is None:
                return "0.00%"
            v = float(val)
            if 0 < v <= 1.0:
                v = v * 100.0
            return f"{v:.2f}%"

        def fmt_int(val: Any) -> Any:
            if val is None or val == "":
                return 0
            try:
                v = float(val)
                return int(round(v))
            except (ValueError, TypeError):
                return val

        z_col = col_idx_to_a1(start_col + 1)
        s_col = col_idx_to_a1(start_col + 2)
        zs_col = col_idx_to_a1(start_col + 3)

        r_base = start_row + 5  # Row 1-3 headers, Row 4 column headers, Row 5+ data
        r_orders = r_base + 0
        r_subtotal = r_base + 1
        r_discount = r_base + 2
        r_sales = r_base + 3
        r_nov = r_base + 4
        r_pkg = r_base + 5
        r_comm = r_base + 6
        r_ads = r_base + 7
        r_cib = r_base + 8
        r_disc_pct = r_base + 9
        r_comm_pct = r_base + 10
        r_ads_pct = r_base + 11
        r_payout_pct = r_base + 12
        r_vis = r_base + 13
        r_kpt = r_base + 14
        r_imp = r_base + 15
        r_i2m = r_base + 16
        r_menu = r_base + 17
        r_c2o = r_base + 18
        r_m2o = r_base + 19
        r_mx = r_base + 20

        # Row Definitions with dynamic formulas for Z+S
        rows_config = [
            {"name": "Orders", "format_type": "int", "z_val": fmt_int(zm.orders) if has_z else "", "s_val": fmt_int(sm.orders) if has_s else "", "zs_val": f"={z_col}{r_orders}+{s_col}{r_orders}", "highlight": False, "bold": False},
            {"name": "Subtotal", "format_type": "int", "z_val": fmt_int(zm.subtotal) if has_z else "", "s_val": fmt_int(sm.subtotal) if has_s else "", "zs_val": f"={z_col}{r_subtotal}+{s_col}{r_subtotal}", "highlight": False, "bold": False},
            {"name": "Total Discount", "format_type": "int", "z_val": fmt_int(zm.total_discount) if has_z else "", "s_val": fmt_int(sm.total_discount) if has_s else "", "zs_val": f"={z_col}{r_discount}+{s_col}{r_discount}", "highlight": False, "bold": False},
            {"name": "Sales after discount", "format_type": "int", "z_val": fmt_int(zm.sales_after_discount) if has_z else "", "s_val": fmt_int(sm.sales_after_discount) if has_s else "", "zs_val": f"={z_col}{r_sales}+{s_col}{r_sales}", "highlight": False, "bold": False},
            {"name": "Net order value", "format_type": "dec", "z_val": fmt_int(zm.net_order_value) if has_z else "", "s_val": fmt_int(sm.net_order_value) if has_s else "", "zs_val": f"=IFERROR(ROUND({zs_col}{r_sales}/{zs_col}{r_orders}, 2), 0)", "highlight": False, "bold": False},
            {"name": "Packaging Charges", "format_type": "int", "z_val": fmt_int(zm.packaging_charges) if has_z else "", "s_val": fmt_int(sm.packaging_charges) if has_s else "", "zs_val": f"={z_col}{r_pkg}+{s_col}{r_pkg}", "highlight": False, "bold": False},
            {"name": "Commission", "format_type": "int", "z_val": fmt_int(zm.commission) if has_z else "", "s_val": fmt_int(sm.commission) if has_s else "", "zs_val": f"={z_col}{r_comm}+{s_col}{r_comm}", "highlight": False, "bold": False},
            {"name": "ads", "format_type": "int", "z_val": fmt_int(zm.ads) if has_z else "", "s_val": fmt_int(sm.ads) if has_s else "", "zs_val": f"={z_col}{r_ads}+{s_col}{r_ads}", "highlight": False, "bold": False},
            {"name": "Cash in Bank", "format_type": "int", "z_val": fmt_int(zm.cash_in_bank) if has_z else "", "s_val": fmt_int(sm.cash_in_bank) if has_s else "", "zs_val": f"={z_col}{r_cib}+{s_col}{r_cib}", "highlight": True, "bold": True},
            {"name": "Discount %", "format_type": "pct", "z_val": fmt_pct(zm.discount_pct) if has_z else "", "s_val": fmt_pct(sm.discount_pct) if has_s else "", "zs_val": f"=IFERROR({zs_col}{r_discount}/{zs_col}{r_subtotal}, 0)", "highlight": False, "bold": False},
            {"name": "Commission %", "format_type": "pct", "z_val": fmt_pct(zm.commission_pct) if has_z else "", "s_val": fmt_pct(sm.commission_pct) if has_s else "", "zs_val": f"=IFERROR({zs_col}{r_comm}/{zs_col}{r_sales}, 0)", "highlight": False, "bold": False},
            {"name": "Ads %", "format_type": "pct", "z_val": fmt_pct(zm.ads_pct) if has_z else "", "s_val": fmt_pct(sm.ads_pct) if has_s else "", "zs_val": f"=IFERROR({zs_col}{r_ads}/{zs_col}{r_subtotal}, 0)", "highlight": False, "bold": False},
            {"name": "Payout %", "format_type": "pct", "z_val": fmt_pct(zm.payout_pct) if has_z else "", "s_val": fmt_pct(sm.payout_pct) if has_s else "", "zs_val": f"=IFERROR({zs_col}{r_cib}/{zs_col}{r_subtotal}, 0)", "highlight": True, "bold": True},
            {"name": "Visibility", "format_type": "pct", "z_val": fmt_pct(zm.visibility) if has_z else "", "s_val": fmt_pct(sm.visibility) if has_s else "", "zs_val": f"=IFERROR(AVERAGE({z_col}{r_vis}, {s_col}{r_vis}), 0)", "highlight": False, "bold": False},
            {"name": "KPT", "format_type": "kpt", "z_val": fmt_int(zm.kpt) if has_z else "", "s_val": fmt_int(sm.kpt) if has_s else "", "zs_val": f"=IFERROR(AVERAGE({z_col}{r_kpt}, {s_col}{r_kpt}), 0)", "highlight": False, "bold": False},
            {"name": "Impressions", "format_type": "int", "z_val": fmt_int(zm.impressions) if has_z else "", "s_val": fmt_int(sm.impressions) if has_s else "", "zs_val": f"={z_col}{r_imp}+{s_col}{r_imp}", "highlight": False, "bold": False},
            {"name": "I2M", "format_type": "pct", "z_val": fmt_pct(zm.i2m) if has_z else "", "s_val": fmt_pct(sm.i2m) if has_s else "", "zs_val": f"=IFERROR(AVERAGE({z_col}{r_i2m}, {s_col}{r_i2m}), 0)", "highlight": False, "bold": False},
            {"name": "Menu Opens", "format_type": "int", "z_val": fmt_int(zm.menu_opens) if has_z else "", "s_val": fmt_int(sm.menu_opens) if has_s else "", "zs_val": f"={z_col}{r_menu}+{s_col}{r_menu}", "highlight": False, "bold": False},
            {"name": "C2O", "format_type": "pct", "z_val": fmt_pct(zm.c2o) if has_z else "", "s_val": fmt_pct(sm.c2o) if has_s else "", "zs_val": f"=IFERROR(AVERAGE({z_col}{r_c2o}, {s_col}{r_c2o}), 0)", "highlight": False, "bold": False},
            {"name": "M2O", "format_type": "pct", "z_val": fmt_pct(zm.m2o) if has_z else "", "s_val": fmt_pct(sm.m2o) if has_s else "", "zs_val": f"=IFERROR(AVERAGE({z_col}{r_m2o}, {s_col}{r_m2o}), 0)", "highlight": False, "bold": True},
            {"name": "Mx Rejections", "format_type": "int", "z_val": fmt_int(zm.mx_rejections) if has_z else "", "s_val": fmt_int(sm.mx_rejections) if has_s else "", "zs_val": f"={z_col}{r_mx}+{s_col}{r_mx}", "highlight": False, "bold": False},
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

        start_col_a1 = col_idx_to_a1(start_col)
        end_col_a1 = col_idx_to_a1(end_col - 1)
        start_row_a1 = start_row + 1
        end_row_a1 = start_row + 25
        cell_range = f"{start_col_a1}{start_row_a1}:{end_col_a1}{end_row_a1}"
        ws.update(values=table_values, range_name=cell_range, raw=False)

        # Build formatting requests
        requests = []

        # 1. Merges for Row 1, Row 2, Row 3
        for r_idx in range(3):
            requests.append({
                "mergeCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row + r_idx,
                        "endRowIndex": start_row + r_idx + 1,
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

        # 6. Format Data Rows (Rows 5-25)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row + 4,
                    "endRowIndex": start_row + 25,
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

        # Number formatting & highlights per data row
        for idx, item in enumerate(rows_config):
            r_num = start_row + 4 + idx  # 0-indexed row

            # Apply specific numberFormat
            num_fmt = None
            fmt_type = item.get("format_type")
            if fmt_type == "pct":
                num_fmt = {"type": "PERCENT", "pattern": "0.00%"}
            elif fmt_type == "int":
                num_fmt = {"type": "NUMBER", "pattern": "#,##0"}
            elif fmt_type == "dec":
                num_fmt = {"type": "NUMBER", "pattern": "#,##0.00"}
            elif fmt_type == "kpt":
                num_fmt = {"type": "NUMBER", "pattern": "0.0"}

            if num_fmt:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": r_num,
                            "endRowIndex": r_num + 1,
                            "startColumnIndex": start_col + 1,
                            "endColumnIndex": end_col,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": num_fmt,
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    }
                })

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
