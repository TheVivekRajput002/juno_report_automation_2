// Zomato Business Reports Scraper Content Script

(function() {
  if (window.__ZOMATO_REPORTING_SCRIPT_LOADED__) return;
  window.__ZOMATO_REPORTING_SCRIPT_LOADED__ = true;

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

  async function selectWeeklyView() {
    console.log("[*] Checking 'Weekly' view / granularity toggle...");
    const bodyTxt = document.body ? document.body.innerText.toLowerCase() : "";
    if (bodyTxt.includes("week") && (bodyTxt.includes("week 1") || bodyTxt.includes("week 2") || bodyTxt.includes("week 3") || bodyTxt.includes("week 4") || bodyTxt.includes("week 35") || bodyTxt.includes("week 36"))) {
      console.log("[+] Weekly view is already active.");
      return true;
    }

    const elements = Array.from(document.querySelectorAll("button, div, span, a, label, [role='tab']"));
    for (const el of elements) {
      if ((el.innerText || "").trim().toLowerCase() === "weekly") {
        el.click();
        console.log("[+] Clicked 'Weekly' button.");
        await sleep(2500);
        return true;
      }
    }
    return false;
  }

  async function expandAccordions() {
    console.log("[*] Expanding table accordions (e.g. Menu to order -> Cart to order)...");
    const bodyTxt = document.body ? document.body.innerText.toLowerCase() : "";
    if (bodyTxt.includes("cart to order") || bodyTxt.includes("menu to cart")) {
      console.log("[+] 'Cart to order' is already visible.");
      return;
    }

    const rows = Array.from(document.querySelectorAll("tr, [role='row'], div"));
    for (const r of rows) {
      const txt = (r.innerText || "").toLowerCase().trim();
      if (txt.includes("menu to order") && !txt.includes("cart to order")) {
        const btn = r.querySelector("svg, button, [role='button'], i, [class*='chevron'], [class*='arrow']") || r;
        btn.click();
        console.log("[+] Clicked 'Menu to order' chevron to expand Cart to order.");
        await sleep(1500);
        break;
      }
    }
  }

  function scrollToRevealColumns() {
    console.log("[*] Scrolling table horizontally to reveal earlier weekly columns...");
    const scrollables = Array.from(document.querySelectorAll("*")).filter(el => {
      return (el.scrollWidth > el.clientWidth) && (el.clientWidth > 250);
    });
    for (const s of scrollables) {
      s.scrollLeft = 0;
    }
  }

  function extractTableDOM() {
    const result = {
      headers: [],
      rows: [],
      rawText: document.body ? document.body.innerText : ""
    };

    const tables = document.querySelectorAll("table, [role='table'], [role='grid']");
    for (const t of tables) {
      let ths = [];
      const theadRow = t.querySelector("thead tr, tr:first-child");
      if (theadRow) {
        ths = Array.from(theadRow.querySelectorAll("th, td, [role='columnheader']")).map(el => (el.innerText || "").trim().replace(/\s+/g, " "));
      }
      if (ths.length === 0) {
        ths = Array.from(t.querySelectorAll("th, [role='columnheader']")).map(el => (el.innerText || "").trim().replace(/\s+/g, " "));
      }
      if (ths.length > result.headers.length) {
        result.headers = ths;
      }

      const trs = Array.from(t.querySelectorAll("tbody tr, tr[role='row']"));
      for (const row of trs) {
        const cellElements = Array.from(row.querySelectorAll("td, th, [role='cell'], [role='columnheader']"));
        const cells = cellElements.map(el => (el.innerText || "").trim());
        if (cells.length > 1 && cells[0]) {
          const headerMap = {};
          for (let c = 0; c < ths.length && c < cells.length; c++) {
            if (ths[c]) {
              headerMap[ths[c]] = cells[c];
            }
          }
          result.rows.push({
            metricName: cells[0],
            cells: cells,
            headerMap: headerMap
          });
        }
      }
    }

    if (result.rows.length === 0) {
      const potentialRows = Array.from(document.querySelectorAll("div[class*='row'], div[class*='Row'], div[class*='grid'], div[role='row']"));
      for (const r of potentialRows) {
        const cells = Array.from(r.children).map(c => (c.innerText || "").trim()).filter(Boolean);
        if (cells.length >= 3) {
          if (cells.some(c => c.toLowerCase().includes("week") || /\d+\s*-\s*\d+\s*[A-Za-z]+/.test(c))) {
            if (cells.length > result.headers.length) {
              result.headers = cells;
            }
          } else if (cells[0] && cells[0].length < 40 && !cells[0].includes("\n")) {
            result.rows.push({
              metricName: cells[0],
              cells: cells,
              headerMap: {}
            });
          }
        }
      }
    }

    return result;
  }

  function findTargetColumnIndex(headers, startISO, endISO, dateLabel) {
    if (!headers || headers.length <= 1) return 1;

    const sDate = new Date(startISO);
    const eDate = new Date(endISO);
    const sDay = String(sDate.getDate());
    const eDay = String(eDate.getDate());
    const months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
    const sMonth = months[sDate.getMonth()];
    const eMonth = months[eDate.getMonth()];

    // Calculate ISO Week Number
    const d = new Date(Date.UTC(sDate.getFullYear(), sDate.getMonth(), sDate.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const calWeek = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);

    // Priority 1: Match by ISO Week Number
    for (let idx = 0; idx < headers.length; idx++) {
      const h = headers[idx].toLowerCase();
      if (h.includes("vs") || h.includes("trend") || h.includes("comparison")) continue;
      if (new RegExp(`\\bweek\\s*${calWeek}\\b`, "i").test(h)) {
        return idx;
      }
    }

    // Priority 2: Exact date range matching
    for (let idx = 0; idx < headers.length; idx++) {
      const h = headers[idx].toLowerCase();
      if (h.includes("vs") || h.includes("trend") || h.includes("comparison")) continue;
      if (sMonth !== eMonth) {
        if (new RegExp(`\\b0?${sDay}\\s*${sMonth}\\s*-\\s*0?${eDay}\\s*${eMonth}\\b`, "i").test(h) ||
            new RegExp(`\\b0?${sDay}\\s*-\\s*0?${eDay}\\s*${eMonth}\\b`, "i").test(h)) {
          return idx;
        }
      } else {
        if (new RegExp(`\\b0?${sDay}\\s*(?:${sMonth})?\\s*-\\s*0?${eDay}\\s*${sMonth}\\b`, "i").test(h)) {
          return idx;
        }
      }
    }

    // Priority 3: dateLabel matching
    if (dateLabel) {
      const dClean = dateLabel.toLowerCase();
      for (let idx = 0; idx < headers.length; idx++) {
        const h = headers[idx].toLowerCase();
        if (h.includes(dClean)) return idx;
      }
    }

    // Priority 4: Column position offset
    const validIndices = [];
    for (let idx = 0; idx < headers.length; idx++) {
      const h = headers[idx].toLowerCase();
      if (h.includes("trend") || h.includes("metric") || h.includes("vs")) continue;
      if (h.includes("week") || months.some(m => h.includes(m))) {
        validIndices.push(idx);
      }
    }

    if (validIndices.length >= 2) {
      return validIndices[validIndices.length - 2];
    } else if (validIndices.length > 0) {
      return validIndices[validIndices.length - 1];
    }

    return headers.length - 1;
  }

  function extractMetricsFromRows(rows, targetColIdx) {
    const extracted = {};

    for (const rowData of rows) {
      const metricName = (rowData.metricName || "").trim().toLowerCase();
      const cells = rowData.cells || [];
      const cellVal = (targetColIdx < cells.length) ? cells[targetColIdx] : (cells[cells.length - 1] || "");

      if (metricName === "sales" || metricName === "total sales") {
        extracted.sales = cleanNumber(cellVal);
        extracted.reporting_sales = cleanNumber(cellVal);
        extracted.sales_after_discount = cleanNumber(cellVal);
      } else if (metricName.includes("delivered") || metricName === "orders" || metricName.includes("total orders")) {
        extracted.orders = cleanNumber(cellVal);
        extracted.reporting_orders = cleanNumber(cellVal);
        extracted.delivered_orders = cleanNumber(cellVal);
      } else if (metricName.includes("average order value") || metricName === "aov") {
        extracted.net_order_value = cleanNumber(cellVal);
        extracted.aov = cleanNumber(cellVal);
      } else if (metricName.includes("average rating") || metricName.includes("rating")) {
        extracted.avg_rating = cleanNumber(cellVal);
      } else if (metricName.includes("bad order")) {
        extracted.bad_orders = cleanNumber(cellVal);
      } else if (metricName.includes("complaint")) {
        extracted.total_complaints = cleanNumber(cellVal);
      } else if (metricName.includes("lost sales")) {
        extracted.lost_sales = cleanNumber(cellVal);
      } else if ((metricName.includes("online") && metricName.includes("%")) || metricName.includes("visibility")) {
        extracted.visibility = cleanNumber(cellVal);
      } else if (metricName.includes("kitchen") || metricName.includes("prep") || metricName.includes("kpt")) {
        extracted.kpt = cleanNumber(cellVal);
      } else if (metricName.includes("impression") && metricName.includes("menu")) {
        extracted.i2m = cleanNumber(cellVal);
      } else if (metricName.includes("impression") && !metricName.includes("menu")) {
        extracted.impressions = cleanNumber(cellVal);
      } else if (metricName.includes("menu") && metricName.includes("order")) {
        extracted.m2o = cleanNumber(cellVal);
      } else if (metricName.includes("cart to order") || metricName.includes("cart")) {
        extracted.c2o = cleanNumber(cellVal);
      } else if (metricName.includes("new user")) {
        extracted.new_users = cleanNumber(cellVal);
      } else if (metricName.includes("rejection") || metricName.includes("rejected")) {
        extracted.mx_rejections = cleanNumber(cellVal);
      }
    }

    return extracted;
  }

  function parseReportingTextMatrix(bodyText, targetColIdx, headers, startISO, endISO) {
    const metrics = {};
    const lines = bodyText.split("\n").map(l => l.trim()).filter(Boolean);

    function extractCleanSequence(lineIdx, isPct = false) {
      const rawTokens = [];
      for (let j = lineIdx + 1; j < Math.min(lineIdx + 40, lines.length); j++) {
        const valStr = lines[j];
        if (["sales overview", "customer experience", "funnel", "sales", "delivered orders", "orders", "average order value", "online %", "kitchen preparation", "impressions", "impressions to menu", "menu to order", "cart to order", "rejections"].some(k => valStr.toLowerCase() === k || valStr.toLowerCase().startsWith(k))) {
          break;
        }
        if (/^[-+▲▼]?\s*₹?\s*[\d,]+(?:\.\d+)?\s*(?:%|mins|min)?$/i.test(valStr)) {
          rawTokens.push(valStr);
        }
      }

      if (rawTokens.length === 0) return null;

      let firstIsTrend = false;
      const firstVal = rawTokens[0].trim();
      if (firstVal.startsWith("+") || firstVal.startsWith("▲") || firstVal.startsWith("▼") || (firstVal.startsWith("-") && isPct)) {
        firstIsTrend = true;
      }

      const pureValues = [];
      for (let idx = 0; idx < rawTokens.length; idx++) {
        if (idx === 0 && firstIsTrend) continue;
        const num = cleanNumber(rawTokens[idx]);
        if (isPct && num < 0) continue;
        pureValues.push(num);
      }

      if (pureValues.length === 0) return null;
      if (pureValues.length >= 2) return pureValues[pureValues.length - 2];
      return pureValues[pureValues.length - 1];
    }

    for (let i = 0; i < lines.length; i++) {
      const l = lines[i].toLowerCase();
      if ((l.includes("delivered orders") || l === "orders") && !metrics.orders) {
        const val = extractCleanSequence(i, false);
        if (val !== null && val > 0) {
          metrics.orders = val;
          metrics.reporting_orders = val;
          metrics.delivered_orders = val;
        }
      } else if (l === "sales" && !metrics.sales) {
        const val = extractCleanSequence(i, false);
        if (val !== null && val > 0) {
          metrics.sales = val;
          metrics.reporting_sales = val;
          metrics.sales_after_discount = val;
        }
      } else if ((l.includes("average order value") || l === "aov") && !metrics.net_order_value) {
        const val = extractCleanSequence(i, false);
        if (val !== null && val > 0) metrics.net_order_value = val;
      } else if ((l.includes("online %") || l.includes("visibility")) && !metrics.visibility) {
        const val = extractCleanSequence(i, true);
        if (val !== null && val >= 0) metrics.visibility = val;
      } else if ((l.includes("kitchen preparation") || l.includes("kitchen prep") || l === "kpt") && !metrics.kpt) {
        const val = extractCleanSequence(i, false);
        if (val !== null && val > 0) metrics.kpt = val;
      } else if (l === "impressions" && !metrics.impressions) {
        const val = extractCleanSequence(i, false);
        if (val !== null && val > 0) metrics.impressions = val;
      } else if ((l.includes("impressions to menu") || l === "i2m") && !metrics.i2m) {
        const val = extractCleanSequence(i, true);
        if (val !== null && val >= 0) metrics.i2m = val;
      } else if ((l.includes("menu to order") || l === "m2o") && !metrics.m2o) {
        const val = extractCleanSequence(i, true);
        if (val !== null && val >= 0) metrics.m2o = val;
      } else if ((l.includes("cart to order") || l === "c2o") && !metrics.c2o) {
        const val = extractCleanSequence(i, true);
        if (val !== null && val >= 0) metrics.c2o = val;
      } else if (l.includes("rejection") && !metrics.mx_rejections) {
        const val = extractCleanSequence(i, false);
        if (val !== null) metrics.mx_rejections = val;
      }
    }

    return metrics;
  }

  async function scrapeReporting(req) {
    console.log(`[*] Scraping Reporting tab for range: ${req.dateLabel} (${req.startISO} to ${req.endISO})...`);
    await selectWeeklyView();
    await sleep(2500);

    await expandAccordions();
    scrollToRevealColumns();
    await sleep(1500);

    const tableData = extractTableDOM();
    const headers = tableData.headers || [];
    const rows = tableData.rows || [];
    const rawText = tableData.rawText || "";

    const targetColIdx = findTargetColumnIndex(headers, req.startISO, req.endISO, req.dateLabel);
    console.log(`[*] Target Column Index: ${targetColIdx}, Headers:`, headers);

    let extracted = {};
    if (rows.length > 0) {
      extracted = extractMetricsFromRows(rows, targetColIdx);
    }

    const fallback = parseReportingTextMatrix(rawText, targetColIdx, headers, req.startISO, req.endISO);
    for (const [k, v] of Object.entries(fallback)) {
      if (!extracted[k] || extracted[k] === 0) {
        extracted[k] = v;
      }
    }

    // Cross check C2O regex from raw text if missing
    if (!extracted.c2o) {
      const mC2o = rawText.match(/(?:Cart to order|Menu to cart|Cart conversion|C2O)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%/i);
      if (mC2o) {
        extracted.c2o = cleanNumber(mC2o[1]);
      }
    }

    console.log("[✓] Extracted Reporting Metrics:", extracted);
    return { success: true, data: extracted };
  }

  chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    if (req.action === "SCRAPE_REPORTING") {
      scrapeReporting(req).then(res => sendResponse(res)).catch(err => sendResponse({ success: false, error: err.message }));
      return true;
    }
  });
})();
