import os
from pathlib import Path
from typing import Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from processors.metric_calculator import PlatformMetrics
from config import REPORTS_DIR, DEFAULT_RESTAURANT_NAME, DEFAULT_RESTAURANT_ID


class ExcelReportGenerator:
    """Generates styled Excel reports matching the exact user template."""

    # Colors (HEX without #)
    COLOR_TITLE_BG = "CCA9C2"       # Light mauve / pink
    COLOR_REPORT_TYPE_BG = "434343" # Dark grey
    COLOR_REPORT_TYPE_TXT = "FFFFFF"# White text
    COLOR_LINE_ITEMS_BG = "8EA6B4"  # Muted teal/blue
    COLOR_ZOMATO_BG = "D32F2F"      # Zomato Red
    COLOR_SWIGGY_BG = "E69138"      # Swiggy Orange
    COLOR_ZS_BG = "A9D18E"          # Light Green
    COLOR_HIGHLIGHT_ROW = "F9CB9C"  # Peach / Light Orange for Cash in Bank & Payout %
    COLOR_BORDER = "000000"         # Black

    def __init__(self, output_dir: Path = REPORTS_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        zomato_metrics: PlatformMetrics,
        swiggy_metrics: Optional[PlatformMetrics] = None,
        restaurant_name: str = DEFAULT_RESTAURANT_NAME,
        restaurant_id: str = DEFAULT_RESTAURANT_ID,
        date_range_label: str = "24 - 30 Aug'26",
        report_title: str = "Weekly Report",
        filename: Optional[str] = None,
    ) -> Path:
        """Creates the formatted Excel workbook."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Weekly Report"

        # Ensure grid lines are visible
        ws.views.sheetView[0].showGridLines = True

        # Define Common Styles (Font: Arial)
        font_name = "Arial"
        font_title = Font(name=font_name, size=11, bold=True)
        font_report_type = Font(name=font_name, size=11, bold=True, color=self.COLOR_REPORT_TYPE_TXT)
        font_col_header = Font(name=font_name, size=11, bold=True, italic=True)
        font_regular = Font(name=font_name, size=10)
        font_bold = Font(name=font_name, size=10, bold=True)

        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        thin_side = Side(border_style="thin", color=self.COLOR_BORDER)
        border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        fill_title = PatternFill(start_color=self.COLOR_TITLE_BG, end_color=self.COLOR_TITLE_BG, fill_type="solid")
        fill_report_type = PatternFill(start_color=self.COLOR_REPORT_TYPE_BG, end_color=self.COLOR_REPORT_TYPE_BG, fill_type="solid")
        fill_line_items = PatternFill(start_color=self.COLOR_LINE_ITEMS_BG, end_color=self.COLOR_LINE_ITEMS_BG, fill_type="solid")
        fill_zomato = PatternFill(start_color=self.COLOR_ZOMATO_BG, end_color=self.COLOR_ZOMATO_BG, fill_type="solid")
        fill_swiggy = PatternFill(start_color=self.COLOR_SWIGGY_BG, end_color=self.COLOR_SWIGGY_BG, fill_type="solid")
        fill_zs = PatternFill(start_color=self.COLOR_ZS_BG, end_color=self.COLOR_ZS_BG, fill_type="solid")
        fill_highlight = PatternFill(start_color=self.COLOR_HIGHLIGHT_ROW, end_color=self.COLOR_HIGHLIGHT_ROW, fill_type="solid")

        # Row 1: Restaurant Name and ID
        title_text = f"{restaurant_name} (Id: {restaurant_id})"
        ws.merge_cells("A1:D1")
        ws["A1"] = title_text
        ws["A1"].font = font_title
        ws["A1"].alignment = align_center

        # Row 2: Date Range
        ws.merge_cells("A2:D2")
        ws["A2"] = date_range_label
        ws["A2"].font = font_title
        ws["A2"].alignment = align_center

        # Row 3: Report Type (Weekly Report)
        ws.merge_cells("A3:D3")
        ws["A3"] = report_title
        ws["A3"].font = font_report_type
        ws["A3"].alignment = align_center

        # Apply fills and borders for headers
        for r in range(1, 4):
            for c in range(1, 5):
                cell = ws.cell(row=r, column=c)
                cell.border = border_all
                if r in [1, 2]:
                    cell.fill = fill_title
                elif r == 3:
                    cell.fill = fill_report_type

        # Row 4: Column Headers
        headers = [
            ("Line Items", fill_line_items, font_col_header),
            ("Zomato", fill_zomato, font_col_header),
            ("Swiggy", fill_swiggy, font_col_header),
            ("Z+S", fill_zs, font_col_header),
        ]
        for col_idx, (text, fill, font) in enumerate(headers, start=1):
            cell = ws.cell(row=4, column=col_idx, value=text)
            cell.font = font
            cell.fill = fill
            cell.alignment = align_center
            cell.border = border_all

        def fmt_pct(val: float) -> str:
            """Formats percentage values (0-100 scale or 0-1 scale) as 'X.XX%' string."""
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

        # Row Definitions: (Line Item Name, type, z_val, zs_val, highlight, bold)
        rows_config = [
            # 5
            {"name": "Orders", "type": "int", "z_val": zomato_metrics.orders, "zs_val": zs_orders, "highlight": False, "bold": False},
            # 6
            {"name": "Subtotal", "type": "num", "z_val": zomato_metrics.subtotal, "zs_val": zs_subtotal, "highlight": False, "bold": False},
            # 7
            {"name": "Total Discount", "type": "num", "z_val": zomato_metrics.total_discount, "zs_val": zs_total_discount, "highlight": False, "bold": False},
            # 8
            {"name": "Sales after discount", "type": "num", "z_val": zomato_metrics.sales_after_discount, "zs_val": zs_sales_after_discount, "highlight": False, "bold": False},
            # 9
            {"name": "Net order value", "type": "num", "z_val": zomato_metrics.net_order_value, "zs_val": zs_net_order_value, "highlight": False, "bold": False},
            # 10
            {"name": "Packaging Charges", "type": "num", "z_val": zomato_metrics.packaging_charges, "zs_val": zs_packaging, "highlight": False, "bold": False},
            # 11
            {"name": "Commission", "type": "num", "z_val": zomato_metrics.commission, "zs_val": zs_commission, "highlight": False, "bold": False},
            # 12
            {"name": "ads", "type": "num", "z_val": zomato_metrics.ads, "zs_val": zs_ads, "highlight": False, "bold": False},
            # 13: Cash in Bank (Highlighted)
            {"name": "Cash in Bank", "type": "num", "z_val": zomato_metrics.cash_in_bank, "zs_val": zs_cash_in_bank, "highlight": True, "bold": True},
            # 14
            {"name": "Discount %", "type": "str", "z_val": fmt_pct(zomato_metrics.discount_pct), "zs_val": zs_discount_pct, "highlight": False, "bold": False},
            # 15
            {"name": "Commission %", "type": "str", "z_val": fmt_pct(zomato_metrics.commission_pct), "zs_val": zs_commission_pct, "highlight": False, "bold": False},
            # 16
            {"name": "Ads %", "type": "str", "z_val": fmt_pct(zomato_metrics.ads_pct), "zs_val": zs_ads_pct, "highlight": False, "bold": False},
            # 17: Payout % (Highlighted)
            {"name": "Payout %", "type": "str", "z_val": fmt_pct(zomato_metrics.payout_pct), "zs_val": zs_payout_pct, "highlight": True, "bold": True},
            # 18
            {"name": "Visibility", "type": "str", "z_val": fmt_pct(zomato_metrics.visibility), "zs_val": zs_visibility, "highlight": False, "bold": False},
            # 19
            {"name": "KPT", "type": "int", "z_val": zomato_metrics.kpt, "zs_val": zs_kpt, "highlight": False, "bold": False},
            # 20
            {"name": "Impressions", "type": "num", "z_val": zomato_metrics.impressions, "zs_val": zs_impressions, "highlight": False, "bold": False},
            # 21
            {"name": "I2M", "type": "str", "z_val": fmt_pct(zomato_metrics.i2m), "zs_val": zs_i2m, "highlight": False, "bold": False},
            # 22
            {"name": "Menu Opens", "type": "num", "z_val": zomato_metrics.menu_opens, "zs_val": zs_menu_opens, "highlight": False, "bold": False},
            # 23
            {"name": "C2O", "type": "str", "z_val": fmt_pct(zomato_metrics.c2o), "zs_val": zs_c2o, "highlight": False, "bold": False},
            # 24
            {"name": "M2O", "type": "str", "z_val": fmt_pct(zomato_metrics.m2o), "zs_val": zs_m2o, "highlight": False, "bold": True},
            # 25
            {"name": "Mx Rejections", "type": "int", "z_val": zomato_metrics.mx_rejections, "zs_val": zs_mx_rejections, "highlight": False, "bold": False},
        ]

        # Populate rows
        for idx, item in enumerate(rows_config, start=5):
            # Line item name (Col A)
            cell_a = ws.cell(row=idx, column=1, value=item["name"])
            cell_a.font = font_bold if item["bold"] else font_regular
            cell_a.alignment = align_center
            cell_a.border = border_all
            if item["highlight"]:
                cell_a.fill = fill_highlight

            # Zomato value (Col B) - Direct value
            cell_b = ws.cell(row=idx, column=2, value=item["z_val"])
            cell_b.font = font_bold if item["bold"] else font_regular
            cell_b.alignment = align_center
            cell_b.border = border_all
            if item["highlight"]:
                cell_b.fill = fill_highlight

            # Swiggy value (Col C - placeholder / future support)
            swiggy_val = 0
            if swiggy_metrics:
                swiggy_val = getattr(swiggy_metrics, item["name"].lower().replace(" ", "_"), 0)
            cell_c = ws.cell(row=idx, column=3, value=swiggy_val if swiggy_metrics else "")
            cell_c.font = font_bold if item["bold"] else font_regular
            cell_c.alignment = align_center
            cell_c.border = border_all
            if item["highlight"]:
                cell_c.fill = fill_highlight

            # Z+S value (Col D) - Direct value
            cell_d = ws.cell(row=idx, column=4, value=item["zs_val"])
            cell_d.font = font_bold if item["bold"] else font_regular
            cell_d.alignment = align_center
            cell_d.border = border_all
            if item["highlight"]:
                cell_d.fill = fill_highlight

            # Number Formatting
            format_type = item["type"]
            for c_idx in [2, 3, 4]:
                c = ws.cell(row=idx, column=c_idx)
                if format_type == "int":
                    c.number_format = "#,##0"
                elif format_type == "num":
                    c.number_format = "#,##0"
                elif format_type == "str":
                    c.number_format = "@"

        # Set Column Widths
        column_widths = {
            "A": 24,
            "B": 16,
            "C": 16,
            "D": 16,
        }
        for col_letter, width in column_widths.items():
            ws.column_dimensions[col_letter].width = width

        # Set Row Heights
        for r in range(1, 26):
            ws.row_dimensions[r].height = 20

        # Save workbook
        if not filename:
            clean_date = date_range_label.replace(" ", "_").replace("'", "").replace("-", "_")
            filename = f"Report_{restaurant_name.replace(' ', '_')}_{clean_date}.xlsx"

        output_path = self.output_dir / filename
        wb.save(output_path)
        print(f"\n[+] Successfully generated Excel report: {output_path}")
        return output_path
