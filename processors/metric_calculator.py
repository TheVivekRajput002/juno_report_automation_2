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
        # Orders = delivered orders from reporting tab (or payout fallback)
        orders = clean_number(
            raw.get("reporting_orders")
            or raw.get("delivered_orders")
            or raw.get("orders")
            or raw.get("payout_delivered_orders")
            or 0
        )
        
        # Financial amounts
        # reporting_sales / sales_after_discount / sales = Net Sales (from Business Reports table)
        # nov_payout = Net order value (A) (from Payout drawer)
        # item_subtotal = Item subtotal (Gross Sales) (from Payout drawer)
        # total_discount = sum of discounts (from Payout drawer)
        reporting_sales = clean_number(raw.get("reporting_sales") or raw.get("sales_after_discount") or raw.get("sales") or 0)
        nov_payout = clean_number(raw.get("net_order_value_amount") or raw.get("net_order_value_A") or raw.get("nov_amount") or 0)
        net_sales = nov_payout if nov_payout > 0 else reporting_sales

        disc_promos = abs(clean_number(raw.get("discount_promos", 0)))
        disc_flat = abs(clean_number(raw.get("discount_flat_offs", 0)))
        disc_deliv = abs(clean_number(raw.get("discount_delivery", 0)))
        scraped_discount = clean_number(raw.get("total_discount")) or round(disc_promos + disc_flat + disc_deliv, 2)

        raw_sub = clean_number(raw.get("item_subtotal") or raw.get("subtotal") or 0)
        # Avoid treating reporting_sales mistakenly passed as subtotal
        if raw_sub == reporting_sales and raw_sub > 0 and scraped_discount > 0:
            item_subtotal = 0.0
        else:
            item_subtotal = raw_sub

        # Mathematical Reconciliation:
        # Subtotal (Gross Sales) = Sales After Discount (Net Sales) + Total Discount
        # Sales After Discount = Subtotal - Total Discount
        # Total Discount = Subtotal - Sales After Discount
        if item_subtotal > 0 and scraped_discount > 0:
            subtotal = item_subtotal
            total_discount = scraped_discount
            sales_after_discount = round(subtotal - total_discount, 2)
        elif item_subtotal > 0 and net_sales > 0 and item_subtotal >= net_sales:
            subtotal = item_subtotal
            total_discount = round(subtotal - net_sales, 2) if scraped_discount == 0 else scraped_discount
            sales_after_discount = round(subtotal - total_discount, 2)
        elif net_sales > 0 and scraped_discount > 0:
            total_discount = scraped_discount
            sales_after_discount = net_sales
            subtotal = round(sales_after_discount + total_discount, 2)
        elif item_subtotal > 0:
            subtotal = item_subtotal
            total_discount = scraped_discount
            sales_after_discount = round(subtotal - total_discount, 2)
        elif net_sales > 0:
            total_discount = scraped_discount
            sales_after_discount = net_sales
            subtotal = round(sales_after_discount + total_discount, 2)
        else:
            subtotal = 0.0
            total_discount = 0.0
            sales_after_discount = 0.0

        # Net order value = Sales after discount / orders
        if orders > 0 and sales_after_discount > 0:
            net_order_value = round(sales_after_discount / orders, 2)
        elif raw.get("net_order_value") or raw.get("aov") or raw.get("average_order_value"):
            net_order_value = clean_number(raw.get("net_order_value") or raw.get("aov") or raw.get("average_order_value"))
        else:
            net_order_value = 0.0

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

        # Operational & Funnel Metrics (Ensure in 0-100 percentage scale and non-negative)
        visibility = clean_number(raw.get("visibility") or raw.get("online_pct", 0))
        if visibility < 0:
            visibility = 0.0
        elif 0 < visibility <= 1.0:
            visibility = round(visibility * 100.0, 2)

        kpt = max(0.0, clean_number(raw.get("kpt") or raw.get("kitchen_prep_time", 0)))
        impressions = max(0.0, clean_number(raw.get("impressions", 0)))

        i2m_raw = clean_number(raw.get("i2m") or raw.get("impression_to_menu", 0))
        i2m = 0.0 if i2m_raw < 0 else i2m_raw
        if 0 < i2m <= 1.0:
            i2m = round(i2m * 100.0, 2)

        menu_opens_raw = max(0.0, clean_number(raw.get("menu_opens", 0)))
        
        # Cross-derive menu_opens or i2m
        if menu_opens_raw > 0:
            menu_opens = menu_opens_raw
            if i2m == 0.0 and impressions > 0:
                i2m = round((menu_opens / impressions) * 100.0, 2)
        elif impressions > 0 and i2m > 0:
            menu_opens = round(impressions * (i2m / 100.0))
        else:
            menu_opens = 0.0

        c2o_raw = clean_number(raw.get("c2o") or raw.get("cart_to_order", 0))
        c2o = 0.0 if c2o_raw < 0 else c2o_raw
        if 0 < c2o <= 1.0:
            c2o = round(c2o * 100.0, 2)

        m2o_raw = clean_number(raw.get("m2o") or raw.get("menu_to_order", 0))
        m2o = 0.0 if m2o_raw < 0 else m2o_raw
        if 0 < m2o <= 1.0:
            m2o = round(m2o * 100.0, 2)
        elif m2o == 0.0 and orders > 0 and menu_opens > 0:
            m2o = round((orders / menu_opens) * 100.0, 2)

        mx_rejections = max(0.0, clean_number(raw.get("rejected_orders") or raw.get("mx_rejections", 0)))

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

    @staticmethod
    def calculate_swiggy_metrics(raw: Dict[str, Any]) -> PlatformMetrics:
        """
        Applies specific calculation rules for Swiggy:
        - Orders: Total Orders (under past payout card header)
        - Subtotal: Item Total (under (A) Total Customer Paid)
        - Total Discount: Sum of Restaurant Discounts (Coupon based) + Restaurant Discounts (Trade Discounts, Freebies and others)
        - Sales after discount: Subtotal - Total Discount
        - Net order value: Sales after discount / Orders (Numeric, rounded to 2 decimal places)
        - Packaging Charges: Packaging Charges under Finance tab (or 0 if absent)
        - Commission: (B) Total Fees + TDS (under (D) Total Taxes)
        - Ads: (E) Growth Investments in Ads
        - Cash in Bank: Net Payout (Net Payout (A+B+C+D+E+F))
        - Visibility: Online availability (under Operations section)
        - KPT: Kitchen Prep Time (under Operations section)
        - Impressions: Impressions (under Funnel section)
        - I2M: Menu opens percentage (under Funnel section)
        - Menu Opens: Menu opens count (under Funnel section)
        - C2O: Orders placed percentage (under Funnel section)
        - M2O: Calculated as Cart builds % × Orders placed % (from Funnel section)
        - Mx Rejections: Restaurant Cancelled Orders (under Sales section)
        - All percentage metrics: Formatted consistently (0-100 float scale)
        """
        # 1. Orders: Total Orders from payout card header or reporting
        orders = clean_number(
            raw.get("orders")
            or raw.get("payout_delivered_orders")
            or raw.get("reporting_orders")
            or raw.get("delivered_orders")
            or 0
        )

        # 2. Financial Amounts
        reporting_sales = clean_number(raw.get("reporting_sales") or raw.get("sales_after_discount") or raw.get("sales") or 0)
        
        # Total Discount: Coupon based + Trade discounts / Freebies
        disc_coupon = abs(clean_number(raw.get("discount_coupons", 0)))
        disc_trade = abs(clean_number(raw.get("discount_trade", 0)))
        scraped_discount = clean_number(raw.get("total_discount")) or round(disc_coupon + disc_trade, 2)

        # Subtotal: Item Total (under (A) Total Customer Paid)
        raw_sub = clean_number(raw.get("item_subtotal") or raw.get("subtotal") or 0)
        if raw_sub == reporting_sales and raw_sub > 0 and scraped_discount > 0:
            item_subtotal = 0.0
        else:
            item_subtotal = raw_sub

        # Mathematical Reconciliation:
        # Subtotal (Gross Sales) = Sales After Discount (Net Sales) + Total Discount
        # Sales After Discount = Subtotal - Total Discount
        if item_subtotal > 0 and scraped_discount > 0:
            subtotal = item_subtotal
            total_discount = scraped_discount
            sales_after_discount = round(subtotal - total_discount, 2)
        elif item_subtotal > 0 and reporting_sales > 0 and item_subtotal >= reporting_sales:
            subtotal = item_subtotal
            total_discount = round(subtotal - reporting_sales, 2) if scraped_discount == 0 else scraped_discount
            sales_after_discount = round(subtotal - total_discount, 2)
        elif reporting_sales > 0 and scraped_discount > 0:
            total_discount = scraped_discount
            sales_after_discount = reporting_sales
            subtotal = round(sales_after_discount + total_discount, 2)
        elif item_subtotal > 0:
            subtotal = item_subtotal
            total_discount = scraped_discount
            sales_after_discount = round(subtotal - total_discount, 2)
        elif reporting_sales > 0:
            total_discount = scraped_discount
            sales_after_discount = reporting_sales
            subtotal = round(sales_after_discount + total_discount, 2)
        else:
            subtotal = 0.0
            total_discount = 0.0
            sales_after_discount = 0.0

        # Net order value = Sales after discount / orders
        if orders > 0 and sales_after_discount > 0:
            net_order_value = round(sales_after_discount / orders, 2)
        elif raw.get("net_order_value") or raw.get("aov"):
            net_order_value = clean_number(raw.get("net_order_value") or raw.get("aov"))
        else:
            net_order_value = 0.0

        packaging_charges = clean_number(raw.get("packaging_charges", 0))

        # Commission = (B) Total Fees + TDS (under (D) Total Taxes)
        total_fees = abs(clean_number(raw.get("total_fees_B") or raw.get("total_fees", 0)))
        tds = abs(clean_number(raw.get("tds_amount") or raw.get("tds", 0)))
        commission = clean_number(raw.get("commission")) or round(total_fees + tds, 2)

        # Ads: (E) Growth Investments in Ads
        ads = abs(clean_number(raw.get("ads") or raw.get("growth_investments_ads", 0)))

        # Cash in Bank: Net Payout
        cash_in_bank = clean_number(raw.get("cash_in_bank") or raw.get("net_payout", 0))

        # Derived Financial Percentages (0 to 100 scale)
        discount_pct = (total_discount / subtotal * 100) if subtotal > 0 else 0.0
        commission_pct = (commission / sales_after_discount * 100) if sales_after_discount > 0 else 0.0
        ads_pct = (ads / subtotal * 100) if subtotal > 0 else 0.0
        payout_pct = (cash_in_bank / subtotal * 100) if subtotal > 0 else 0.0

        # Operational & Funnel Metrics
        visibility = clean_number(raw.get("visibility") or raw.get("online_availability", 0))
        if visibility < 0:
            visibility = 0.0
        elif 0 < visibility <= 1.0:
            visibility = round(visibility * 100.0, 2)

        kpt = max(0.0, clean_number(raw.get("kpt") or raw.get("kitchen_prep_time", 0)))
        impressions = max(0.0, clean_number(raw.get("impressions", 0)))

        i2m_raw = clean_number(raw.get("i2m") or raw.get("menu_opens_pct", 0))
        i2m = 0.0 if i2m_raw < 0 else i2m_raw
        if 0 < i2m <= 1.0:
            i2m = round(i2m * 100.0, 2)

        menu_opens_raw = max(0.0, clean_number(raw.get("menu_opens", 0)))
        if menu_opens_raw > 0:
            menu_opens = menu_opens_raw
            if i2m == 0.0 and impressions > 0:
                i2m = round((menu_opens / impressions) * 100.0, 2)
        elif impressions > 0 and i2m > 0:
            menu_opens = round(impressions * (i2m / 100.0))
        else:
            menu_opens = 0.0

        c2o_raw = clean_number(raw.get("c2o") or raw.get("orders_placed_pct", 0))
        c2o = 0.0 if c2o_raw < 0 else c2o_raw
        if 0 < c2o <= 1.0:
            c2o = round(c2o * 100.0, 2)

        # M2O: Calculated as Cart builds % × Orders placed %
        cart_builds_pct = clean_number(raw.get("cart_builds_pct", 0))
        if cart_builds_pct > 0 and c2o > 0:
            m2o = round((cart_builds_pct * c2o) / 100.0, 2)
        else:
            m2o_raw = clean_number(raw.get("m2o", 0))
            m2o = 0.0 if m2o_raw < 0 else m2o_raw
            if 0 < m2o <= 1.0:
                m2o = round(m2o * 100.0, 2)

        mx_rejections = max(0.0, clean_number(raw.get("restaurant_cancelled_orders") or raw.get("mx_rejections", 0)))

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
