import re
from typing import Dict, Any, List, Optional
from processors.metric_calculator import clean_number


class PayoutParser:
    """
    Pure data and text parser for Zomato Payout details side drawer.
    Extracts financial breakdown, discount components, deductions, ads, and cash in bank.
    Completely decoupled from Playwright/Browser state for easy isolated unit testing.
    """

    @staticmethod
    def parse_payout_text(drawer_text: str, all_text: str = "") -> Dict[str, Any]:
        """
        Parses financial fields from the Payout side drawer and page text.
        """
        data: Dict[str, Any] = {}
        combined_text = (drawer_text or "") + "\n" + (all_text or "")

        # Extract Restaurant Name
        m_res = re.search(r">\s*([A-Za-z0-9\s]+?)(?:\.\.\.|\n|$)", drawer_text)
        if m_res:
            data["restaurant_name"] = m_res.group(1).strip()

        # 1. Delivered orders (payout page)
        m_orders = re.search(r"(?:Delivered orders|Total orders|Orders delivered)\s*[:\n\r]*\s*([\d,]+)", combined_text, re.I)
        if m_orders:
            data["payout_delivered_orders"] = clean_number(m_orders.group(1))

        # 2. Net order value (A) / Sales after discount
        m_nov = re.search(r"Net order value\s*(?:\(A\))?[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_nov:
            data["net_order_value_amount"] = clean_number(m_nov.group(1))
            data["sales_after_discount"] = clean_number(m_nov.group(1))

        lines = [l.strip() for l in combined_text.splitlines() if l.strip()]

        def get_item_value(keywords: List[str], max_lookahead: int = 3) -> float:
            for idx, l in enumerate(lines):
                l_low = l.lower().strip()
                if all(kw.lower() in l_low for kw in keywords):
                    # Check next lines for ₹ amount
                    for j in range(idx + 1, min(idx + 1 + max_lookahead, len(lines))):
                        next_l = lines[j]
                        if any(k in next_l.lower() for k in ["additions", "order level", "tax deductions", "investments in growth"]):
                            break
                        m_next = re.search(r'[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)', next_l)
                        if m_next:
                            val = abs(clean_number(m_next.group(1)))
                            if val > 0:
                                return val
                            break
            return 0.0

        # 3. Item subtotal (under Net Order Value)
        m_subtotal = re.search(r"(?:Item\s*Subtotal|Item\s*Total|Gross\s*Sales)[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        subtotal_val = clean_number(m_subtotal.group(1)) if m_subtotal else 0.0
        if subtotal_val == 0.0:
            subtotal_val = get_item_value(["item subtotal"]) or get_item_value(["item total"])
        if subtotal_val > 0.0:
            data["subtotal"] = subtotal_val
            data["item_subtotal"] = subtotal_val

        # 4. Total Discounts (formula as specified):
        #    Total Discount = Restaurant discount (Promos)
        #                   + Restaurant discount (Flat offs, Freebies, Gold, relisted orders and others)
        #                   + Delivery charge discount (0 if not exists)
        def get_item_discount(keywords: List[str]) -> float:
            for idx, l in enumerate(lines):
                l_low = l.lower().strip()
                if all(kw.lower() in l_low for kw in keywords):
                    # Check for - ₹ amount on the same line
                    m_neg = re.findall(r'[-–—]\s*₹?\s*([\d,]+(?:\.\d+)?)', l)
                    if m_neg:
                        val = abs(clean_number(m_neg[-1]))
                        if val > 0:
                            return val
                    # Check next 1-3 lines for ₹ amount
                    for j in range(idx + 1, min(idx + 4, len(lines))):
                        next_l = lines[j]
                        if any(k in next_l.lower() for k in ["gst", "subtotal", "net order", "additions", "packaging", "order level", "delivery charge", "restaurant discount"]):
                            break
                        m_next = re.search(r'[-–—]?\s*₹\s*([\d,]+(?:\.\d+)?)', next_l)
                        if m_next:
                            val = abs(clean_number(m_next.group(1)))
                            if val > 0:
                                return val
                            break
            return 0.0

        # Item 1: Restaurant discount (Promos)
        disc_promos = get_item_discount(["restaurant discount", "promos"])
        if disc_promos == 0.0:
            disc_promos = get_item_discount(["promos"])
        if disc_promos == 0.0:
            m_p = re.search(r"(?:Restaurant discount\s*\(Promos\)|Promos(?:\s*discount)?)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_p:
                disc_promos = abs(clean_number(m_p.group(1)))

        # Item 2: Restaurant discount (Flat offs, Freebies, Gold, relisted orders and others)
        disc_flat_offs = get_item_discount(["flat offs"])
        if disc_flat_offs == 0.0:
            disc_flat_offs = get_item_discount(["freebies"])
        if disc_flat_offs == 0.0:
            disc_flat_offs = get_item_discount(["gold", "discount"])
        if disc_flat_offs == 0.0:
            disc_flat_offs = get_item_discount(["relisted"])
        if disc_flat_offs == 0.0:
            m_f = re.search(r"(?:Restaurant discount\s*\([^)]*(?:flat off|freebie|gold|relisted)[^)]*\)|Flat offs[^\n\r]*?discount)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_f:
                disc_flat_offs = abs(clean_number(m_f.group(1)))

        # Item 3: Delivery charge discount (0 if not exists)
        disc_delivery = get_item_discount(["delivery", "discount"])
        if disc_delivery == 0.0:
            m_d = re.search(r"(?:Delivery charge discount|Delivery fee discount|Delivery discount)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
            if m_d:
                disc_delivery = abs(clean_number(m_d.group(1)))

        total_discount = round(disc_promos + disc_flat_offs + disc_delivery, 2)
        data["discount_promos"] = disc_promos
        data["discount_flat_offs"] = disc_flat_offs
        data["discount_delivery"] = disc_delivery
        data["total_discount"] = total_discount

        # Reconciliation: Subtotal vs Net Order Value vs Discount
        nov = data.get("net_order_value_amount", 0.0)
        sub = data.get("subtotal", 0.0)
        if sub > 0 and nov > 0 and sub > nov and total_discount == 0.0:
            total_discount = round(sub - nov, 2)
            data["total_discount"] = total_discount
        elif nov > 0 and total_discount > 0 and sub == 0.0:
            sub = round(nov + total_discount, 2)
            data["subtotal"] = sub
            data["item_subtotal"] = sub
        elif sub > 0 and total_discount > 0 and nov == 0.0:
            data["net_order_value_amount"] = round(sub - total_discount, 2)
            data["sales_after_discount"] = data["net_order_value_amount"]

        # 5. Packaging Charges
        m_pack = re.search(r"(?:Packaging Charges?|Packaging Fee)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        data["packaging_charges"] = clean_number(m_pack.group(1)) if m_pack else 0.0

        # 6. Additions (B)
        m_add = re.search(r"Additions\s*(?:\(B\))?\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_add:
            data["additions"] = clean_number(m_add.group(1))

        # 7. Order level deductions (C)
        m_order_ded = re.search(r"Order level deductions?\s*(?:\(C\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_order_ded:
            data["order_level_deductions"] = clean_number(m_order_ded.group(1))

        # 8. Tax deductions (D) total & specific GST on service and payment mechanism fees @18%
        m_gst_18 = re.search(r"GST on service and payment mechanism fees\s*@\s*18%\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_gst_18:
            data["gst_fee_18"] = clean_number(m_gst_18.group(1))

        m_tax_ded = re.search(r"Tax deductions?\s*(?:\(D\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_tax_ded:
            data["tax_deductions"] = clean_number(m_tax_ded.group(1))

        # Commission = Order level deductions + GST on service and payment mechanism fees @18%
        order_ded = data.get("order_level_deductions", 0.0)
        gst_fee = data.get("gst_fee_18", 0.0)
        if order_ded and gst_fee:
            data["commission"] = round(order_ded + gst_fee, 2)
        elif order_ded and "tax_deductions" in data:
            data["commission"] = round(order_ded + data["tax_deductions"], 2)

        # 9. Investments in growth (E) / Ads
        m_ads = re.search(r"Investments? in growth\s*(?:\(E\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_ads:
            data["ads"] = clean_number(m_ads.group(1))

        # 10. Hyperpure spend (F)
        m_hyper = re.search(r"Hyperpure spend\s*(?:\(F\))?\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_hyper:
            data["hyperpure_spend"] = clean_number(m_hyper.group(1))

        # 11. Est payout / Net payout -> Cash in Bank
        m_payout = re.search(r"(?:Est\.?\s*payout|Estimated payout|Net payout|Amount Settled)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)", combined_text, re.I)
        if m_payout:
            data["est_payout"] = clean_number(m_payout.group(1))
            data["cash_in_bank"] = clean_number(m_payout.group(1))

        # 12. Rejected orders (under payout section)
        m_rej = re.search(r"(?:Rejected orders|Rejections|Mx Rejections)\s*[:\n\r]*\s*([\d,]+)", combined_text, re.I)
        if m_rej:
            data["rejected_orders"] = clean_number(m_rej.group(1))
            data["mx_rejections"] = clean_number(m_rej.group(1))

        return data
