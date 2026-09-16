// Zomato Finance / Payouts Scraper Content Script

(function() {
  if (window.__ZOMATO_PAYOUTS_SCRIPT_LOADED__) return;
  window.__ZOMATO_PAYOUTS_SCRIPT_LOADED__ = true;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function cleanNumber(val) {
    if (val === null || val === undefined || val === "") return 0.0;
    if (typeof val === "number") return isNaN(val) ? 0.0 : val;
    let s = String(val).trim();
    let isNeg = false;
    if (s.startsWith("-") || s.startsWith("–") || s.startsWith("—") || (s.startsWith("(") && s.endsWith(")"))) {
      isNeg = true;
      s = s.replace(/^[-–—(]+|[)]+$/g, "").trim();
    }
    s = s.replace(/₹/g, "").replace(/,/g, "").replace(/%/g, "").replace(/mins?/gi, "").trim();
    const num = parseFloat(s);
    if (!isNaN(num)) return isNeg ? -num : num;
    const match = s.match(/[-+]?\d+(?:\.\d+)?/);
    if (match) {
      const extracted = parseFloat(match[0]);
      return isNeg ? -extracted : extracted;
    }
    return 0.0;
  }

  async function selectPayoutCycleRow(startISO, endISO, dateLabel) {
    const sDate = new Date(startISO);
    const eDate = new Date(endISO);
    const sDay = String(sDate.getDate());
    const eDay = String(eDate.getDate());
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const sMonth = months[sDate.getMonth()].toLowerCase();
    const eMonth = months[eDate.getMonth()].toLowerCase();

    console.log(`[*] Locating payout cycle row for ${sDay} ${sMonth} - ${eDay} ${eMonth}...`);

    const rows = Array.from(document.querySelectorAll("tr, [role='row'], div[class*='row'], div[class*='item'], div[class*='card']"));
    for (const r of rows) {
      const txt = (r.innerText || "").toLowerCase();
      const hasMonth = txt.includes(sMonth) || txt.includes(eMonth);
      const hasStart = txt.includes(sDay) || (new RegExp(`\\b0?${sDay}\\b`)).test(txt);
      const hasEnd = txt.includes(eDay) || (new RegExp(`\\b0?${eDay}\\b`)).test(txt);

      if (hasMonth && hasStart && hasEnd && r.children.length < 10) {
        try {
          r.click();
          console.log(`[+] Clicked matching payout cycle row: "${txt.substring(0, 40)}..."`);
          await sleep(2500);
          return true;
        } catch (e) {
          console.warn("[!] Error clicking payout row:", e);
        }
      }
    }

    // Fallback: Click first row in table
    const firstRow = document.querySelector("table tbody tr, div[class*='table-body'] div[class*='row']");
    if (firstRow) {
      try {
        firstRow.click();
        console.log("[+] Clicked first row in Past cycles table as fallback.");
        await sleep(2000);
        return true;
      } catch (e) {}
    }

    return false;
  }

  async function expandDrawerAccordions() {
    console.log("[*] Expanding accordions inside Payout details side drawer...");
    const drawer = document.querySelector("[class*='drawer'], [class*='modal'], [class*='sheet'], [class*='sidebar'], [role='dialog'], [class*='details']") || document.body;

    const ariaClosed = Array.from(drawer.querySelectorAll("[aria-expanded='false']"));
    for (const el of ariaClosed) {
      try { el.click(); } catch(e) {}
    }

    const drawerText = (drawer.innerText || "").toLowerCase();
    if (!drawerText.includes("item subtotal")) {
      const sectionElements = Array.from(drawer.querySelectorAll("div, button, span, p")).filter(el => {
        const t = (el.innerText || "").trim();
        return (t.startsWith("Net order value") || t.startsWith("Tax deductions") || t.startsWith("Order level") || t.startsWith("Additions")) && el.children.length < 4;
      });
      for (const el of sectionElements) {
        try { el.click(); } catch(e) {}
      }
    }
    await sleep(1500);
  }

  function parsePayoutText(drawerText, allText) {
    const data = {};
    const combinedText = `${drawerText || ""}\n${allText || ""}`;
    const lines = combinedText.split("\n").map(l => l.trim()).filter(Boolean);

    // Restaurant Name
    const mRes = drawerText.match(/>\s*([A-Za-z0-9\s]+?)(?:\.\.\.|\n|$)/);
    if (mRes) {
      data.restaurant_name = mRes[1].trim();
    }

    // 1. Delivered orders (payout page)
    const mOrders = combinedText.match(/(?:Delivered orders|Total orders|Orders delivered)\s*[:\n\r]*\s*([\d,]+)/i);
    if (mOrders) {
      data.payout_delivered_orders = cleanNumber(mOrders[1]);
    }

    // 2. Net order value (A) / Sales after discount
    const mNov = combinedText.match(/Net order value\s*(?:\(A\))?[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mNov) {
      data.net_order_value_amount = cleanNumber(mNov[1]);
      data.sales_after_discount = cleanNumber(mNov[1]);
    }

    function getItemValue(keywords, maxLookahead = 3) {
      for (let idx = 0; idx < lines.length; idx++) {
        const lLow = lines[idx].toLowerCase();
        if (keywords.every(kw => lLow.includes(kw.toLowerCase()))) {
          for (let j = idx + 1; j < Math.min(idx + 1 + maxLookahead, lines.length); j++) {
            const nextL = lines[j];
            if (["additions", "order level", "tax deductions", "investments in growth"].some(k => nextL.toLowerCase().includes(k))) {
              break;
            }
            const mNext = nextL.match(/[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/);
            if (mNext) {
              const val = Math.abs(cleanNumber(mNext[1]));
              if (val > 0) return val;
              break;
            }
          }
        }
      }
      return 0.0;
    }

    // 3. Item Subtotal
    const mSubtotal = combinedText.match(/(?:Item\s*Subtotal|Item\s*Total|Gross\s*Sales)[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)/i);
    let subtotalVal = mSubtotal ? cleanNumber(mSubtotal[1]) : 0.0;
    if (subtotalVal === 0.0) {
      subtotalVal = getItemValue(["item subtotal"]) || getItemValue(["item total"]);
    }
    if (subtotalVal > 0.0) {
      data.subtotal = subtotalVal;
      data.item_subtotal = subtotalVal;
    }

    // 4. Discounts
    function getItemDiscount(keywords) {
      for (let idx = 0; idx < lines.length; idx++) {
        const lLow = lines[idx].toLowerCase();
        if (keywords.every(kw => lLow.includes(kw.toLowerCase()))) {
          const mNeg = lines[idx].match(/[-–—]\s*₹?\s*([\d,]+(?:\.\d+)?)/g);
          if (mNeg) {
            const val = Math.abs(cleanNumber(mNeg[mNeg.length - 1]));
            if (val > 0) return val;
          }
          for (let j = idx + 1; j < Math.min(idx + 4, lines.length); j++) {
            const nextL = lines[j];
            if (["gst", "subtotal", "net order", "additions", "packaging", "order level"].some(k => nextL.toLowerCase().includes(k))) {
              break;
            }
            const mNext = nextL.match(/[-–—]?\s*₹\s*([\d,]+(?:\.\d+)?)/);
            if (mNext) {
              const val = Math.abs(cleanNumber(mNext[1]));
              if (val > 0) return val;
              break;
            }
          }
        }
      }
      return 0.0;
    }

    let discPromos = getItemDiscount(["restaurant discount", "promos"]) || getItemDiscount(["promos"]);
    if (discPromos === 0.0) {
      const mP = combinedText.match(/(?:Restaurant discount\s*\(Promos\)|Promos(?:\s*discount)?)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
      if (mP) discPromos = Math.abs(cleanNumber(mP[1]));
    }

    let discFlatOffs = getItemDiscount(["flat offs"]) || getItemDiscount(["freebies"]) || getItemDiscount(["gold", "discount"]) || getItemDiscount(["relisted"]);
    if (discFlatOffs === 0.0) {
      const mF = combinedText.match(/(?:Restaurant discount\s*\([^)]*(?:flat off|freebie|gold|relisted)[^)]*\)|Flat offs[^\n\r]*?discount)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
      if (mF) discFlatOffs = Math.abs(cleanNumber(mF[1]));
    }

    let discDelivery = getItemDiscount(["delivery", "discount"]);
    if (discDelivery === 0.0) {
      const mD = combinedText.match(/(?:Delivery charge discount|Delivery fee discount|Delivery discount)[^\d\n\r]{0,30}[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
      if (mD) discDelivery = Math.abs(cleanNumber(mD[1]));
    }

    const totalDiscount = Number((discPromos + discFlatOffs + discDelivery).toFixed(2));
    data.discount_promos = discPromos;
    data.discount_flat_offs = discFlatOffs;
    data.discount_delivery = discDelivery;
    data.total_discount = totalDiscount;

    // 5. Packaging Charges
    const mPack = combinedText.match(/(?:Packaging Charges?|Packaging Fee)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    data.packaging_charges = mPack ? cleanNumber(mPack[1]) : 0.0;

    // 6. Additions (B)
    const mAdd = combinedText.match(/Additions\s*(?:\(B\))?\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mAdd) data.additions = cleanNumber(mAdd[1]);

    // 7. Order Level Deductions (C)
    const mOrderDed = combinedText.match(/Order level deductions?\s*(?:\(C\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mOrderDed) data.order_level_deductions = cleanNumber(mOrderDed[1]);

    // 8. GST 18% & Tax Deductions (D)
    const mGst18 = combinedText.match(/GST on service and payment mechanism fees\s*@\s*18%\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mGst18) data.gst_fee_18 = cleanNumber(mGst18[1]);

    const mTaxDed = combinedText.match(/Tax deductions?\s*(?:\(D\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mTaxDed) data.tax_deductions = cleanNumber(mTaxDed[1]);

    const orderDed = data.order_level_deductions || 0.0;
    const gstFee = data.gst_fee_18 || data.tax_deductions || 0.0;
    if (orderDed || gstFee) {
      data.commission = Number((orderDed + gstFee).toFixed(2));
    }

    // 9. Investments in growth (E) / Ads
    const mAds = combinedText.match(/Investments? in growth\s*(?:\(E\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mAds) data.ads = cleanNumber(mAds[1]);

    // 10. Hyperpure spend (F)
    const mHyper = combinedText.match(/Hyperpure spend\s*(?:\(F\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mHyper) data.hyperpure_spend = cleanNumber(mHyper[1]);

    // 11. Est Payout / Cash in Bank
    const mPayout = combinedText.match(/(?:Est\.?\s*payout|Estimated payout|Net payout|Amount Settled)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mPayout) {
      data.est_payout = cleanNumber(mPayout[1]);
      data.cash_in_bank = cleanNumber(mPayout[1]);
    }

    // 12. Rejected Orders
    const mRej = combinedText.match(/(?:Rejected orders|Rejections|Mx Rejections)\s*[:\n\r]*\s*([\d,]+)/i);
    if (mRej) {
      data.rejected_orders = cleanNumber(mRej[1]);
      data.mx_rejections = cleanNumber(mRej[1]);
    }

    return data;
  }

  async function scrapePayouts(req) {
    console.log(`[*] Scraping Payouts tab for range: ${req.dateLabel} (${req.startISO} to ${req.endISO})...`);
    await selectPayoutCycleRow(req.startISO, req.endISO, req.dateLabel);
    await sleep(2500);

    await expandDrawerAccordions();
    await sleep(1500);

    const drawer = document.querySelector("[class*='drawer'], [class*='modal'], [class*='sheet'], [class*='sidebar'], [class*='details']") || document.body;
    const drawerText = drawer ? drawer.innerText : "";
    const allText = document.body ? document.body.innerText : "";

    const parsed = parsePayoutText(drawerText, allText);
    console.log("[✓] Extracted Payouts Metrics:", parsed);

    return { success: true, data: parsed };
  }

  chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    if (req.action === "SCRAPE_PAYOUTS") {
      scrapePayouts(req).then(res => sendResponse(res)).catch(err => sendResponse({ success: false, error: err.message }));
      return true;
    }
  });
})();
