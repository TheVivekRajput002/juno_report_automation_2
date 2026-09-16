// Metric Calculator & Business Logic Engine

export function cleanNumber(val) {
  if (val === null || val === undefined || val === "") {
    return 0.0;
  }
  if (typeof val === "number") {
    return isNaN(val) ? 0.0 : val;
  }
  let s = String(val).trim();
  let isNeg = false;
  if (s.startsWith("-") || s.startsWith("–") || s.startsWith("—") || (s.startsWith("(") && s.endsWith(")"))) {
    isNeg = true;
    s = s.replace(/^[-–—(]+|[)]+$/g, "").trim();
  }

  // Strip currency symbols, commas, percent, units
  s = s.replace(/₹/g, "").replace(/,/g, "").replace(/%/g, "").replace(/mins?/gi, "").trim();

  const num = parseFloat(s);
  if (!isNaN(num)) {
    return isNeg ? -num : num;
  }

  const match = s.match(/[-+]?\d+(?:\.\d+)?/);
  if (match) {
    const extracted = parseFloat(match[0]);
    return isNeg ? -extracted : extracted;
  }
  return 0.0;
}

export function fmtPct(val) {
  if (val === null || val === undefined || val === "" || isNaN(val)) {
    return "0.00%";
  }
  let v = Number(val);
  if (v > 0 && v <= 1.0) {
    v = v * 100.0;
  }
  return `${v.toFixed(2)}%`;
}

export function fmtInt(val) {
  if (val === null || val === undefined || val === "" || isNaN(val)) {
    return 0;
  }
  return Math.round(Number(val));
}

export class MetricCalculator {
  static calculateZomatoMetrics(raw) {
    const orders = cleanNumber(
      raw.reporting_orders ||
      raw.delivered_orders ||
      raw.orders ||
      raw.payout_delivered_orders ||
      0
    );

    const reporting_sales = cleanNumber(raw.reporting_sales || raw.sales_after_discount || raw.sales || 0);
    const nov_payout = cleanNumber(raw.net_order_value_amount || raw.net_order_value_A || raw.nov_amount || 0);
    const net_sales = nov_payout > 0 ? nov_payout : reporting_sales;

    const disc_promos = Math.abs(cleanNumber(raw.discount_promos || 0));
    const disc_flat = Math.abs(cleanNumber(raw.discount_flat_offs || 0));
    const disc_deliv = Math.abs(cleanNumber(raw.discount_delivery || 0));
    const scraped_discount = cleanNumber(raw.total_discount) || Number((disc_promos + disc_flat + disc_deliv).toFixed(2));

    const raw_sub = cleanNumber(raw.item_subtotal || raw.subtotal || 0);
    const item_subtotal = (raw_sub === reporting_sales && raw_sub > 0 && scraped_discount > 0) ? 0.0 : raw_sub;

    let subtotal = 0.0;
    let total_discount = 0.0;
    let sales_after_discount = 0.0;

    // Mathematical Reconciliation:
    if (item_subtotal > 0 && scraped_discount > 0) {
      subtotal = item_subtotal;
      total_discount = scraped_discount;
      sales_after_discount = Number((subtotal - total_discount).toFixed(2));
    } else if (item_subtotal > 0 && net_sales > 0 && item_subtotal >= net_sales) {
      subtotal = item_subtotal;
      total_discount = scraped_discount === 0 ? Number((subtotal - net_sales).toFixed(2)) : scraped_discount;
      sales_after_discount = Number((subtotal - total_discount).toFixed(2));
    } else if (net_sales > 0 && scraped_discount > 0) {
      total_discount = scraped_discount;
      sales_after_discount = net_sales;
      subtotal = Number((sales_after_discount + total_discount).toFixed(2));
    } else if (item_subtotal > 0) {
      subtotal = item_subtotal;
      total_discount = scraped_discount;
      sales_after_discount = Number((subtotal - total_discount).toFixed(2));
    } else if (net_sales > 0) {
      total_discount = scraped_discount;
      sales_after_discount = net_sales;
      subtotal = Number((sales_after_discount + total_discount).toFixed(2));
    }

    let net_order_value = 0.0;
    if (orders > 0 && sales_after_discount > 0) {
      net_order_value = Number((sales_after_discount / orders).toFixed(2));
    } else if (raw.net_order_value || raw.aov || raw.average_order_value) {
      net_order_value = cleanNumber(raw.net_order_value || raw.aov || raw.average_order_value);
    }

    const packaging_charges = cleanNumber(raw.packaging_charges || 0);

    // Commission = Order level deductions + GST on service and payment mechanism fees @18%
    const order_ded = Math.abs(cleanNumber(raw.order_level_deductions || raw.order_level_deductions_C || 0));
    const gst_18 = Math.abs(cleanNumber(raw.gst_fee_18 || raw.gst_tax_deductions || raw.tax_deductions || 0));
    const commission = cleanNumber(raw.commission) || Number((order_ded + gst_18).toFixed(2));

    // Ads: Investments in Growth (E)
    const ads = Math.abs(cleanNumber(raw.ads || raw.investments_in_growth || raw.investments_in_growth_E || 0));

    // Cash in bank = est payout
    const cash_in_bank = cleanNumber(raw.est_payout || raw.cash_in_bank || raw.net_payout || 0);

    // Financial Percentages (0 to 100 scale)
    const discount_pct = subtotal > 0 ? (total_discount / subtotal * 100) : 0.0;
    const commission_pct = sales_after_discount > 0 ? (commission / sales_after_discount * 100) : 0.0;
    const ads_pct = subtotal > 0 ? (ads / subtotal * 100) : 0.0;
    const payout_pct = subtotal > 0 ? (cash_in_bank / subtotal * 100) : 0.0;

    // Operational & Funnel Metrics
    let visibility = cleanNumber(raw.visibility || raw.online_pct || 0);
    if (visibility < 0) visibility = 0.0;
    else if (visibility > 0 && visibility <= 1.0) visibility = visibility * 100.0;

    const kpt = Math.max(0.0, cleanNumber(raw.kpt || raw.kitchen_prep_time || 0));
    const impressions = Math.max(0.0, cleanNumber(raw.impressions || 0));

    let i2m_raw = cleanNumber(raw.i2m || raw.impression_to_menu || 0);
    let i2m = i2m_raw < 0 ? 0.0 : i2m_raw;
    if (i2m > 0 && i2m <= 1.0) i2m = i2m * 100.0;

    const menu_opens_raw = Math.max(0.0, cleanNumber(raw.menu_opens || 0));
    let menu_opens = 0.0;
    if (menu_opens_raw > 0) {
      menu_opens = menu_opens_raw;
      if (i2m === 0.0 && impressions > 0) {
        i2m = Number(((menu_opens / impressions) * 100.0).toFixed(2));
      }
    } else if (impressions > 0 && i2m > 0) {
      menu_opens = Math.round(impressions * (i2m / 100.0));
    }

    let c2o_raw = cleanNumber(raw.c2o || raw.cart_to_order || 0);
    let c2o = c2o_raw < 0 ? 0.0 : c2o_raw;
    if (c2o > 0 && c2o <= 1.0) c2o = c2o * 100.0;

    let m2o_raw = cleanNumber(raw.m2o || raw.menu_to_order || 0);
    let m2o = m2o_raw < 0 ? 0.0 : m2o_raw;
    if (m2o > 0 && m2o <= 1.0) {
      m2o = m2o * 100.0;
    } else if (m2o === 0.0 && orders > 0 && menu_opens > 0) {
      m2o = Number(((orders / menu_opens) * 100.0).toFixed(2));
    }

    const mx_rejections = Math.max(0.0, cleanNumber(raw.rejected_orders || raw.mx_rejections || 0));

    return {
      orders,
      subtotal,
      total_discount,
      sales_after_discount,
      net_order_value,
      packaging_charges,
      commission,
      ads,
      cash_in_bank,
      discount_pct,
      commission_pct,
      ads_pct,
      payout_pct,
      visibility,
      kpt,
      impressions,
      i2m,
      menu_opens,
      c2o,
      m2o,
      mx_rejections,
      raw_data: raw
    };
  }

  /**
   * Generates the 21 row definitions for Google Sheets / Excel table matching the exact template.
   */
  static buildRowsConfig(zm, sm = null) {
    const hasZ = zm !== null;
    const hasS = sm !== null;
    const z = zm || {};
    const s = sm || {};

    // Calculate Z+S combined
    const zs_orders = (z.orders || 0) + (s.orders || 0);
    const zs_subtotal = Number(((z.subtotal || 0) + (s.subtotal || 0)).toFixed(2));
    const zs_total_discount = Number(((z.total_discount || 0) + (s.total_discount || 0)).toFixed(2));
    const zs_sales_after_discount = Number((zs_subtotal - zs_total_discount).toFixed(2));
    const zs_net_order_value = zs_orders > 0 ? Number((zs_sales_after_discount / zs_orders).toFixed(2)) : 0;
    const zs_packaging = Number(((z.packaging_charges || 0) + (s.packaging_charges || 0)).toFixed(2));
    const zs_commission = Number(((z.commission || 0) + (s.commission || 0)).toFixed(2));
    const zs_ads = Number(((z.ads || 0) + (s.ads || 0)).toFixed(2));
    const zs_cash_in_bank = Number(((z.cash_in_bank || 0) + (s.cash_in_bank || 0)).toFixed(2));

    const zs_discount_pct = zs_subtotal > 0 ? fmtPct(zs_total_discount / zs_subtotal * 100) : "0.00%";
    const zs_commission_pct = zs_sales_after_discount > 0 ? fmtPct(zs_commission / zs_sales_after_discount * 100) : "0.00%";
    const zs_ads_pct = zs_subtotal > 0 ? fmtPct(zs_ads / zs_subtotal * 100) : "0.00%";
    const zs_payout_pct = zs_subtotal > 0 ? fmtPct(zs_cash_in_bank / zs_subtotal * 100) : "0.00%";

    const zs_visibility = fmtPct(
      (z.visibility > 0 && s.visibility > 0)
        ? (z.visibility + s.visibility) / 2
        : (z.visibility || s.visibility || 0)
    );
    const zs_kpt = (z.kpt > 0 && s.kpt > 0) ? Math.round((z.kpt + s.kpt) / 2) : (z.kpt || s.kpt || 0);
    const zs_impressions = (z.impressions || 0) + (s.impressions || 0);
    const zs_i2m = fmtPct(
      (z.i2m > 0 && s.i2m > 0)
        ? (z.i2m + s.i2m) / 2
        : (z.i2m || s.i2m || 0)
    );
    const zs_menu_opens = (z.menu_opens || 0) + (s.menu_opens || 0);
    const zs_c2o = fmtPct(
      (z.c2o > 0 && s.c2o > 0)
        ? (z.c2o + s.c2o) / 2
        : (z.c2o || s.c2o || 0)
    );
    const zs_m2o = fmtPct(
      (z.m2o > 0 && s.m2o > 0)
        ? (z.m2o + s.m2o) / 2
        : (z.m2o || s.m2o || 0)
    );
    const zs_mx_rejections = (z.mx_rejections || 0) + (s.mx_rejections || 0);

    return [
      { name: "Orders", z_val: hasZ ? fmtInt(z.orders) : "", s_val: hasS ? fmtInt(s.orders) : "", zs_val: fmtInt(zs_orders), highlight: false, bold: false },
      { name: "Subtotal", z_val: hasZ ? fmtInt(z.subtotal) : "", s_val: hasS ? fmtInt(s.subtotal) : "", zs_val: fmtInt(zs_subtotal), highlight: false, bold: false },
      { name: "Total Discount", z_val: hasZ ? fmtInt(z.total_discount) : "", s_val: hasS ? fmtInt(s.total_discount) : "", zs_val: fmtInt(zs_total_discount), highlight: false, bold: false },
      { name: "Sales after discount", z_val: hasZ ? fmtInt(z.sales_after_discount) : "", s_val: hasS ? fmtInt(s.sales_after_discount) : "", zs_val: fmtInt(zs_sales_after_discount), highlight: false, bold: false },
      { name: "Net order value", z_val: hasZ ? fmtInt(z.net_order_value) : "", s_val: hasS ? fmtInt(s.net_order_value) : "", zs_val: fmtInt(zs_net_order_value), highlight: false, bold: false },
      { name: "Packaging Charges", z_val: hasZ ? fmtInt(z.packaging_charges) : "", s_val: hasS ? fmtInt(s.packaging_charges) : "", zs_val: fmtInt(zs_packaging), highlight: false, bold: false },
      { name: "Commission", z_val: hasZ ? fmtInt(z.commission) : "", s_val: hasS ? fmtInt(s.commission) : "", zs_val: fmtInt(zs_commission), highlight: false, bold: false },
      { name: "ads", z_val: hasZ ? fmtInt(z.ads) : "", s_val: hasS ? fmtInt(s.ads) : "", zs_val: fmtInt(zs_ads), highlight: false, bold: false },
      { name: "Cash in Bank", z_val: hasZ ? fmtInt(z.cash_in_bank) : "", s_val: hasS ? fmtInt(s.cash_in_bank) : "", zs_val: fmtInt(zs_cash_in_bank), highlight: true, bold: true },
      { name: "Discount %", z_val: hasZ ? fmtPct(z.discount_pct) : "", s_val: hasS ? fmtPct(s.discount_pct) : "", zs_val: zs_discount_pct, highlight: false, bold: false },
      { name: "Commission %", z_val: hasZ ? fmtPct(z.commission_pct) : "", s_val: hasS ? fmtPct(s.commission_pct) : "", zs_val: zs_commission_pct, highlight: false, bold: false },
      { name: "Ads %", z_val: hasZ ? fmtPct(z.ads_pct) : "", s_val: hasS ? fmtPct(s.ads_pct) : "", zs_val: zs_ads_pct, highlight: false, bold: false },
      { name: "Payout %", z_val: hasZ ? fmtPct(z.payout_pct) : "", s_val: hasS ? fmtPct(s.payout_pct) : "", zs_val: zs_payout_pct, highlight: true, bold: true },
      { name: "Visibility", z_val: hasZ ? fmtPct(z.visibility) : "", s_val: hasS ? fmtPct(s.visibility) : "", zs_val: zs_visibility, highlight: false, bold: false },
      { name: "KPT", z_val: hasZ ? fmtInt(z.kpt) : "", s_val: hasS ? fmtInt(s.kpt) : "", zs_val: fmtInt(zs_kpt), highlight: false, bold: false },
      { name: "Impressions", z_val: hasZ ? fmtInt(z.impressions) : "", s_val: hasS ? fmtInt(s.impressions) : "", zs_val: fmtInt(zs_impressions), highlight: false, bold: false },
      { name: "I2M", z_val: hasZ ? fmtPct(z.i2m) : "", s_val: hasS ? fmtPct(s.i2m) : "", zs_val: zs_i2m, highlight: false, bold: false },
      { name: "Menu Opens", z_val: hasZ ? fmtInt(z.menu_opens) : "", s_val: hasS ? fmtInt(s.menu_opens) : "", zs_val: fmtInt(zs_menu_opens), highlight: false, bold: false },
      { name: "C2O", z_val: hasZ ? fmtPct(z.c2o) : "", s_val: hasS ? fmtPct(s.c2o) : "", zs_val: zs_c2o, highlight: false, bold: false },
      { name: "M2O", z_val: hasZ ? fmtPct(z.m2o) : "", s_val: hasS ? fmtPct(s.m2o) : "", zs_val: zs_m2o, highlight: false, bold: true },
      { name: "Mx Rejections", z_val: hasZ ? fmtInt(z.mx_rejections) : "", s_val: hasS ? fmtInt(s.mx_rejections) : "", zs_val: fmtInt(zs_mx_rejections), highlight: false, bold: false }
    ];
  }
}
