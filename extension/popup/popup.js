// Popup Controller & UI State Handler

import { CONFIG } from "../config.js";
import { getWeeklyDateRanges, getCustomDates } from "../lib/date_utils.js";

document.addEventListener("DOMContentLoaded", async () => {
  // Elements
  const statusBadge = document.getElementById("statusBadge");
  const statusText = document.getElementById("statusText");
  const outletSelect = document.getElementById("outletSelect");
  const customOutletFields = document.getElementById("customOutletFields");
  const customName = document.getElementById("customName");
  const customZomatoId = document.getElementById("customZomatoId");
  const tabPreset = document.getElementById("tabPreset");
  const tabCustom = document.getElementById("tabCustom");
  const presetView = document.getElementById("presetView");
  const customView = document.getElementById("customView");
  const pillBtns = document.querySelectorAll(".pill-btn");
  const previewRanges = document.getElementById("previewRanges");
  const startDate = document.getElementById("startDate");
  const endDate = document.getElementById("endDate");
  const worksheetInput = document.getElementById("worksheetInput");
  const runBtn = document.getElementById("runBtn");
  const runBtnText = runBtn.querySelector(".btn-text");
  const spinner = runBtn.querySelector(".spinner");
  const sheetLinkBtn = document.getElementById("sheetLinkBtn");
  const progressSection = document.getElementById("progressSection");
  const progressLabel = document.getElementById("progressLabel");
  const progressCounter = document.getElementById("progressCounter");
  const progressBar = document.getElementById("progressBar");
  const consoleBody = document.getElementById("consoleBody");
  const clearLogBtn = document.getElementById("clearLogBtn");

  let currentWeeks = 1;
  let isCustomDateMode = false;
  let outlets = CONFIG.DEFAULT_OUTLETS;

  // 1. Initialize Outlets
  const stored = await chrome.storage.local.get(["saved_outlets", "selected_outlet_id"]);
  if (stored.saved_outlets && Array.isArray(stored.saved_outlets)) {
    outlets = stored.saved_outlets;
  }

  function renderOutletOptions() {
    outletSelect.innerHTML = "";
    outlets.forEach(o => {
      const opt = document.createElement("option");
      opt.value = o.id;
      opt.textContent = `${o.name} (ZID: ${o.zomato_id || "N/A"})`;
      outletSelect.appendChild(opt);
    });

    const customOpt = document.createElement("option");
    customOpt.value = "custom";
    customOpt.textContent = "➕ Enter Custom Outlet...";
    outletSelect.appendChild(customOpt);

    if (stored.selected_outlet_id) {
      outletSelect.value = stored.selected_outlet_id;
    }
  }

  renderOutletOptions();

  outletSelect.addEventListener("change", () => {
    if (outletSelect.value === "custom") {
      customOutletFields.classList.remove("hidden");
    } else {
      customOutletFields.classList.add("hidden");
      chrome.storage.local.set({ selected_outlet_id: outletSelect.value });
    }
  });

  // 2. Preset & Custom Tabs
  tabPreset.addEventListener("click", () => {
    isCustomDateMode = false;
    tabPreset.classList.add("active");
    tabCustom.classList.remove("active");
    presetView.classList.remove("hidden");
    customView.classList.add("hidden");
    updateRangePreview();
  });

  tabCustom.addEventListener("click", () => {
    isCustomDateMode = true;
    tabCustom.classList.add("active");
    tabPreset.classList.remove("active");
    customView.classList.remove("hidden");
    presetView.classList.add("hidden");

    // Default custom dates (past 7 days)
    if (!startDate.value || !endDate.value) {
      const today = new Date();
      const prior = new Date(today);
      prior.setDate(today.getDate() - 7);
      endDate.value = today.toISOString().split("T")[0];
      startDate.value = prior.toISOString().split("T")[0];
    }
  });

  // 3. Week Pill Buttons
  pillBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      pillBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentWeeks = parseInt(btn.dataset.weeks, 10) || 1;
      updateRangePreview();
    });
  });

  function updateRangePreview() {
    const ranges = getWeeklyDateRanges(currentWeeks);
    previewRanges.textContent = ranges.map((r, i) => `Week ${i + 1}: ${r.label}`).join("\n");
  }

  updateRangePreview();

  // 4. Logging & Status UI
  function addLogLine(text, type = "info") {
    const div = document.createElement("div");
    div.className = `log-line ${type}`;
    div.textContent = text;
    consoleBody.appendChild(div);
    consoleBody.scrollTop = consoleBody.scrollHeight;
  }

  clearLogBtn.addEventListener("click", () => {
    consoleBody.innerHTML = "";
  });

  function setStatus(status, label = null) {
    statusText.textContent = label || status;
    statusBadge.className = `status-badge ${status.toLowerCase()}`;

    if (status === "Running") {
      runBtn.disabled = true;
      runBtnText.textContent = "Running Automation...";
      spinner.classList.remove("hidden");
      progressSection.classList.remove("hidden");
    } else {
      runBtn.disabled = false;
      runBtnText.textContent = "🚀 Run Report Automation";
      spinner.classList.add("hidden");
    }
  }

  // 5. Initial State Check from Background Service Worker
  chrome.runtime.sendMessage({ action: "GET_STATE" }, (resp) => {
    if (chrome.runtime.lastError || !resp) return;

    if (resp.isRunning) {
      setStatus("Running");
      progressSection.classList.remove("hidden");
      progressCounter.textContent = `${resp.currentStep} / ${resp.totalSteps}`;
      const pct = resp.totalSteps > 0 ? (resp.currentStep / resp.totalSteps * 100) : 0;
      progressBar.style.width = `${pct}%`;
    } else if (resp.status === "Completed" && resp.sheetUrl) {
      setStatus("Ready");
      sheetLinkBtn.href = resp.sheetUrl;
      sheetLinkBtn.classList.remove("hidden");
    }

    if (resp.logs && resp.logs.length > 0) {
      consoleBody.innerHTML = "";
      resp.logs.forEach(l => addLogLine(l.text, l.type));
    }
  });

  // 6. Listen for Runtime Updates from Background
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "LOG_UPDATE") {
      if (msg.log) addLogLine(msg.log.text, msg.log.type);
      if (msg.state) {
        if (msg.state.isRunning) {
          setStatus("Running");
          progressSection.classList.remove("hidden");
          progressCounter.textContent = `${msg.state.currentStep} / ${msg.state.totalSteps}`;
          const pct = msg.state.totalSteps > 0 ? (msg.state.currentStep / msg.state.totalSteps * 100) : 0;
          progressBar.style.width = `${pct}%`;
        }
      }
    }

    if (msg.action === "JOB_DONE") {
      setStatus("Ready", "Done");
      progressSection.classList.add("hidden");
      if (msg.sheetUrl) {
        sheetLinkBtn.href = msg.sheetUrl;
        sheetLinkBtn.classList.remove("hidden");
      }
    }

    if (msg.action === "JOB_ERROR") {
      setStatus("Error", "Error");
      progressSection.classList.add("hidden");
    }
  });

  // 7. Start Automation Trigger
  runBtn.addEventListener("click", () => {
    let targetName = "";
    let targetZomatoId = "";

    if (outletSelect.value === "custom") {
      targetName = customName.value.trim() || "Custom Outlet";
      targetZomatoId = customZomatoId.value.trim();
    } else {
      const selected = outlets.find(o => o.id === outletSelect.value);
      if (selected) {
        targetName = selected.name;
        targetZomatoId = selected.zomato_id;
      }
    }

    let calculatedRanges = [];
    if (isCustomDateMode) {
      if (!startDate.value || !endDate.value) {
        alert("Please select both a Start Date and an End Date.");
        return;
      }
      const cRange = getCustomDates(startDate.value, endDate.value);
      calculatedRanges = [cRange];
    } else {
      calculatedRanges = getWeeklyDateRanges(currentWeeks);
    }

    const payload = {
      action: "START_AUTOMATION",
      outletName: targetName,
      zomatoId: targetZomatoId,
      worksheetName: worksheetInput.value.trim() || CONFIG.DEFAULT_WORKSHEET_NAME,
      ranges: calculatedRanges
    };

    setStatus("Running");
    sheetLinkBtn.classList.add("hidden");
    progressSection.classList.remove("hidden");
    progressBar.style.width = "0%";
    progressCounter.textContent = `0 / ${calculatedRanges.length}`;

    chrome.runtime.sendMessage(payload, (resp) => {
      if (chrome.runtime.lastError) {
        addLogLine(`Failed to start job: ${chrome.runtime.lastError.message}`, "error");
        setStatus("Error");
      }
    });
  });
});
