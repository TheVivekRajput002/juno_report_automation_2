import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from processors.metric_calculator import clean_number


class ReportingParser:
    """
    Pure data parser for Zomato Business Reports matrix tables and body text fallbacks.
    Completely decoupled from Playwright/Browser state for easy isolated unit testing.
    """

    @staticmethod
    def find_target_column_index(
        headers: List[str],
        start_date: datetime,
        end_date: datetime,
        date_label: Optional[str] = None,
    ) -> int:
        """
        Finds which column index corresponds to the requested date range.
        Handles headers like:
        - 'Week 36 31 Aug - 6 Sep 2026'
        - 'Week 35 24 - 30 Aug 2026'
        - '24 - 30 Aug'
        """
        if not headers or len(headers) <= 1:
            return 1

        start_day = start_date.strftime("%d").lstrip("0")
        end_day = end_date.strftime("%d").lstrip("0")
        s_month = start_date.strftime("%b").lower()
        e_month = end_date.strftime("%b").lower()
        cal_week = start_date.isocalendar()[1]

        # Priority 1: Match by ISO Week number (e.g. 'Week 36')
        for idx, h in enumerate(headers):
            h_low = h.lower()
            if "vs" in h_low or "trend" in h_low or "comparison" in h_low:
                continue
            if re.search(rf"\bweek\s*{cal_week}\b", h, re.I):
                return idx

        # Priority 2: Exact date range regex
        for idx, h in enumerate(headers):
            h_low = h.lower()
            if "vs" in h_low or "trend" in h_low or "comparison" in h_low:
                continue
            if s_month != e_month:
                if re.search(rf"\b0?{start_day}\s*{s_month}\s*-\s*0?{end_day}\s*{e_month}\b", h_low) or \
                   re.search(rf"\b0?{start_day}\s*-\s*0?{end_day}\s*{e_month}\b", h_low):
                    return idx
            else:
                if re.search(rf"\b0?{start_day}\s*(?:{s_month})?\s*-\s*0?{end_day}\s*{s_month}\b", h_low):
                    return idx

        # Priority 3: date_label string matching
        if date_label:
            for idx, h in enumerate(headers):
                h_low = h.lower()
                if "vs" in h_low or "trend" in h_low or "comparison" in h_low:
                    continue
                if date_label.lower() in h_low:
                    return idx

        # Priority 4: Relative week offset calculation
        valid_indices = []
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in ["trend", "metric", "vs", "total", "comparison"]) and not re.search(r"\bweek\b|\d+", h_lower):
                continue
            if "week" in h_lower or any(m in h_lower for m in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
                valid_indices.append(idx)

        today = datetime.now()
        weeks_ago = max(1, int((today - start_date).days / 7))
        if len(valid_indices) >= weeks_ago:
            target_idx_pos = -(weeks_ago + 1)
            if abs(target_idx_pos) <= len(valid_indices):
                return valid_indices[target_idx_pos]

        if len(valid_indices) >= 2:
            return valid_indices[-2]
        elif valid_indices:
            return valid_indices[-1]

        return len(headers) - 1

    @staticmethod
    def extract_metrics_from_rows(
        rows: List[Dict[str, Any]],
        target_col_idx: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        date_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Maps table rows to internal metric keys using resolved column index."""
        extracted: Dict[str, Any] = {}

        for row_data in rows:
            metric_name = row_data.get("metricName", "").strip().lower()
            cells = row_data.get("cells", [])

            if target_col_idx < len(cells):
                cell_val = cells[target_col_idx]
            elif cells:
                cell_val = cells[-1]
            else:
                cell_val = ""

            # 1. Sales
            if metric_name == "sales" or metric_name == "total sales":
                extracted["sales"] = clean_number(cell_val)
                extracted["subtotal"] = clean_number(cell_val)
                extracted["sales_after_discount"] = clean_number(cell_val)

            # 2. Delivered / Total Orders in reporting table
            elif "delivered" in metric_name or metric_name == "orders" or "total orders" in metric_name:
                extracted["orders"] = clean_number(cell_val)
                extracted["reporting_orders"] = clean_number(cell_val)
                extracted["delivered_orders"] = clean_number(cell_val)

            # 3. Average Order Value
            elif "average order value" in metric_name or "aov" in metric_name:
                extracted["net_order_value"] = clean_number(cell_val)
                extracted["aov"] = clean_number(cell_val)

            # 4. Average rating
            elif "average rating" in metric_name or "rating" in metric_name:
                extracted["avg_rating"] = clean_number(cell_val)

            # 5. Bad orders
            elif "bad order" in metric_name:
                extracted["bad_orders"] = clean_number(cell_val)

            # 6. Total complaints
            elif "complaint" in metric_name:
                extracted["total_complaints"] = clean_number(cell_val)

            # 7. Lost sales
            elif "lost sales" in metric_name:
                extracted["lost_sales"] = clean_number(cell_val)

            # 8. Online % / Visibility
            elif ("online" in metric_name and "%" in metric_name) or "visibility" in metric_name:
                extracted["visibility"] = clean_number(cell_val)

            # 9. Kitchen preparation time (KPT)
            elif "kitchen" in metric_name or "prep" in metric_name or "kpt" in metric_name:
                extracted["kpt"] = clean_number(cell_val)

            # 10. Impressions to menu (I2M)
            elif ("impression" in metric_name or "i2m" in metric_name) and "menu" in metric_name:
                extracted["i2m"] = clean_number(cell_val)

            # 11. Impressions (Total impressions)
            elif "impression" in metric_name and "menu" not in metric_name:
                extracted["impressions"] = clean_number(cell_val)

            # 12. Menu to order (M2O)
            elif ("menu" in metric_name or "m2o" in metric_name) and "order" in metric_name:
                extracted["m2o"] = clean_number(cell_val)

            # 13. Cart to order (C2O)
            elif "cart to order" in metric_name or "cart" in metric_name:
                extracted["c2o"] = clean_number(cell_val)

            # 14. New users
            elif "new user" in metric_name:
                extracted["new_users"] = clean_number(cell_val)

            # 15. Sales from Ads
            elif "sales from ads" in metric_name or "ad sales" in metric_name:
                extracted["sales_from_ads"] = clean_number(cell_val)

            # 16. Gross sales from offers
            elif "gross sales from offers" in metric_name or "offers sales" in metric_name:
                extracted["gross_sales_from_offers"] = clean_number(cell_val)

            # 17. Rejections
            elif "rejection" in metric_name or "rejected" in metric_name:
                extracted["mx_rejections"] = clean_number(cell_val)

        return extracted

    @staticmethod
    def parse_reporting_text_matrix(
        body_text: str,
        target_col_idx: int,
        headers: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Robustly parses metric sequences from raw page text.
        Filters out comparison/trend delta badges (e.g., '▲ +9%', '▼ -3%', '-17.3%')
        and maps weekly metric columns strictly to the target week.
        """
        metrics: Dict[str, Any] = {}
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]

        # Identify all week columns present in body_text or headers
        week_headers = []
        for h in headers:
            h_clean = h.replace("\n", " ").strip()
            if any(k in h_clean.lower() for k in ["metric", "trend", "vs", "comparison"]) and not re.search(r"\bweek\b|\d+\s*-\s*\d+", h_clean, re.I):
                continue
            if re.search(r"week\s*\d+|\d+\s*-\s*\d+\s*[A-Za-z]+", h_clean, re.I):
                week_headers.append(h_clean)

        if not week_headers:
            week_headers = re.findall(r"(?:Week\s*\d+(?:\s*[\(\[]?[^\n\r\)\]]+[\)\]]?)?|\d+\s*-\s*\d+\s*[A-Za-z]+)", body_text, re.I)

        target_week_offset = None
        if start_date and end_date and week_headers:
            s_day = start_date.strftime("%d").lstrip("0")
            e_day = end_date.strftime("%d").lstrip("0")
            m_abbr = start_date.strftime("%b").lower()
            cal_week = start_date.isocalendar()[1]

            for w_idx, wh in enumerate(week_headers):
                wh_low = wh.lower()
                if (s_day in wh_low and e_day in wh_low and m_abbr in wh_low) or (f"week {cal_week}" in wh_low or f"week{cal_week}" in wh_low):
                    target_week_offset = w_idx
                    break

        def extract_clean_sequence(line_idx: int, is_pct_conversion: bool = False) -> Optional[float]:
            raw_tokens = []
            for j in range(line_idx + 1, min(line_idx + 40, len(lines))):
                val_str = lines[j]
                if any(k.lower() == val_str.lower() or val_str.lower().startswith(k.lower()) for k in [
                    "sales overview", "customer experience", "funnel", "sales", "delivered orders", "orders",
                    "average order value", "average rating", "bad orders", "total complaints", "online %",
                    "kitchen preparation", "impressions", "impressions to menu", "menu to order", "cart to order",
                    "new users", "lost sales", "rejections", "compare performance", "gross sales"
                ]):
                    break
                # Match numbers, currencies, percentages, minutes
                if re.search(r"^[-+▲▼]?\s*₹?\s*[\d,]+(?:\.\d+)?\s*(?:%|mins|min)?$", val_str):
                    raw_tokens.append(val_str)

            if not raw_tokens:
                return None

            # Filter tokens: separate trend badges (e.g. +9%, -3%, ▲5%) vs absolute values
            first_is_trend = False
            first_val = raw_tokens[0].strip()
            if (
                first_val.startswith("+")
                or first_val.startswith("▲")
                or first_val.startswith("▼")
                or (first_val.startswith("-") and is_pct_conversion)
                or (len(raw_tokens) > len(week_headers) and len(week_headers) > 0)
            ):
                first_is_trend = True

            pure_values = []
            for idx, tok in enumerate(raw_tokens):
                if idx == 0 and first_is_trend:
                    continue
                num = clean_number(tok)
                if is_pct_conversion and num < 0:
                    continue
                pure_values.append(num)

            if not pure_values:
                return None

            if target_week_offset is not None and target_week_offset < len(pure_values):
                return pure_values[target_week_offset]

            if len(headers) > 2 and target_col_idx >= 2:
                col_offset = target_col_idx - 2
                if col_offset < len(pure_values):
                    return pure_values[col_offset]

            if len(pure_values) >= 2:
                return pure_values[-2]
            return pure_values[-1]

        for i, line in enumerate(lines):
            l_lower = line.lower()

            if ("delivered orders" in l_lower or (l_lower == "orders" and "average" not in l_lower and "bad" not in l_lower)) and "orders" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["orders"] = val
                    metrics["reporting_orders"] = val
                    metrics["delivered_orders"] = val

            elif l_lower == "sales" and "sales" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["sales"] = val
                    metrics["subtotal"] = val

            elif ("average order value" in l_lower or l_lower == "aov") and "net_order_value" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["net_order_value"] = val
                    metrics["aov"] = val

            elif "average rating" in l_lower and "avg_rating" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["avg_rating"] = val

            elif "bad order" in l_lower and "bad_orders" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["bad_orders"] = val

            elif ("total complaints" in l_lower or l_lower == "complaints") and "total_complaints" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["total_complaints"] = val

            elif ("online %" in l_lower or "visibility" in l_lower) and "visibility" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["visibility"] = val

            elif ("kitchen preparation" in l_lower or "kitchen prep" in l_lower or l_lower == "kpt") and "kpt" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["kpt"] = val

            elif l_lower == "impressions" and "impressions" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None and val > 0:
                    metrics["impressions"] = val

            elif ("impressions to menu" in l_lower or "impression to menu" in l_lower or l_lower == "i2m") and "i2m" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["i2m"] = val

            elif ("menu to order" in l_lower or l_lower == "m2o") and "m2o" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["m2o"] = val

            elif ("cart to order" in l_lower or l_lower == "c2o" or "menu to cart" in l_lower) and "c2o" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=True)
                if val is not None and val >= 0:
                    metrics["c2o"] = val

            elif "new user" in l_lower and "new_users" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["new_users"] = val

            elif ("rejection" in l_lower or "rejected" in l_lower) and "mx_rejections" not in metrics:
                val = extract_clean_sequence(i, is_pct_conversion=False)
                if val is not None:
                    metrics["mx_rejections"] = val

        return metrics
