import re
from typing import Dict, Any, List, Optional
from processors.metric_calculator import clean_number


class SwiggyPayoutParser:
    """
    Pure data and text parser for Swiggy Finance & Weekly Payout side drawer.
    Completely decoupled from Playwright/Browser state for easy isolated unit testing.

    Extraction Rules:
    - Orders: Total Orders (under past payout card header).
    - Subtotal: Item Total (under (A) Total Customer Paid).
    - Total Discount: Sum of Restaurant Discounts (Coupon based) + Restaurant Discounts (Trade Discounts, Freebies and others) (under (A) Total Customer Paid).
    - Sales after discount: Subtotal - Total Discount
    - Net order value: Sales after discount / Orders (Numeric, rounded to 2 decimal places).
    - Packaging Charges: Packaging Charges (under Finance tab, or 0 if absent).
    - Commission: (B) Total Fees + TDS (under (D) Total Taxes).
    - Ads: (E) Growth Investments in Ads.
    - Cash in Bank: Net Payout (Net Payout (A+B+C+D+E+F)).
    """

    @staticmethod
    def _extract_numeric(data: Dict[str, Any], *keys: str) -> float:
        for key in keys:
            if key in data and data[key] is not None:
                return clean_number(data[key])
            for k, v in data.items():
                if str(k).lower() == key.lower() and v is not None:
                    return clean_number(v)
        return 0.0

    @staticmethod
    def parse_graphql_payout_details(raw_json: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Parses getRestaurantPayoutDetailsV3 GraphQL response."""
        if not raw_json:
            return {}

        data_list = raw_json.get("data", {}).get("getRestaurantPayoutDetailsV3", {}).get("data") or []
        if not data_list:
            return SwiggyPayoutParser.parse_payout_json(raw_json)

        p0 = data_list[0]
        result: Dict[str, Any] = {}

        orders = clean_number(p0.get("orderCount"))
        if orders > 0:
            result["orders"] = orders
            result["payout_delivered_orders"] = orders

        net = clean_number(p0.get("netPayout"))
        if net != 0:
            result["cash_in_bank"] = net
            result["net_payout"] = net

        for section in p0.get("payoutSummary") or []:
            header = (section.get("header") or "").lower()
            amount = abs(clean_number(section.get("amount")))
            subs = section.get("subHeaders") or []

            if "customer paid" in header:
                result["total_customer_paid_A"] = clean_number(section.get("amount"))
                for sub in subs:
                    text = (sub.get("text") or "").lower()
                    sub_amt = abs(clean_number(sub.get("amount")))
                    if "item total" in text or "item subtotal" in text or "gross" in text:
                        result["subtotal"] = sub_amt
                        result["item_subtotal"] = sub_amt
                    elif "coupon" in text:
                        result["discount_coupons"] = sub_amt
                    elif "trade" in text or "freebie" in text:
                        result["discount_trade"] = sub_amt

            elif "total fees" in header:
                result["total_fees_B"] = amount

            elif "total taxes" in header:
                result["total_taxes_D"] = amount
                for sub in subs:
                    if "tds" in (sub.get("text") or "").lower():
                        result["tds_amount"] = abs(clean_number(sub.get("amount")))

            elif "growth investments" in header or "ads" in header:
                result["ads"] = amount

            elif "packaging" in header:
                result["packaging_charges"] = amount

        disc_c = result.get("discount_coupons", 0.0)
        disc_t = result.get("discount_trade", 0.0)
        if disc_c or disc_t:
            result["total_discount"] = round(disc_c + disc_t, 2)

        sub = result.get("subtotal", 0.0)
        td = result.get("total_discount", 0.0)
        if sub > 0 and td > 0:
            result["sales_after_discount"] = round(sub - td, 2)

        fees = result.get("total_fees_B", 0.0)
        tds = result.get("tds_amount", 0.0)
        if fees or tds:
            result["commission"] = round(fees + tds, 2)

        return result

    @staticmethod
    def parse_payout_json(raw_json: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parses financial settlement fields from intercepted Swiggy Finance/Settlement API JSON.
        Uses flexible key matching since exact payload shapes are discovered at runtime.
        """
        if not raw_json:
            return {}

        data: Dict[str, Any] = {}
        block = raw_json.get("data") or raw_json.get("result") or raw_json
        if isinstance(block, list) and block:
            block = block[0]
        if not isinstance(block, dict):
            return {}

        orders = SwiggyPayoutParser._extract_numeric(
            block, "orders", "totalOrders", "deliveredOrders", "orderCount", "payout_delivered_orders"
        )
        if orders > 0:
            data["orders"] = orders
            data["payout_delivered_orders"] = orders

        subtotal = SwiggyPayoutParser._extract_numeric(
            block, "subtotal", "itemSubtotal", "itemTotal", "grossSales", "totalCustomerPaid"
        )
        if subtotal > 0:
            data["subtotal"] = subtotal
            data["item_subtotal"] = subtotal

        disc_coupons = SwiggyPayoutParser._extract_numeric(block, "couponDiscount", "discountCoupons", "couponBasedDiscount")
        disc_trade = SwiggyPayoutParser._extract_numeric(block, "tradeDiscount", "discountTrade", "freebieDiscount")
        total_discount = SwiggyPayoutParser._extract_numeric(block, "totalDiscount", "restaurantDiscount")
        if total_discount == 0 and (disc_coupons > 0 or disc_trade > 0):
            total_discount = round(disc_coupons + disc_trade, 2)
        if total_discount > 0:
            data["discount_coupons"] = disc_coupons
            data["discount_trade"] = disc_trade
            data["total_discount"] = total_discount

        sub = data.get("subtotal", 0.0)
        if sub > 0 and total_discount > 0:
            data["sales_after_discount"] = round(sub - total_discount, 2)

        packaging = SwiggyPayoutParser._extract_numeric(block, "packagingCharges", "packagingFee")
        data["packaging_charges"] = packaging

        total_fees = SwiggyPayoutParser._extract_numeric(block, "totalFees", "serviceFee", "commissionFees")
        tds = SwiggyPayoutParser._extract_numeric(block, "tds", "tdsAmount", "taxDeductedAtSource")
        commission = SwiggyPayoutParser._extract_numeric(block, "commission", "totalCommission")
        if commission == 0 and (total_fees > 0 or tds > 0):
            commission = round(total_fees + tds, 2)
        if total_fees > 0:
            data["total_fees_B"] = total_fees
        if tds > 0:
            data["tds_amount"] = tds
        if commission > 0:
            data["commission"] = commission

        ads = SwiggyPayoutParser._extract_numeric(block, "ads", "adsSpend", "growthInvestments", "adSpend")
        data["ads"] = ads

        net_payout = SwiggyPayoutParser._extract_numeric(
            block, "netPayout", "cashInBank", "estimatedPayout", "amountSettled", "payoutAmount"
        )
        if net_payout > 0:
            data["cash_in_bank"] = net_payout
            data["net_payout"] = net_payout

        return data

    @staticmethod
    def _has_core_payout_fields(data: Dict[str, Any]) -> bool:
        return bool(
            data.get("orders")
            or data.get("subtotal")
            or data.get("cash_in_bank") is not None
            or data.get("net_payout") is not None
            or data.get("commission")
            or data.get("ads")
        )

    @staticmethod
    def parse_payout_text(
        drawer_text: str,
        all_text: str = "",
        card_header_text: str = "",
        raw_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Parses financial breakdown, discounts, fees, TDS, ads, and net payout from Swiggy Finance drawer and card.
        Prefers intercepted JSON when it contains core payout fields; DOM text is used as fallback/supplement.
        """
        data: Dict[str, Any] = SwiggyPayoutParser.parse_graphql_payout_details(raw_json)
        if not SwiggyPayoutParser._has_core_payout_fields(data):
            data = SwiggyPayoutParser.parse_payout_json(raw_json)
        if SwiggyPayoutParser._has_core_payout_fields(data):
            return data

        combined_text = (drawer_text or "") + "\n" + (card_header_text or "") + "\n" + (all_text or "")
        lines = [l.strip() for l in combined_text.splitlines() if l.strip()]

        # -------------------------------------------------------------
        # 1. TOTAL ORDERS (under past payout card header)
        # -------------------------------------------------------------
        m_orders = re.search(r"(?:Total\s*Orders|Delivered\s*Orders|Orders\s*Delivered|Orders)\s*[:\n\r]*\s*([\d,]+)", card_header_text or combined_text, re.I)
        if m_orders:
            data["orders"] = clean_number(m_orders.group(1))
            data["payout_delivered_orders"] = clean_number(m_orders.group(1))

        # -------------------------------------------------------------
        # 2. (A) TOTAL CUSTOMER PAID & ITEM TOTAL (SUBTOTAL)
        # -------------------------------------------------------------
        def get_item_value(keywords: List[str], max_lookahead: int = 3) -> float:
            for idx, l in enumerate(lines):
                l_low = l.lower().strip()
                if all(kw.lower() in l_low for kw in keywords):
                    for j in range(idx + 1, min(idx + 1 + max_lookahead, len(lines))):
                        next_l = lines[j]
                        if any(k in next_l.lower() for k in ["total fees", "(b)", "(c)", "(d)", "(e)", "total taxes", "growth investments"]):
                            break
                        m_next = re.search(r'[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)', next_l)
                        if m_next:
                            val = abs(clean_number(m_next.group(1)))
                            if val > 0:
                                return val
                            break
            return 0.0

        # Subtotal: Item Total (under (A) Total Customer Paid)
        m_subtotal = re.search(r"(?:Item\s*Total|Item\s*Subtotal|Gross\s*Sales|Gross\s*Item\s*Total)[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        subtotal_val = clean_number(m_subtotal.group(1)) if m_subtotal else 0.0
        if subtotal_val == 0.0:
            subtotal_val = get_item_value(["item total"]) or get_item_value(["item subtotal"])

        if subtotal_val > 0:
            data["subtotal"] = subtotal_val
            data["item_subtotal"] = subtotal_val

        # (A) Total Customer Paid fallback
        m_cust_paid = re.search(r"(?:\(A\)\s*Total\s*Customer\s*Paid|Total\s*Customer\s*Paid\s*\(A\)?)[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_cust_paid:
            data["total_customer_paid_A"] = clean_number(m_cust_paid.group(1))
            if "subtotal" not in data or data["subtotal"] == 0:
                data["subtotal"] = clean_number(m_cust_paid.group(1))
                data["item_subtotal"] = clean_number(m_cust_paid.group(1))

        # -------------------------------------------------------------
        # 3. TOTAL DISCOUNT FORMULA:
        # Sum of:
        #   - Restaurant Discounts (Coupon based)
        #   - Restaurant Discounts (Trade Discounts, Freebies and others)
        # -------------------------------------------------------------
        def get_discount_item(keywords: List[str]) -> float:
            for idx, l in enumerate(lines):
                l_low = l.lower()
                if all(kw.lower() in l_low for kw in keywords):
                    # Check negative ₹ amount on same line
                    m_neg = re.findall(r'[-–—]\s*₹?\s*([\d,]+(?:\.\d+)?)', l)
                    if m_neg:
                        val = abs(clean_number(m_neg[-1]))
                        if val > 0:
                            return val
                    # Check next 1-3 lines for ₹ amount
                    for j in range(idx + 1, min(idx + 4, len(lines))):
                        next_l = lines[j]
                        if any(k in next_l.lower() for k in ["total customer", "total fees", "(b)", "(c)", "(d)", "(e)", "item total", "restaurant discount"]):
                            break
                        m_next = re.search(r'[-–—]?\s*₹\s*([\d,]+(?:\.\d+)?)', next_l)
                        if m_next:
                            val = abs(clean_number(m_next.group(1)))
                            if val > 0:
                                return val
                            break
            return 0.0

        # Item 1: Restaurant Discounts (Coupon based)
        disc_coupons = get_discount_item(["coupon based"])
        if disc_coupons == 0.0:
            disc_coupons = get_discount_item(["coupon", "discount"])
        if disc_coupons == 0.0:
            m_c = re.search(r"(?:Restaurant\s*Discounts?\s*\(Coupon\s*based\)|Coupon\s*Discounts?)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_c:
                disc_coupons = abs(clean_number(m_c.group(1)))

        # Item 2: Restaurant Discounts (Trade Discounts, Freebies and others)
        disc_trade = get_discount_item(["trade discount"])
        if disc_trade == 0.0:
            disc_trade = get_discount_item(["trade discounts, freebies"])
        if disc_trade == 0.0:
            disc_trade = get_discount_item(["freebies", "discount"])
        if disc_trade == 0.0:
            m_t = re.search(r"(?:Restaurant\s*Discounts?\s*\([^)]*(?:trade|freebie)[^)]*\)|Trade\s*Discounts?[^\n\r]*?)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_t:
                disc_trade = abs(clean_number(m_t.group(1)))

        total_discount = round(disc_coupons + disc_trade, 2)
        data["discount_coupons"] = disc_coupons
        data["discount_trade"] = disc_trade
        data["total_discount"] = total_discount

        # Reconciliation
        sub = data.get("subtotal", 0.0)
        if sub > 0 and total_discount > 0:
            data["sales_after_discount"] = round(sub - total_discount, 2)

        # -------------------------------------------------------------
        # 4. PACKAGING CHARGES
        # -------------------------------------------------------------
        m_pack = re.search(r"(?:Packaging\s*Charges?|Packaging\s*Fee)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        data["packaging_charges"] = clean_number(m_pack.group(1)) if m_pack else 0.0

        # -------------------------------------------------------------
        # 5. COMMISSION = (B) Total Fees + TDS (under (D) Total Taxes)
        # -------------------------------------------------------------
        # (B) Total Fees
        total_fees = 0.0
        m_fees = re.search(r"(?:\(B\)\s*Total\s*Fees|Total\s*Fees\s*\(B\)?|Swiggy\s*Service\s*Fee|Commission\s*&\s*Service\s*Fees?)\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_fees:
            total_fees = abs(clean_number(m_fees.group(1)))
        else:
            fee_val = get_discount_item(["total fees"])
            if fee_val > 0:
                total_fees = fee_val

        # TDS under (D) Total Taxes
        tds_amount = 0.0
        m_tds = re.search(r"(?:TDS|Tax\s*Deducted\s*at\s*Source)\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_tds:
            tds_amount = abs(clean_number(m_tds.group(1)))
        else:
            tds_val = get_discount_item(["tds"])
            if tds_val > 0:
                tds_amount = tds_val

        commission = round(total_fees + tds_amount, 2)
        data["total_fees_B"] = total_fees
        data["tds_amount"] = tds_amount
        data["commission"] = commission

        # (D) Total Taxes total if present
        m_taxes = re.search(r"(?:\(D\)\s*Total\s*Taxes|Total\s*Taxes\s*\(D\)?)\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_taxes:
            data["total_taxes_D"] = abs(clean_number(m_taxes.group(1)))

        # -------------------------------------------------------------
        # 6. ADS: (E) Growth Investments in Ads
        # -------------------------------------------------------------
        m_ads = re.search(r"(?:\(E\)\s*Growth\s*Investments?\s*in\s*Ads|Growth\s*Investments?\s*in\s*Ads|Investments?\s*in\s*Ads|\(E\)\s*Ads\s*Spend|Swiggy\s*Ads?)\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_ads:
            data["ads"] = abs(clean_number(m_ads.group(1)))
        else:
            ads_val = get_discount_item(["growth investments", "ads"])
            if ads_val > 0:
                data["ads"] = ads_val
            else:
                data["ads"] = 0.0

        # -------------------------------------------------------------
        # 7. CASH IN BANK: Net Payout (Net Payout (A+B+C+D+E+F))
        # -------------------------------------------------------------
        m_payout = re.search(r"(?:Net\s*Payout\s*\(A\+B\+C\+D\+E\+F\)|Net\s*Payout|Total\s*Payout|Amount\s*Settled|Estimated\s*Payout)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_payout:
            data["cash_in_bank"] = clean_number(m_payout.group(1))
            data["net_payout"] = clean_number(m_payout.group(1))

        # Rejections if present
        m_rej = re.search(r"(?:Restaurant\s*Cancelled\s*Orders?|Cancelled\s*Orders?|Rejections?)\s*[:\n\r]*\s*([\d,]+)", combined_text, re.I)
        if m_rej:
            data["mx_rejections"] = clean_number(m_rej.group(1))

        return data
