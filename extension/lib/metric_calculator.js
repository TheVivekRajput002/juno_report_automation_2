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

export function colIndexToA1(cIdx) {
  let result = "";
  let c = cIdx + 1;
  while (c > 0) {
    const remainder = (c - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    c = Math.floor((c - 1) / 26);
  }
  return result;
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
   * Uses dynamic formulas for the Z+S column referencing Zomato and Swiggy columns.
   */
  static buildRowsConfig(zm, sm = null, options = {}) {
    const hasZ = zm !== null;
    const hasS = sm !== null;
    const z = zm || {};
    const s = sm || {};

    const startCol = options.startCol !== undefined ? options.startCol : 0;
    const startRow = options.startRow !== undefined ? options.startRow : 0;
    const useFormulas = options.useFormulas !== undefined ? options.useFormulas : true;

    // A1 notation columns
    const zCol = colIndexToA1(startCol + 1);
    const sCol = colIndexToA1(startCol + 2);
    const zsCol = colIndexToA1(startCol + 3);

    // 1-indexed row numbers: Table Row 1-3 headers, Row 4 column titles, Row 5+ data rows
    const rBase = startRow + 5;
    const rOrders = rBase + 0;
    const rSubtotal = rBase + 1;
    const rDiscount = rBase + 2;
    const rSales = rBase + 3;
    const rNov = rBase + 4;
    const rPkg = rBase + 5;
    const rComm = rBase + 6;
    const rAds = rBase + 7;
    const rCib = rBase + 8;
    const rDiscPct = rBase + 9;
    const rCommPct = rBase + 10;
    const rAdsPct = rBase + 11;
    const rPayoutPct = rBase + 12;
    const rVis = rBase + 13;
    const rKpt = rBase + 14;
    const rImp = rBase + 15;
    const rI2m = rBase + 16;
    const rMenu = rBase + 17;
    const rC2o = rBase + 18;
    const rM2o = rBase + 19;
    const rMx = rBase + 20;

    // Pre-calculated values (used as fallback or for direct calculation)
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
      {
        name: "Orders",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.orders) : "",
        s_val: hasS ? fmtInt(s.orders) : "",
        zs_val: useFormulas ? `=${zCol}${rOrders}+${sCol}${rOrders}` : fmtInt(zs_orders),
        zs_calculated: fmtInt(zs_orders),
        highlight: false,
        bold: false
      },
      {
        name: "Subtotal",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.subtotal) : "",
        s_val: hasS ? fmtInt(s.subtotal) : "",
        zs_val: useFormulas ? `=${zCol}${rSubtotal}+${sCol}${rSubtotal}` : fmtInt(zs_subtotal),
        zs_calculated: fmtInt(zs_subtotal),
        highlight: false,
        bold: false
      },
      {
        name: "Total Discount",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.total_discount) : "",
        s_val: hasS ? fmtInt(s.total_discount) : "",
        zs_val: useFormulas ? `=${zCol}${rDiscount}+${sCol}${rDiscount}` : fmtInt(zs_total_discount),
        zs_calculated: fmtInt(zs_total_discount),
        highlight: false,
        bold: false
      },
      {
        name: "Sales after discount",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.sales_after_discount) : "",
        s_val: hasS ? fmtInt(s.sales_after_discount) : "",
        zs_val: useFormulas ? `=${zCol}${rSales}+${sCol}${rSales}` : fmtInt(zs_sales_after_discount),
        zs_calculated: fmtInt(zs_sales_after_discount),
        highlight: false,
        bold: false
      },
      {
        name: "Net order value",
        formatType: "dec",
        z_val: hasZ ? fmtInt(z.net_order_value) : "",
        s_val: hasS ? fmtInt(s.net_order_value) : "",
        zs_val: useFormulas ? `=IFERROR(ROUND(${zsCol}${rSales}/${zsCol}${rOrders}, 2), 0)` : fmtInt(zs_net_order_value),
        zs_calculated: fmtInt(zs_net_order_value),
        highlight: false,
        bold: false
      },
      {
        name: "Packaging Charges",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.packaging_charges) : "",
        s_val: hasS ? fmtInt(s.packaging_charges) : "",
        zs_val: useFormulas ? `=${zCol}${rPkg}+${sCol}${rPkg}` : fmtInt(zs_packaging),
        zs_calculated: fmtInt(zs_packaging),
        highlight: false,
        bold: false
      },
      {
        name: "Commission",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.commission) : "",
        s_val: hasS ? fmtInt(s.commission) : "",
        zs_val: useFormulas ? `=${zCol}${rComm}+${sCol}${rComm}` : fmtInt(zs_commission),
        zs_calculated: fmtInt(zs_commission),
        highlight: false,
        bold: false
      },
      {
        name: "ads",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.ads) : "",
        s_val: hasS ? fmtInt(s.ads) : "",
        zs_val: useFormulas ? `=${zCol}${rAds}+${sCol}${rAds}` : fmtInt(zs_ads),
        zs_calculated: fmtInt(zs_ads),
        highlight: false,
        bold: false
      },
      {
        name: "Cash in Bank",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.cash_in_bank) : "",
        s_val: hasS ? fmtInt(s.cash_in_bank) : "",
        zs_val: useFormulas ? `=${zCol}${rCib}+${sCol}${rCib}` : fmtInt(zs_cash_in_bank),
        zs_calculated: fmtInt(zs_cash_in_bank),
        highlight: true,
        bold: true
      },
      {
        name: "Discount %",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.discount_pct) : "",
        s_val: hasS ? fmtPct(s.discount_pct) : "",
        zs_val: useFormulas ? `=IFERROR(${zsCol}${rDiscount}/${zsCol}${rSubtotal}, 0)` : zs_discount_pct,
        zs_calculated: zs_discount_pct,
        highlight: false,
        bold: false
      },
      {
        name: "Commission %",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.commission_pct) : "",
        s_val: hasS ? fmtPct(s.commission_pct) : "",
        zs_val: useFormulas ? `=IFERROR(${zsCol}${rComm}/${zsCol}${rSales}, 0)` : zs_commission_pct,
        zs_calculated: zs_commission_pct,
        highlight: false,
        bold: false
      },
      {
        name: "Ads %",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.ads_pct) : "",
        s_val: hasS ? fmtPct(s.ads_pct) : "",
        zs_val: useFormulas ? `=IFERROR(${zsCol}${rAds}/${zsCol}${rSubtotal}, 0)` : zs_ads_pct,
        zs_calculated: zs_ads_pct,
        highlight: false,
        bold: false
      },
      {
        name: "Payout %",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.payout_pct) : "",
        s_val: hasS ? fmtPct(s.payout_pct) : "",
        zs_val: useFormulas ? `=IFERROR(${zsCol}${rCib}/${zsCol}${rSubtotal}, 0)` : zs_payout_pct,
        zs_calculated: zs_payout_pct,
        highlight: true,
        bold: true
      },
      {
        name: "Visibility",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.visibility) : "",
        s_val: hasS ? fmtPct(s.visibility) : "",
        zs_val: useFormulas ? `=IFERROR(AVERAGE(${zCol}${rVis}, ${sCol}${rVis}), 0)` : zs_visibility,
        zs_calculated: zs_visibility,
        highlight: false,
        bold: false
      },
      {
        name: "KPT",
        formatType: "kpt",
        z_val: hasZ ? fmtInt(z.kpt) : "",
        s_val: hasS ? fmtInt(s.kpt) : "",
        zs_val: useFormulas ? `=IFERROR(AVERAGE(${zCol}${rKpt}, ${sCol}${rKpt}), 0)` : fmtInt(zs_kpt),
        zs_calculated: fmtInt(zs_kpt),
        highlight: false,
        bold: false
      },
      {
        name: "Impressions",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.impressions) : "",
        s_val: hasS ? fmtInt(s.impressions) : "",
        zs_val: useFormulas ? `=${zCol}${rImp}+${sCol}${rImp}` : fmtInt(zs_impressions),
        zs_calculated: fmtInt(zs_impressions),
        highlight: false,
        bold: false
      },
      {
        name: "I2M",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.i2m) : "",
        s_val: hasS ? fmtPct(s.i2m) : "",
        zs_val: useFormulas ? `=IFERROR(AVERAGE(${zCol}${rI2m}, ${sCol}${rI2m}), 0)` : zs_i2m,
        zs_calculated: zs_i2m,
        highlight: false,
        bold: false
      },
      {
        name: "Menu Opens",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.menu_opens) : "",
        s_val: hasS ? fmtInt(s.menu_opens) : "",
        zs_val: useFormulas ? `=${zCol}${rMenu}+${sCol}${rMenu}` : fmtInt(zs_menu_opens),
        zs_calculated: fmtInt(zs_menu_opens),
        highlight: false,
        bold: false
      },
      {
        name: "C2O",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.c2o) : "",
        s_val: hasS ? fmtPct(s.c2o) : "",
        zs_val: useFormulas ? `=IFERROR(AVERAGE(${zCol}${rC2o}, ${sCol}${rC2o}), 0)` : zs_c2o,
        zs_calculated: zs_c2o,
        highlight: false,
        bold: false
      },
      {
        name: "M2O",
        formatType: "pct",
        z_val: hasZ ? fmtPct(z.m2o) : "",
        s_val: hasS ? fmtPct(s.m2o) : "",
        zs_val: useFormulas ? `=IFERROR(AVERAGE(${zCol}${rM2o}, ${sCol}${rM2o}), 0)` : zs_m2o,
        zs_calculated: zs_m2o,
        highlight: false,
        bold: true
      },
      {
        name: "Mx Rejections",
        formatType: "int",
        z_val: hasZ ? fmtInt(z.mx_rejections) : "",
        s_val: hasS ? fmtInt(s.mx_rejections) : "",
        zs_val: useFormulas ? `=${zCol}${rMx}+${sCol}${rMx}` : fmtInt(zs_mx_rejections),
        zs_calculated: fmtInt(zs_mx_rejections),
        highlight: false,
        bold: false
      }
    ];
  }
}
