import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from processors.metric_calculator import clean_number


METRIC_ID_MAP = {
    "ONLINE_PERCENTAGE": "visibility",
    "KITCHEN_PREPARATION_TIME": "kpt",
    "IMPRESSIONS": "impressions",
    "MENU_OPENS": "menu_opens",
    "MENU_OPEN": "menu_opens",
    "I2M": "i2m",
    "MENU_OPENS_PERCENTAGE": "i2m",
    "C2O": "c2o",
    "ORDERS_PLACED_PERCENTAGE": "c2o",
    "M2O": "m2o",
    "CART_BUILDS": "cart_builds_pct",
    "CART_BUILDS_PERCENTAGE": "cart_builds_pct",
    "RESTAURANT_CANCELLED_ORDERS": "mx_rejections",
    "CANCELLED_ORDERS": "mx_rejections",
    "CANCELLED_ORDER": "mx_rejections",
    "DELIVERED_ORDERS": "reporting_orders",
    "NET_SALES": "reporting_sales",
    "GROSS_SALES": "reporting_sales",
}


class SwiggyPerformanceParser:
    """
    Pure data parser for Swiggy Partner Portal -> Business Reports / Performance tab.
    Decoupled from Playwright/browser state for clean isolated unit testing.

    Extraction Rules:
    - Visibility: Online availability (under Operations section).
    - KPT: Kitchen Prep Time (under Operations section).
    - Impressions: Impressions (under Funnel section).
    - I2M: Menu opens percentage (under Funnel section).
    - Menu Opens: Menu opens count (under Funnel section).
    - C2O: Orders placed percentage (under Funnel section).
    - M2O: Calculated as Cart builds % × Orders placed % (from Funnel section).
    - Mx Rejections: Restaurant Cancelled Orders (under Sales section).
    """

    @staticmethod
    def _apply_card_metric(metrics: Dict[str, Any], metric_id: str, value: str) -> None:
        field = METRIC_ID_MAP.get(metric_id.upper())
        if not field or not value:
            return
        num = clean_number(value)
        if num == 0 and "%" not in value and "min" not in value.lower():
            return
        metrics[field] = num

    @staticmethod
    def _apply_funnel_current_metric(
        metrics: Dict[str, Any], label: str, value: Any, percent: Any
    ) -> None:
        """Parses CONVERSION_FUNNEL current.metrics rows (label + value + percent)."""
        label_up = (label or "").upper().strip()
        if "IMPRESSION" in label_up:
            if value not in (None, ""):
                metrics["impressions"] = clean_number(value)
        elif "MENU OPEN" in label_up:
            if value not in (None, ""):
                metrics["menu_opens"] = clean_number(value)
            if percent not in (None, ""):
                metrics["i2m"] = clean_number(percent)
        elif "CART BUILD" in label_up:
            if percent not in (None, ""):
                metrics["cart_builds_pct"] = clean_number(percent)
        elif "ORDER" in label_up and "PLACED" in label_up:
            if percent not in (None, ""):
                metrics["c2o"] = clean_number(percent)

    @staticmethod
    def parse_graphql_business_metrics(raw_json: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Parses businessMetricsDetailsV3 GraphQL response into flat metrics dict."""
        if not raw_json:
            return {}
        metrics: Dict[str, Any] = {}
        root = raw_json.get("data", {}).get("businessMetricsDetailsV3")
        if isinstance(root, list):
            root = root[0] if root else {}
        if not root or not isinstance(root, dict):
            return {}

        sections = root.get("businessMetricsDetails") or []
        for section in sections:
            for block in section.get("metrics") or []:
                for sm in block.get("subMetrics") or []:
                    for cm in sm.get("cardMetrics") or []:
                        SwiggyPerformanceParser._apply_card_metric(metrics, cm.get("id", ""), cm.get("value", ""))
                    for lm in sm.get("listMetrics") or []:
                        SwiggyPerformanceParser._apply_card_metric(metrics, lm.get("id", ""), lm.get("value", ""))
                for cm in (block.get("current") or {}).get("metrics") or []:
                    SwiggyPerformanceParser._apply_funnel_current_metric(
                        metrics,
                        cm.get("label", ""),
                        cm.get("value"),
                        cm.get("percent"),
                    )

        # M2O = cart_builds_pct × c2o / 100
        cart = metrics.get("cart_builds_pct")
        c2o = metrics.get("c2o")
        if cart and c2o and "m2o" not in metrics:
            metrics["m2o"] = round((cart * c2o) / 100.0, 2)

        imp = metrics.get("impressions", 0.0)
        i2m = metrics.get("i2m", 0.0)
        if "menu_opens" not in metrics and imp > 0 and i2m > 0:
            metrics["menu_opens"] = round(imp * (i2m / 100.0))
        elif "i2m" not in metrics and imp > 0 and metrics.get("menu_opens", 0) > 0:
            metrics["i2m"] = round((metrics["menu_opens"] / imp) * 100.0, 2)

        return metrics

    @staticmethod
    def _has_core_performance_fields(metrics: Dict[str, Any]) -> bool:
        return bool(
            metrics.get("visibility")
            or metrics.get("kpt")
            or metrics.get("impressions")
            or metrics.get("i2m")
            or metrics.get("c2o")
        )

    @staticmethod
    def parse_performance_text(body_text: str, raw_json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parses operational, funnel, and sales metrics from Swiggy Business Reports text and/or GraphQL JSON.
        """
        metrics: Dict[str, Any] = {}

        if not body_text and not raw_json:
            return metrics

        # 1. Prefer GraphQL businessMetricsDetailsV3 structure
        if raw_json:
            gql_metrics = SwiggyPerformanceParser.parse_graphql_business_metrics(raw_json)
            if gql_metrics:
                metrics.update(gql_metrics)
            if SwiggyPerformanceParser._has_core_performance_fields(metrics):
                return metrics

            # Legacy flat JSON fallback
            try:
                data_block = raw_json.get("data") or raw_json
                if isinstance(data_block, dict):
                    if "impressions" in data_block:
                        metrics["impressions"] = clean_number(data_block["impressions"])
                    if "menuOpens" in data_block or "menu_opens" in data_block:
                        metrics["menu_opens"] = clean_number(data_block.get("menuOpens") or data_block.get("menu_opens"))
                    if "i2m" in data_block or "menuOpensPercentage" in data_block:
                        metrics["i2m"] = clean_number(data_block.get("i2m") or data_block.get("menuOpensPercentage"))
                    if "onlineAvailability" in data_block or "availability" in data_block:
                        metrics["visibility"] = clean_number(data_block.get("onlineAvailability") or data_block.get("availability"))
                    if "kpt" in data_block or "kitchenPrepTime" in data_block:
                        metrics["kpt"] = clean_number(data_block.get("kpt") or data_block.get("kitchenPrepTime"))
                    if "cancelledOrders" in data_block or "restaurantCancelled" in data_block:
                        metrics["mx_rejections"] = clean_number(data_block.get("cancelledOrders") or data_block.get("restaurantCancelled"))
            except Exception:
                pass
            if SwiggyPerformanceParser._has_core_performance_fields(metrics):
                return metrics

        lines = [l.strip() for l in (body_text or "").split("\n") if l.strip()]

        # Helper to extract next numeric/percentage value after keyword
        def extract_next_metric(keywords: List[str], max_lookahead: int = 5, require_pct: bool = False) -> Optional[float]:
            for idx, line in enumerate(lines):
                l_low = line.lower()
                if any(kw.lower() in l_low for kw in keywords):
                    # Check current line first
                    m_curr = re.search(r"[-+]?\s*₹?\s*([\d,]+(?:\.\d+)?)\s*%", line) if require_pct else re.search(r"[-+]?\s*₹?\s*([\d,]+(?:\.\d+)?)", line)
                    if m_curr:
                        val = clean_number(m_curr.group(1))
                        # Don't pick if it's part of the keyword itself
                        if not any(k.isdigit() for k in keywords):
                            return val

                    # Check subsequent lines
                    for j in range(idx + 1, min(idx + 1 + max_lookahead, len(lines))):
                        next_line = lines[j]
                        # Stop if encountering next section title
                        if any(next_line.lower().startswith(sec) for sec in ["operations", "funnel", "sales", "customer", "rating", "insights"]):
                            break
                        if require_pct:
                            m = re.search(r"([\d,]+(?:\.\d+)?)\s*%", next_line)
                            if m:
                                return clean_number(m.group(1))
                        else:
                            m = re.search(r"^[-+]?\s*₹?\s*([\d,]+(?:\.\d+)?)\s*(?:mins|min)?$", next_line)
                            if m:
                                return clean_number(m.group(1))
            return None

        # -------------------------------------------------------------
        # 1. OPERATIONS SECTION
        # -------------------------------------------------------------
        # Visibility: Online availability (under Operations section)
        m_online = re.search(r"(?:Online\s*availability|Online\s*Hours?|Serviceability|Store\s*uptime)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%", body_text, re.I)
        if m_online:
            metrics["visibility"] = clean_number(m_online.group(1))
        elif "visibility" not in metrics:
            val = extract_next_metric(["online availability", "online hours", "serviceability", "store uptime"], require_pct=True)
            if val is not None:
                metrics["visibility"] = val

        # KPT: Kitchen Prep Time (under Operations section)
        m_kpt = re.search(r"(?:Kitchen\s*Prep\s*Time|KPT|Prep\s*Time|Average\s*KPT)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*(?:mins|min)?", body_text, re.I)
        if m_kpt:
            metrics["kpt"] = clean_number(m_kpt.group(1))
        elif "kpt" not in metrics:
            val = extract_next_metric(["kitchen prep time", "kpt", "prep time"], require_pct=False)
            if val is not None:
                metrics["kpt"] = val

        # -------------------------------------------------------------
        # 2. FUNNEL SECTION
        # -------------------------------------------------------------
        # Impressions: Impressions (under Funnel section)
        m_imp = re.search(r"(?:Impressions|Listing\s*Views|Total\s*Impressions)\s*[:\n\r]*\s*([\d,]+)", body_text, re.I)
        if m_imp:
            metrics["impressions"] = clean_number(m_imp.group(1))
        elif "impressions" not in metrics:
            val = extract_next_metric(["impressions", "listing views"], require_pct=False)
            if val is not None:
                metrics["impressions"] = val

        # Menu Opens Count & I2M Percentage: Menu opens (under Funnel section)
        # Format often: "Menu opens: 1,885 (13.00%)" or "Menu opens\n1,885\n13.00%"
        m_menu = re.search(r"Menu\s*opens?\s*[:\n\r]*\s*([\d,]+)(?:\s*\(([\d.]+)%\))?", body_text, re.I)
        if m_menu:
            metrics["menu_opens"] = clean_number(m_menu.group(1))
            if m_menu.group(2):
                metrics["i2m"] = clean_number(m_menu.group(2))

        # I2M: Menu opens percentage
        if "i2m" not in metrics:
            m_i2m = re.search(r"(?:Menu\s*opens?\s*percentage|I2M|Impression\s*to\s*menu)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%", body_text, re.I)
            if m_i2m:
                metrics["i2m"] = clean_number(m_i2m.group(1))
            else:
                val = extract_next_metric(["menu opens percentage", "impression to menu", "i2m"], require_pct=True)
                if val is not None:
                    metrics["i2m"] = val

        # Cart builds percentage (used for M2O calculation)
        cart_builds_pct = None
        m_cart = re.search(r"(?:Cart\s*builds?|Menu\s*to\s*cart)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%", body_text, re.I)
        if m_cart:
            cart_builds_pct = clean_number(m_cart.group(1))
        else:
            val = extract_next_metric(["cart builds", "menu to cart", "cart build %"], require_pct=True)
            if val is not None:
                cart_builds_pct = val

        # C2O: Orders placed percentage (under Funnel section)
        m_c2o = re.search(r"(?:Orders\s*placed\s*percentage|Orders\s*placed|Cart\s*to\s*order|C2O)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%", body_text, re.I)
        if m_c2o:
            metrics["c2o"] = clean_number(m_c2o.group(1))
        elif "c2o" not in metrics:
            val = extract_next_metric(["orders placed percentage", "cart to order", "orders placed", "c2o"], require_pct=True)
            if val is not None:
                metrics["c2o"] = val

        # M2O: Calculated as Cart builds % × Orders placed % (from Funnel section)
        c2o_val = metrics.get("c2o", 0.0)
        if cart_builds_pct is not None and c2o_val > 0:
            # e.g., 45.00% * 32.00% = 14.40%
            m2o_calculated = round((cart_builds_pct * c2o_val) / 100.0, 2)
            metrics["m2o"] = m2o_calculated
            metrics["cart_builds_pct"] = cart_builds_pct
        else:
            m_m2o_direct = re.search(r"(?:Menu\s*to\s*order|M2O)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%", body_text, re.I)
            if m_m2o_direct:
                metrics["m2o"] = clean_number(m_m2o_direct.group(1))

        # -------------------------------------------------------------
        # 3. SALES & ORDERS SECTION
        # -------------------------------------------------------------
        # Mx Rejections: Restaurant Cancelled Orders (under Sales section)
        m_rej = re.search(r"(?:Restaurant\s*Cancelled\s*Orders?|Merchant\s*Cancelled|Restaurant\s*Rejections?|Mx\s*Rejections?|Cancelled\s*by\s*Restaurant)\s*[:\n\r]*\s*([\d,]+)", body_text, re.I)
        if m_rej:
            metrics["mx_rejections"] = clean_number(m_rej.group(1))
        elif "mx_rejections" not in metrics:
            val = extract_next_metric(["restaurant cancelled orders", "restaurant cancelled", "merchant cancelled", "cancelled by restaurant"], require_pct=False)
            if val is not None:
                metrics["mx_rejections"] = val

        # Orders & Sales if displayed in Business Reports
        m_orders = re.search(r"(?:Delivered\s*Orders|Total\s*Orders|Orders\s*Completed)\s*[:\n\r]*\s*([\d,]+)", body_text, re.I)
        if m_orders:
            metrics["reporting_orders"] = clean_number(m_orders.group(1))

        m_sales = re.search(r"(?:Gross\s*Sales|Total\s*Sales|Net\s*Sales)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", body_text, re.I)
        if m_sales:
            metrics["reporting_sales"] = clean_number(m_sales.group(1))

        # Cross derive Menu opens if missing: Impressions * (I2M / 100)
        imp = metrics.get("impressions", 0.0)
        i2m = metrics.get("i2m", 0.0)
        if "menu_opens" not in metrics and imp > 0 and i2m > 0:
            metrics["menu_opens"] = round(imp * (i2m / 100.0))
        elif "i2m" not in metrics and imp > 0 and metrics.get("menu_opens", 0) > 0:
            metrics["i2m"] = round((metrics["menu_opens"] / imp) * 100.0, 2)

        return metrics
