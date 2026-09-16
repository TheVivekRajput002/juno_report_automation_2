// Background Service Worker: Coordinates Zomato Extraction & Google Sheets Synchronization

import { CONFIG } from "../config.js";
import { MetricCalculator } from "../lib/metric_calculator.js";
import { GoogleSheetsClient } from "../lib/google_sheets_client.js";
import { inPageExtractReporting, inPageExtractPayouts } from "../lib/zomato_runner.js";

const state = {
  isRunning: false,
  status: "Ready",
  currentStep: 0,
  totalSteps: 0,
  sheetUrl: null,
  logs: [],
  error: null
};

function log(text, type = "info") {
  const timestamp = new Date().toLocaleTimeString();
  const entry = { text: `[${timestamp}] ${text}`, type };
  state.logs.push(entry);
  if (state.logs.length > 300) state.logs.shift();

  // Broadcast log to popup
  chrome.runtime.sendMessage({ action: "LOG_UPDATE", log: entry, state }).catch(() => {});
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function getOrCreateTab(url) {
  const tabs = await chrome.tabs.query({ url: "https://www.zomato.com/*" });
  if (tabs.length > 0) {
    const tab = tabs[0];
    await chrome.tabs.update(tab.id, { url, active: true });
    return tab;
  }
  return await chrome.tabs.create({ url, active: true });
}

async function waitForTabComplete(tabId, timeoutMs = 25000) {
  const start = Date.now();
  return new Promise((resolve) => {
    function listener(updatedTabId, info) {
      if (updatedTabId === tabId && info.status === "complete") {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve(true);
      }
    }
    chrome.tabs.onUpdated.addListener(listener);

    const checkInterval = setInterval(async () => {
      try {
        const t = await chrome.tabs.get(tabId);
        if (t.status === "complete" || Date.now() - start > timeoutMs) {
          clearInterval(checkInterval);
          chrome.tabs.onUpdated.removeListener(listener);
          resolve(true);
        }
      } catch (e) {
        clearInterval(checkInterval);
        resolve(true);
      }
    }, 800);
  });
}

async function runAutomationJob(req) {
  if (state.isRunning) {
    throw new Error("An automation job is already running.");
  }

  state.isRunning = true;
  state.status = "Running";
  state.error = null;
  state.sheetUrl = null;
  state.logs = [];

  const outletName = (req.outletName || "Restaurant").trim();
  const zomatoId = (req.zomatoId || "").trim();
  const worksheetName = (req.worksheetName || CONFIG.DEFAULT_WORKSHEET_NAME).trim();
  const ranges = req.ranges || [];

  state.totalSteps = ranges.length;
  state.currentStep = 0;

  log(`🚀 Starting Zomato Report Automation for "${outletName}" (ID: ${zomatoId || "Default"})`, "info");
  log(`Destination Google Sheet Tab: "${worksheetName}" | Total Reports: ${ranges.length}`, "info");

  const sheetsClient = new GoogleSheetsClient();

  try {
    const tab = await getOrCreateTab(CONFIG.ZOMATO.REPORTING_URL);
    const tabId = tab.id;

    let completedReports = 0;
    let lastSheetUrl = null;

    for (let i = 0; i < ranges.length; i++) {
      const range = ranges[i];
      state.currentStep = i + 1;
      log(`\n============================================================`, "info");
      log(`[Step ${i + 1}/${ranges.length}] Processing Date Range: ${range.label}`, "info");
      log(`============================================================`, "info");

      // -------------------------------------------------------------
      // STEP 1: BUSINESS REPORTS EXTRACTION
      // -------------------------------------------------------------
      log(`Navigating to Zomato Business Reports: ${CONFIG.ZOMATO.REPORTING_URL}`, "info");
      await chrome.tabs.update(tabId, { url: CONFIG.ZOMATO.REPORTING_URL });
      await waitForTabComplete(tabId);
      await sleep(3500);

      log(`Executing Business Reports extraction for ${range.label}...`, "info");
      const repExecResults = await chrome.scripting.executeScript({
        target: { tabId },
        func: inPageExtractReporting,
        args: [range.startISO, range.endISO, range.label, zomatoId, outletName]
      });

      const repResult = (repExecResults && repExecResults[0] && repExecResults[0].result) ? repExecResults[0].result : null;
      if (repResult && repResult.logs) {
        repResult.logs.forEach(l => log(l, "info"));
      }

      if (!repResult || !repResult.success) {
        log(`[!] Reporting extraction notice: ${repResult ? repResult.error : "No script result returned"}`, "warn");
      }
      const reportingData = (repResult && repResult.data) ? repResult.data : {};
      log(`[✓] Reporting Extracted: Orders=${reportingData.orders || 0}, Sales=₹${reportingData.sales || 0}, Impressions=${reportingData.impressions || 0}, I2M=${reportingData.i2m || 0}%, C2O=${reportingData.c2o || 0}%`, "success");

      // -------------------------------------------------------------
      // STEP 2: FINANCE / PAYOUTS EXTRACTION
      // -------------------------------------------------------------
      log(`Navigating to Zomato Finance Payouts: ${CONFIG.ZOMATO.PAYOUTS_URL}`, "info");
      await chrome.tabs.update(tabId, { url: CONFIG.ZOMATO.PAYOUTS_URL });
      await waitForTabComplete(tabId);
      await sleep(3500);

      log(`Locating weekly payout cycle and expanding side-drawer for ${range.label}...`, "info");
      const payExecResults = await chrome.scripting.executeScript({
        target: { tabId },
        func: inPageExtractPayouts,
        args: [range.startISO, range.endISO, range.label, zomatoId, outletName]
      });

      const payResult = (payExecResults && payExecResults[0] && payExecResults[0].result) ? payExecResults[0].result : null;
      if (payResult && payResult.logs) {
        payResult.logs.forEach(l => log(l, "info"));
      }

      if (!payResult || !payResult.success) {
        log(`[!] Payouts extraction notice: ${payResult ? payResult.error : "No script result returned"}`, "warn");
      }
      const payoutData = (payResult && payResult.data) ? payResult.data : {};
      log(`[✓] Payout Extracted: Subtotal=₹${payoutData.subtotal || 0}, Total Discount=₹${payoutData.total_discount || 0}, Commission=₹${payoutData.commission || 0}, Cash in Bank=₹${payoutData.cash_in_bank || 0}`, "success");

      // -------------------------------------------------------------
      // STEP 3: COMBINE & NORMALIZE METRICS
      // -------------------------------------------------------------
      const combinedRaw = Object.assign({}, reportingData, payoutData);
      const calculatedZomato = MetricCalculator.calculateZomatoMetrics(combinedRaw);

      log(`[✓] Reconciled Metrics: Net Sales=₹${calculatedZomato.sales_after_discount}, Orders=${calculatedZomato.orders}, NOV=₹${calculatedZomato.net_order_value}, Payout %= ${calculatedZomato.payout_pct.toFixed(2)}%`, "success");

      // -------------------------------------------------------------
      // STEP 4: WRITE FORMATTED TABLE TO GOOGLE SHEETS
      // -------------------------------------------------------------
      log(`Writing formatted table to Google Sheet tab "${worksheetName}"...`, "info");
      lastSheetUrl = await sheetsClient.generateReport({
        zomatoMetrics: calculatedZomato,
        swiggyMetrics: null,
        restaurantName: outletName,
        restaurantId: zomatoId || "N/A",
        dateRangeLabel: range.label,
        reportTitle: "Weekly Report",
        worksheetName: worksheetName
      });

      state.sheetUrl = lastSheetUrl;
      completedReports++;
      log(`[✓] Report for "${range.label}" synced successfully!`, "success");
    }

    state.status = "Completed";
    log(`\n============================================================`, "success");
    log(`🎉 ALL ${completedReports} REPORT(S) GENERATED & SYNCED TO GOOGLE SHEETS!`, "success");
    log(`🔗 Google Sheet: ${lastSheetUrl}`, "success");
    log(`============================================================`, "success");

    chrome.runtime.sendMessage({
      action: "JOB_DONE",
      sheetUrl: lastSheetUrl,
      completedReports
    }).catch(() => {});

  } catch (err) {
    state.status = "Error";
    state.error = err.message;
    log(`❌ Automation Error: ${err.message}`, "error");
    chrome.runtime.sendMessage({ action: "JOB_ERROR", error: err.message }).catch(() => {});
  } finally {
    state.isRunning = false;
  }
}

chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
  if (req.action === "START_AUTOMATION") {
    runAutomationJob(req).catch(err => {
      log(`Job failed to launch: ${err.message}`, "error");
    });
    sendResponse({ status: "started" });
    return true;
  }

  if (req.action === "GET_STATE") {
    sendResponse(state);
    return true;
  }
});
