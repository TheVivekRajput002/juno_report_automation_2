// In-Page Zomato Extraction Engine: 1:1 Complete Port of Python Scraper

/**
 * Self-contained in-page extractor for Zomato Business Reports tab.
 */
export async function inPageExtractReporting(startISO, endISO, dateLabel, targetId, targetName) {
  const logs = [];
  function logMsg(m) {
    logs.push(m);
    console.log(`[ReportingScraper] ${m}`);
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));

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

  function closeModals() {
    const closeBtns = Array.from(document.querySelectorAll('[aria-label="close"], [aria-label="Close"], button[class*="close"], [class*="close-icon"], svg[class*="close"]'));
    for (const b of closeBtns) {
      try { b.click(); } catch(e) {}
    }
  }

  async function selectOutletInReporting(resId, resName) {
    const tId = (resId || "").trim().toLowerCase();
    const tName = (resName || "").trim().toLowerCase();
    if (!tId && !tName) return;

    logMsg(`Checking outlet in Reporting modal for "${tId || tName}"...`);

    // Check if #modal is already open
    let modal = document.querySelector('#modal, div.sc-fBuWsC');
    if (!modal) {
      // Find outlet trigger button
      const triggers = Array.from(document.querySelectorAll('span, button, div, a')).filter(el => {
        const txt = (el.innerText || "").trim().toLowerCase();
        return (txt === 'all outlets' || txt.includes('outlets') || txt.includes('show data for') || txt.includes('change outlet') || txt.startsWith('id:')) && el.children.length < 5;
      });

      if (triggers.length > 0) {
        const btnText = (triggers[0].innerText || "").trim();
        if ((btnText.toLowerCase().includes(tId) || btnText.toLowerCase().includes(tName)) && !btnText.toLowerCase().includes('all outlet')) {
          logMsg(`Outlet "${btnText}" is already active in Reporting.`);
          return;
        }
        triggers[0].click();
        await sleep(1500);
      }
    }

    modal = document.querySelector('#modal, div.sc-fBuWsC');
    if (modal) {
      logMsg("Opening 'Outlet' tab in filter modal...");
      // Click 'Outlet' tab
      const tabs = Array.from(modal.querySelectorAll('span, div')).filter(el => (el.innerText || "").trim() === 'Outlet' && el.children.length === 0);
      if (tabs.length > 0) {
        tabs[0].click();
        await sleep(600);
      }

      // Clear filters
      const clearBtns = Array.from(modal.querySelectorAll('button, span, a, div[role="button"]')).filter(b => {
        const t = (b.innerText || "").trim().toLowerCase();
        return t === 'clear all' || t === 'clear filters' || t === 'deselect all';
      });
      if (clearBtns.length > 0) {
        clearBtns[0].click();
        await sleep(400);
      }

      // Type in search box
      const searchInput = modal.querySelector('input[placeholder*="Search"], input[type="text"]');
      if (searchInput) {
        searchInput.focus();
        searchInput.value = tId || tName;
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
        await sleep(1000);
      }

      // Click matching item
      const items = Array.from(modal.querySelectorAll('[class*="css-1mwie36"], [class*="css-gj25qc"], [data-test-id="virtuoso-item-list"] > div, label, div[class*="row"]'));
      for (const it of items) {
        const txt = (it.innerText || "").toLowerCase();
        if ((txt.includes(tId) || txt.includes(tName)) && !txt.includes('clear all') && !txt.includes('apply')) {
          it.click();
          logMsg(`Selected outlet: "${it.innerText.trim()}"`);
          await sleep(800);
          break;
        }
      }

      // Click Apply
      const applyBtns = Array.from(modal.querySelectorAll('button, div[role="button"], span')).filter(b => (b.innerText || "").trim().toLowerCase() === 'apply');
      if (applyBtns.length > 0) {
        applyBtns[0].click();
        logMsg("Clicked 'Apply' in filter modal.");
        await sleep(3500);
      }
    }
  }

  try {
    closeModals();
    await sleep(400);

    // 1. Ensure 'Business reports' tab is active
    const bizTabs = Array.from(document.querySelectorAll('span, button, div[role="tab"], a')).filter(el => (el.innerText || "").trim() === 'Business reports');
    if (bizTabs.length > 0) {
      bizTabs[0].click();
      logMsg("Clicked 'Business reports' tab.");
      await sleep(2500);
    }

    // 2. Select Outlet
    if (targetId || targetName) {
      await selectOutletInReporting(targetId, targetName);
    }

    // 3. Ensure 'Weekly' Granularity View
    const bodyTxt = document.body ? document.body.innerText.toLowerCase() : "";
    const isWeekly = bodyTxt.includes("week") && (bodyTxt.includes("week 1") || bodyTxt.includes("week 2") || bodyTxt.includes("week 3") || bodyTxt.includes("week 35") || bodyTxt.includes("week 36") || bodyTxt.includes("week 37"));
    if (!isWeekly) {
      const weeklyBtns = Array.from(document.querySelectorAll('button, div, span, a, label, [role="tab"]')).filter(el => (el.innerText || "").trim().toLowerCase() === 'weekly');
      if (weeklyBtns.length > 0) {
        weeklyBtns[0].click();
        logMsg("Clicked 'Weekly' granularity view toggle.");
        await sleep(3000);
      }
    }

    // 4. Wait for table rows to render (poll up to 12s)
    let foundRows = 0;
    for (let attempt = 0; attempt < 12; attempt++) {
      const rows = document.querySelectorAll('table tbody tr, table tr, [role="table"] [role="row"], [role="grid"] [role="row"]');
      if (rows && rows.length >= 3) {
        foundRows = rows.length;
        break;
      }
      await sleep(1000);
    }
    logMsg(`Rendered table with ${foundRows} rows.`);

    // 5. Expand Accordions (Menu to order -> Cart to order)
    const isCartVisible = (document.body ? document.body.innerText.toLowerCase() : "").includes("cart to order");
    if (!isCartVisible) {
      const trs = Array.from(document.querySelectorAll('tr, [role="row"], div'));
      for (const r of trs) {
        const txt = (r.innerText || "").toLowerCase().trim();
        if (txt.includes("menu to order") && !txt.includes("cart to order")) {
          const chevron = r.querySelector('svg, button, [role="button"], i, [class*="chevron"], [class*="arrow"]') || r;
          chevron.click();
          logMsg("Expanded 'Menu to order' chevron accordion.");
          await sleep(1500);
          break;
        }
      }
    }

    // 6. Scroll Horizontally
    const scrollables = Array.from(document.querySelectorAll('*')).filter(el => el.scrollWidth > el.clientWidth && el.clientWidth > 250);
    for (const s of scrollables) {
      s.scrollLeft = 0;
    }
    await sleep(800);

    // 7. Extract Table Headers & Rows
    const tableData = { headers: [], rows: [], rawText: document.body ? document.body.innerText : "" };
    const tables = document.querySelectorAll('table, [role="table"], [role="grid"]');
    for (const t of tables) {
      let ths = [];
      const theadRow = t.querySelector('thead tr, tr:first-child');
      if (theadRow) {
        ths = Array.from(theadRow.querySelectorAll('th, td, [role="columnheader"]')).map(el => (el.innerText || "").trim().replace(/\s+/g, " "));
      }
      if (ths.length === 0) {
        ths = Array.from(t.querySelectorAll('th, [role="columnheader"]')).map(el => (el.innerText || "").trim().replace(/\s+/g, " "));
      }
      if (ths.length > tableData.headers.length) {
        tableData.headers = ths;
      }

      const trs = Array.from(t.querySelectorAll('tbody tr, tr[role="row"]'));
      for (const row of trs) {
        const cellElements = Array.from(row.querySelectorAll('td, th, [role="cell"], [role="columnheader"]'));
        const cells = cellElements.map(el => (el.innerText || "").trim());
        if (cells.length > 1 && cells[0]) {
          tableData.rows.push({ metricName: cells[0], cells });
        }
      }
    }

    // If 0 table tags found, check virtualized div rows
    if (tableData.rows.length === 0) {
      const potentialRows = Array.from(document.querySelectorAll('div[class*="row"], div[class*="Row"], div[class*="grid"], div[role="row"]'));
      for (const r of potentialRows) {
        const cells = Array.from(r.children).map(c => (c.innerText || "").trim()).filter(Boolean);
        if (cells.length >= 3) {
          if (cells.some(c => c.toLowerCase().includes("week") || /\d+\s*-\s*\d+\s*[A-Za-z]+/.test(c))) {
            if (cells.length > tableData.headers.length) tableData.headers = cells;
          } else if (cells[0] && cells[0].length < 40 && !cells[0].includes("\n")) {
            tableData.rows.push({ metricName: cells[0], cells });
          }
        }
      }
    }

    logMsg(`Discovered ${tableData.headers.length} columns: ${JSON.stringify(tableData.headers)}`);

    // 8. Resolve Target Column Index
    const headers = tableData.headers;
    let targetColIdx = 1;

    const sDate = new Date(startISO + "T00:00:00");
    const eDate = new Date(endISO + "T00:00:00");
    const sDay = String(sDate.getDate());
    const eDay = String(eDate.getDate());
    const months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
    const sMonth = months[sDate.getMonth()];
    const eMonth = months[eDate.getMonth()];

    // ISO week number calculation
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
        targetColIdx = idx;
        break;
      }
    }

    // Priority 2: Match by exact date range
    if (targetColIdx === 1) {
      for (let idx = 0; idx < headers.length; idx++) {
        const h = headers[idx].toLowerCase();
        if (h.includes("vs") || h.includes("trend") || h.includes("comparison")) continue;
        if (sMonth !== eMonth) {
          if (new RegExp(`\\b0?${sDay}\\s*${sMonth}\\s*-\\s*0?${eDay}\\s*${eMonth}\\b`, "i").test(h) ||
              new RegExp(`\\b0?${sDay}\\s*-\\s*0?${eDay}\\s*${eMonth}\\b`, "i").test(h)) {
            targetColIdx = idx;
            break;
          }
        } else {
          if (new RegExp(`\\b0?${sDay}\\s*(?:${sMonth})?\\s*-\\s*0?${eDay}\\s*${sMonth}\\b`, "i").test(h)) {
            targetColIdx = idx;
            break;
          }
        }
      }
    }

    // Priority 3: Fallback to last or second-to-last column
    if (targetColIdx === 1 && headers.length > 2) {
      targetColIdx = headers.length - 2;
    }

    logMsg(`Target column index resolved to: ${targetColIdx} (${headers[targetColIdx] || 'Default'})`);

    // 9. Extract Metrics from Rows
    const extracted = {};
    for (const row of tableData.rows) {
      const metricName = (row.metricName || "").trim().toLowerCase();
      const cells = row.cells || [];
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

    // Fallback: Text Matrix Parser if structured rows were empty
    if (!extracted.orders || !extracted.sales) {
      logMsg("Running text matrix fallback parser...");
      const lines = tableData.rawText.split("\n").map(l => l.trim()).filter(Boolean);

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
        if ((l.includes("delivered orders") || l === "orders") && !extracted.orders) {
          const val = extractCleanSequence(i, false);
          if (val !== null && val > 0) {
            extracted.orders = val;
            extracted.reporting_orders = val;
          }
        } else if (l === "sales" && !extracted.sales) {
          const val = extractCleanSequence(i, false);
          if (val !== null && val > 0) {
            extracted.sales = val;
            extracted.reporting_sales = val;
          }
        } else if ((l.includes("average order value") || l === "aov") && !extracted.net_order_value) {
          const val = extractCleanSequence(i, false);
          if (val !== null && val > 0) extracted.net_order_value = val;
        } else if ((l.includes("online %") || l.includes("visibility")) && !extracted.visibility) {
          const val = extractCleanSequence(i, true);
          if (val !== null && val >= 0) extracted.visibility = val;
        } else if ((l.includes("kitchen preparation") || l.includes("kitchen prep") || l === "kpt") && !extracted.kpt) {
          const val = extractCleanSequence(i, false);
          if (val !== null && val > 0) extracted.kpt = val;
        } else if (l === "impressions" && !extracted.impressions) {
          const val = extractCleanSequence(i, false);
          if (val !== null && val > 0) extracted.impressions = val;
        } else if ((l.includes("impressions to menu") || l === "i2m") && !extracted.i2m) {
          const val = extractCleanSequence(i, true);
          if (val !== null && val >= 0) extracted.i2m = val;
        } else if ((l.includes("menu to order") || l === "m2o") && !extracted.m2o) {
          const val = extractCleanSequence(i, true);
          if (val !== null && val >= 0) extracted.m2o = val;
        } else if ((l.includes("cart to order") || l === "c2o") && !extracted.c2o) {
          const val = extractCleanSequence(i, true);
          if (val !== null && val >= 0) extracted.c2o = val;
        } else if (l.includes("rejection") && !extracted.mx_rejections) {
          const val = extractCleanSequence(i, false);
          if (val !== null) extracted.mx_rejections = val;
        }
      }
    }

    if (!extracted.c2o) {
      const mC2o = tableData.rawText.match(/(?:Cart to order|Menu to cart|Cart conversion|C2O)\s*[:\n\r]*\s*([\d,]+(?:\.\d+)?)\s*%/i);
      if (mC2o) extracted.c2o = cleanNumber(mC2o[1]);
    }

    logMsg(`Reporting extraction successful: ${JSON.stringify(extracted)}`);
    return { success: true, data: extracted, logs };

  } catch (err) {
    logMsg(`ERROR in Reporting extraction: ${err.message}`);
    return { success: false, error: err.message, logs };
  }
}

/**
 * Self-contained in-page extractor for Zomato Payouts / Finance tab.
 */
export async function inPageExtractPayouts(startISO, endISO, dateLabel, targetId, targetName) {
  const logs = [];
  function logMsg(m) {
    logs.push(m);
    console.log(`[PayoutsScraper] ${m}`);
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));

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

  function closeModals() {
    const closeBtns = Array.from(document.querySelectorAll('[aria-label="close"], [aria-label="Close"], button[class*="close"], [class*="close-icon"], svg[class*="close"]'));
    for (const b of closeBtns) {
      try { b.click(); } catch(e) {}
    }
  }

  async function selectOutletInPayouts(resId, resName) {
    const tId = (resId || "").trim().toLowerCase();
    const tName = (resName || "").trim().toLowerCase();
    if (!tId && !tName) return;

    logMsg(`Checking outlet in Payouts dialog for "${tId || tName}"...`);
    let payoutDialog = document.querySelector('div[role="dialog"], div[class*="max-h-[720px]"]');

    if (!payoutDialog) {
      const triggers = Array.from(document.querySelectorAll('span, button, div')).filter(el => {
        const txt = (el.innerText || "").trim().toLowerCase();
        return (txt === 'show data for' || txt.includes('outlets') || txt.includes('change outlet')) && el.children.length < 5;
      });
      if (triggers.length > 0) {
        triggers[0].click();
        await sleep(1500);
      }
    }

    payoutDialog = document.querySelector('div[role="dialog"], div[class*="max-h-[720px]"]');
    if (payoutDialog) {
      // Click 'Restaurant' tab
      const resTabs = Array.from(payoutDialog.querySelectorAll('span, div, button, [role="tab"]')).filter(el => (el.innerText || "").trim() === 'Restaurant');
      if (resTabs.length > 0) {
        resTabs[0].click();
        await sleep(500);
      }

      // Search box
      const searchInput = payoutDialog.querySelector('input[placeholder*="Search"], input[type="text"], input');
      if (searchInput) {
        searchInput.focus();
        searchInput.value = tId || tName;
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
        searchInput.dispatchEvent(new Event('change', { bubbles: true }));
        await sleep(1000);
      }

      // Click radio label
      const labels = Array.from(payoutDialog.querySelectorAll('label, input[type="radio"], div.border-b, div[class*="item"], div[class*="card"]'));
      for (const l of labels) {
        const txt = (l.innerText || '' + l.id || '').toLowerCase();
        if (txt.includes(tId) || txt.includes(tName) || (tId && l.getAttribute('for') === tId) || (tId && l.id === tId)) {
          l.click();
          logMsg(`Clicked Payouts outlet radio option: "${l.innerText ? l.innerText.trim() : tId}"`);
          await sleep(800);
          break;
        }
      }

      // Click Apply
      const applyBtns = Array.from(payoutDialog.querySelectorAll('button, div[role="button"]')).filter(b => (b.innerText || "").trim().toLowerCase() === 'apply');
      if (applyBtns.length > 0) {
        applyBtns[0].click();
        logMsg("Clicked 'Apply' in Payouts outlet dialog.");
        await sleep(3500);
      }
    }
  }

  try {
    closeModals();
    await sleep(400);

    // 1. Outlet Selection
    if (targetId || targetName) {
      await selectOutletInPayouts(targetId, targetName);
    }

    // 2. Select Payout Cycle Row in Past cycles
    const sDate = new Date(startISO + "T00:00:00");
    const eDate = new Date(endISO + "T00:00:00");
    const sDay = String(sDate.getDate());
    const eDay = String(eDate.getDate());
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const sMonth = months[sDate.getMonth()].toLowerCase();
    const eMonth = months[eDate.getMonth()].toLowerCase();

    logMsg(`Locating payout cycle for: ${sDay} ${sMonth} - ${eDay} ${eMonth}...`);

    let clickedRow = false;
    // Look specifically inside tables or list items under Past cycles
    const tableRows = Array.from(document.querySelectorAll("table tbody tr, tr[role='row'], div[class*='table'] div[class*='row'], div[class*='PastCycles'] div[class*='item'], div[class*='card']"));
    for (const r of tableRows) {
      const txt = (r.innerText || "").toLowerCase();
      // Ensure it's not a giant container
      if (txt.length > 300) continue;

      const hasMonth = txt.includes(sMonth) || txt.includes(eMonth);
      const hasStart = txt.includes(sDay) || (new RegExp(`\\b0?${sDay}\\b`)).test(txt);
      const hasEnd = txt.includes(eDay) || (new RegExp(`\\b0?${eDay}\\b`)).test(txt);

      if (hasMonth && hasStart && hasEnd) {
        r.click();
        clickedRow = true;
        logMsg(`Clicked matching payout cycle row: "${txt.substring(0, 45).replace(/\n/g, ' ')}..."`);
        await sleep(3500);
        break;
      }
    }

    if (!clickedRow) {
      const firstRow = document.querySelector("table tbody tr, div[class*='table-body'] div[class*='row']");
      if (firstRow) {
        firstRow.click();
        logMsg("Clicked first available row in Past cycles table as fallback.");
        await sleep(3000);
      }
    }

    // 3. Expand Drawer Accordions
    const drawer = document.querySelector("[class*='drawer'], [class*='modal'], [class*='sheet'], [class*='sidebar'], [role='dialog'], [class*='details']") || document.body;
    const ariaClosed = Array.from(drawer.querySelectorAll("[aria-expanded='false']"));
    for (const el of ariaClosed) {
      try { el.click(); } catch(e) {}
    }

    const drawerText = drawer ? drawer.innerText : "";
    if (!drawerText.toLowerCase().includes("item subtotal")) {
      const sections = Array.from(drawer.querySelectorAll("div, button, span, p")).filter(el => {
        const t = (el.innerText || "").trim();
        return (t.startsWith("Net order value") || t.startsWith("Tax deductions") || t.startsWith("Order level") || t.startsWith("Additions") || t.startsWith("Investments")) && el.children.length < 4;
      });
      for (const s of sections) {
        try { s.click(); } catch(e) {}
      }
      await sleep(1500);
    }

    // 4. Parse Payout Text
    const data = {};
    const fullDrawerText = drawer ? drawer.innerText : "";
    const combinedText = `${fullDrawerText}\n${document.body ? document.body.innerText : ""}`;
    const lines = combinedText.split("\n").map(l => l.trim()).filter(Boolean);

    // Restaurant Name
    const mRes = fullDrawerText.match(/>\s*([A-Za-z0-9\s]+?)(?:\.\.\.|\n|$)/);
    if (mRes) data.restaurant_name = mRes[1].trim();

    // Delivered Orders
    const mOrders = combinedText.match(/(?:Delivered orders|Total orders|Orders delivered)\s*[:\n\r]*\s*([\d,]+)/i);
    if (mOrders) data.payout_delivered_orders = cleanNumber(mOrders[1]);

    // Net Order Value (A)
    const mNov = combinedText.match(/Net order value\s*(?:\(A\))?[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mNov) {
      data.net_order_value_amount = cleanNumber(mNov[1]);
      data.sales_after_discount = cleanNumber(mNov[1]);
    }

    // Item Subtotal (Gross Sales)
    const mSubtotal = combinedText.match(/(?:Item\s*Subtotal|Item\s*Total|Gross\s*Sales)[^\d\n\r]{0,30}₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mSubtotal) {
      data.subtotal = cleanNumber(mSubtotal[1]);
      data.item_subtotal = cleanNumber(mSubtotal[1]);
    }

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
            if (["gst", "subtotal", "net order", "additions", "packaging", "order level"].some(k => nextL.toLowerCase().includes(k))) break;
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

    data.discount_promos = discPromos;
    data.discount_flat_offs = discFlatOffs;
    data.discount_delivery = discDelivery;
    data.total_discount = Number((discPromos + discFlatOffs + discDelivery).toFixed(2));

    // Packaging Charges
    const mPack = combinedText.match(/(?:Packaging Charges?|Packaging Fee)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    data.packaging_charges = mPack ? cleanNumber(mPack[1]) : 0.0;

    // Additions (B)
    const mAdd = combinedText.match(/Additions\s*(?:\(B\))?\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mAdd) data.additions = cleanNumber(mAdd[1]);

    // Order Level Deductions (C)
    const mOrderDed = combinedText.match(/Order level deductions?\s*(?:\(C\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mOrderDed) data.order_level_deductions = cleanNumber(mOrderDed[1]);

    // GST 18%
    const mGst18 = combinedText.match(/GST on service and payment mechanism fees\s*@\s*18%\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mGst18) data.gst_fee_18 = cleanNumber(mGst18[1]);

    const mTaxDed = combinedText.match(/Tax deductions?\s*(?:\(D\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mTaxDed) data.tax_deductions = cleanNumber(mTaxDed[1]);

    const orderDed = data.order_level_deductions || 0.0;
    const gstFee = data.gst_fee_18 || data.tax_deductions || 0.0;
    if (orderDed || gstFee) {
      data.commission = Number((orderDed + gstFee).toFixed(2));
    }

    // Ads: Investments in Growth (E)
    const mAds = combinedText.match(/Investments? in growth\s*(?:\(E\))?\s*[:\n\r]*\s*[-–—]?\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mAds) data.ads = cleanNumber(mAds[1]);

    // Cash in Bank: Est Payout
    const mPayout = combinedText.match(/(?:Est\.?\s*payout|Estimated payout|Net payout|Amount Settled)\s*[:\n\r]*\s*₹?\s*([\d,]+(?:\.\d+)?)/i);
    if (mPayout) {
      data.est_payout = cleanNumber(mPayout[1]);
      data.cash_in_bank = cleanNumber(mPayout[1]);
    }

    // Rejections
    const mRej = combinedText.match(/(?:Rejected orders|Rejections|Mx Rejections)\s*[:\n\r]*\s*([\d,]+)/i);
    if (mRej) data.mx_rejections = cleanNumber(mRej[1]);

    // Close drawer after extraction
    closeModals();

    logMsg(`Payouts extraction successful: ${JSON.stringify(data)}`);
    return { success: true, data, logs };

  } catch (err) {
    logMsg(`ERROR in Payouts extraction: ${err.message}`);
    return { success: false, error: err.message, logs };
  }
}
