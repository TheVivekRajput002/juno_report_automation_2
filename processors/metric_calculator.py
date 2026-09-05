from dataclasses import dataclass, field
from typing import Optional, Dict, Any


def clean_number(val: Any) -> float:
    """Cleans currency strings, percentages, minus signs, and commas to float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    # Check if negative
    is_neg = False
    if s.startswith("-") or s.startswith("–") or s.startswith("—") or (s.startswith("(") and s.endswith(")")):
        is_neg = True
        s = s.strip("-–—()")
    
    # Strip symbols, commas, unit words
    s = s.replace("₹", "").replace(",", "").replace("%", "").replace("mins", "").replace("min", "").strip()
    s = s.replace("₹", "").strip()
    
    try:
        num = float(s)
        return -num if is_neg else num
    except ValueError:
        import re
        m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
        if m:
            try:
                num = float(m.group(0))
                return -num if is_neg else num
            except ValueError:
                return 0.0
        return 0.0


@dataclass
class PlatformMetrics:
    """Stores metrics for a single delivery platform (Zomato or Swiggy)."""
    orders: float = 0.0
    subtotal: float = 0.0
    total_discount: float = 0.0
    sales_after_discount: float = 0.0
    net_order_value: float = 0.0
    packaging_charges: float = 0.0
    commission: float = 0.0
    ads: float = 0.0
    cash_in_bank: float = 0.0
    discount_pct: float = 0.0
    commission_pct: float = 0.0
    ads_pct: float = 0.0
    payout_pct: float = 0.0
    visibility: float = 0.0
    kpt: float = 0.0
    impressions: float = 0.0
    i2m: float = 0.0
    menu_opens: float = 0.0
    c2o: float = 0.0
    m2o: float = 0.0
    mx_rejections: float = 0.0

    raw_data: Dict[str, Any] = field(default_factory=dict)


class MetricCalculator:
    """Calculates derived metrics according to the exact business rules."""

    @staticmethod
    def calculate_zomato_metrics(raw: Dict[str, Any]) -> PlatformMetrics:
        """
        Applies specific calculation rules for Zomato:
        - orders = delivered orders from reporting tab
        - subtotal = Item subtotal under Net Order Value (payout page)
        - total_discount = sum of the discounts under net order value (payout page)
        - sales_after_discount = formula: subtotal - total discount
        - net_order_value = formula: sales after discount divided by orders
        - packaging_charges = packaging charges if applicable else 0
        - commission = order level deductions + GST on service and payment mechanism fees @18% under tax deductions block
        - ads = investment in growth
        - cash_in_bank = est payout
        - discount_pct = total_discount / subtotal
        - commission_pct = commission / sales_after_discount
        - ads_pct = ads / subtotal
        - payout_pct = cash_in_bank / subtotal
        - visibility = in percentage (in report section)
        - kpt = Kitchen Prep Time
        - impressions = Impressions
        - i2m = in percentage
        - menu_opens = impressions * i2m
        - c2o = cart to order
        - m2o = in percentage (in report section)
        - mx_rejections = rejected orders (under payout section)
        """
        # Orders = delivered orders from reporting tab
        orders = clean_number(raw.get("reporting_orders") or raw.get("orders") or raw.get("delivered_orders", 0))
        
        # Financial amounts
        subtotal_raw = raw.get("subtotal") or raw.get("item_subtotal")
        nov_amount_raw = raw.get("net_order_value_amount") or raw.get("net_order_value_A") or raw.get("nov_amount")
        total_discount = clean_number(raw.get("total_discount") or raw.get("discounts", 0))

        if subtotal_raw:
            subtotal = clean_number(subtotal_raw)
        elif nov_amount_raw:
            subtotal = clean_number(nov_amount_raw) + total_discount
        else:
            subtotal = 0.0

        # Sales after discount = formula: subtotal - total discount
        sales_after_discount = round(subtotal - total_discount, 2)

        # Net order value = formula: sales after discount divided by orders
        net_order_value = (sales_after_discount / orders) if orders > 0 else 0.0

        packaging_charges = clean_number(raw.get("packaging_charges", 0))

        # Commission = order level deductions + GST on service and payment mechanism fees @18%
        order_ded = abs(clean_number(raw.get("order_level_deductions") or raw.get("order_level_deductions_C", 0)))
        gst_18 = abs(clean_number(raw.get("gst_fee_18") or raw.get("gst_tax_deductions") or raw.get("tax_deductions", 0)))
        commission = clean_number(raw.get("commission", 0)) or round(order_ded + gst_18, 2)

        # Ads: Investments in Growth (E)
        ads = abs(clean_number(raw.get("ads") or raw.get("investments_in_growth") or raw.get("investments_in_growth_E", 0)))

        # Cash in bank = est payout
        cash_in_bank = clean_number(raw.get("est_payout") or raw.get("cash_in_bank") or raw.get("net_payout", 0))

        # Derived Financial Percentages (0 to 100)
        discount_pct = (total_discount / subtotal * 100) if subtotal > 0 else 0.0
        commission_pct = (commission / sales_after_discount * 100) if sales_after_discount > 0 else 0.0
        ads_pct = (ads / subtotal * 100) if subtotal > 0 else 0.0
        payout_pct = (cash_in_bank / subtotal * 100) if subtotal > 0 else 0.0

        # Operational & Funnel Metrics (Ensure in 0-100 percentage scale)
        visibility = clean_number(raw.get("visibility") or raw.get("online_pct", 0))
        if 0 < visibility <= 1.0:
            visibility = round(visibility * 100.0, 2)

        kpt = clean_number(raw.get("kpt") or raw.get("kitchen_prep_time", 0))
        impressions = clean_number(raw.get("impressions", 0))

        i2m = clean_number(raw.get("i2m") or raw.get("impression_to_menu", 0))
        if 0 < i2m <= 1.0:
            i2m = round(i2m * 100.0, 2)

        c2o = clean_number(raw.get("c2o") or raw.get("cart_to_order", 0))
        if 0 < c2o <= 1.0:
            c2o = round(c2o * 100.0, 2)

        m2o = clean_number(raw.get("m2o") or raw.get("menu_to_order", 0))
        if 0 < m2o <= 1.0:
            m2o = round(m2o * 100.0, 2)

        # Menu Opens = impressions * i2m
        menu_opens = clean_number(raw.get("menu_opens", 0))
        if impressions > 0 and i2m > 0:
            menu_opens = round(impressions * (i2m / 100.0))

        mx_rejections = clean_number(raw.get("rejected_orders") or raw.get("mx_rejections", 0))

        return PlatformMetrics(
            orders=orders,
            subtotal=subtotal,
            total_discount=total_discount,
            sales_after_discount=sales_after_discount,
            net_order_value=net_order_value,
            packaging_charges=packaging_charges,
            commission=commission,
            ads=ads,
            cash_in_bank=cash_in_bank,
            discount_pct=discount_pct,
            commission_pct=commission_pct,
            ads_pct=ads_pct,
            payout_pct=payout_pct,
            visibility=visibility,
            kpt=kpt,
            impressions=impressions,
            i2m=i2m,
            menu_opens=menu_opens,
            c2o=c2o,
            m2o=m2o,
            mx_rejections=mx_rejections,
            raw_data=raw
        )
