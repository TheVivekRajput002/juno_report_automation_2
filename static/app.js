// ==========================================================================
// Report Automation Web App Logic (app.js)
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const outletSelect = document.getElementById("outletSelect");
  const currentOutletNameDisplay = document.getElementById("currentOutletNameDisplay");
  const statusPill = document.getElementById("statusPill");
  const statusText = document.getElementById("statusText");
  const customToggleBtn = document.getElementById("customToggleBtn");
  const customOutletDrawer = document.getElementById("customOutletDrawer");
  const customOutletName = document.getElementById("customOutletName");
  const customZomatoId = document.getElementById("customZomatoId");
  const customSwiggyId = document.getElementById("customSwiggyId");
  const saveCustomOutletBtn = document.getElementById("saveCustomOutletBtn");
  const cancelCustomBtn = document.getElementById("cancelCustomBtn");
  
  const dateRangeSegmented = document.getElementById("dateRangeSegmented");
  const customDatePickerRow = document.getElementById("customDatePickerRow");
  const customStartDate = document.getElementById("customStartDate");
  const customEndDate = document.getElementById("customEndDate");
  
  const platformSegmented = document.getElementById("platformSegmented");
  const generateBtn = document.getElementById("generateBtn");
  const btnText = generateBtn.querySelector(".btn-text");
  const btnSpinner = generateBtn.querySelector(".btn-spinner");
  
  const executionPanel = document.getElementById("executionPanel");
  const terminalLogs = document.getElementById("terminalLogs");
  const liveSheetLink = document.getElementById("liveSheetLink");
  const clearLogsBtn = document.getElementById("clearLogsBtn");
  const setupLoginBtn = document.getElementById("setupLoginBtn");

  // State
  let storedOutlets = [];
  let selectedRangeType = "1";
  let selectedPlatform = "both";
  let isRunning = false;
  let eventSource = null;

  // Initialize Default Custom Dates (Previous complete week)
  const today = new Date();
  const dayOfWeek = today.getDay(); // 0 is Sunday, 1 is Monday
  const prevMonday = new Date(today);
  prevMonday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1) - 7);
  const prevSunday = new Date(prevMonday);
  prevSunday.setDate(prevMonday.getDate() + 6);

  customStartDate.value = prevMonday.toISOString().split("T")[0];
  customEndDate.value = prevSunday.toISOString().split("T")[0];

  // 1. Fetch & Populate Outlets
  async function fetchOutlets(selectedId = null) {
    try {
      const res = await fetch("/api/outlets");
      storedOutlets = await res.json();
      renderOutletOptions(selectedId);
    } catch (err) {
      console.error("Failed to load outlets:", err);
    }
  }

  function renderOutletOptions(selectedId = null) {
    outletSelect.innerHTML = "";
    storedOutlets.forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o.zomato_id;
      opt.dataset.name = o.name;
      opt.dataset.swiggy = o.swiggy_id || "";
      
      const sPart = o.swiggy_id ? ` | S: ${o.swiggy_id}` : "";
      opt.textContent = `${o.name} (Z: ${o.zomato_id}${sPart})`;
      
      if (selectedId && (o.id === selectedId || o.zomato_id === selectedId)) {
        opt.selected = true;
      }
      outletSelect.appendChild(opt);
    });

    updateHeaderOutletName();
  }

  function updateHeaderOutletName() {
    const selectedOpt = outletSelect.options[outletSelect.selectedIndex];
    if (selectedOpt) {
      currentOutletNameDisplay.textContent = selectedOpt.dataset.name || selectedOpt.textContent.split("(")[0].trim();
    }
  }

  outletSelect.addEventListener("change", updateHeaderOutletName);

  // 2. Custom Outlet Toggle & Save
  customToggleBtn.addEventListener("click", () => {
    customOutletDrawer.classList.toggle("hidden");
    if (!customOutletDrawer.classList.contains("hidden")) {
      customOutletName.focus();
    }
  });

  cancelCustomBtn.addEventListener("click", () => {
    customOutletDrawer.classList.add("hidden");
  });

  saveCustomOutletBtn.addEventListener("click", async () => {
    const name = customOutletName.value.trim();
    const zId = customZomatoId.value.trim();
    const sId = customSwiggyId.value.trim();

    if (!name || !zId) {
      alert("Please enter both Outlet Name and Zomato ID.");
      return;
    }

    try {
      const res = await fetch("/api/outlets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, zomato_id: zId, swiggy_id: sId }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        storedOutlets = data.outlets;
        renderOutletOptions(zId);
        customOutletDrawer.classList.add("hidden");
        customOutletName.value = "";
        customZomatoId.value = "";
        customSwiggyId.value = "";
      }
    } catch (err) {
      alert("Error saving outlet: " + err.message);
    }
  });

  // 3. Date Range Segmented Control
  dateRangeSegmented.querySelectorAll(".segment-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      dateRangeSegmented.querySelectorAll(".segment-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedRangeType = btn.dataset.range;

      if (selectedRangeType === "custom") {
        customDatePickerRow.classList.remove("hidden");
      } else {
        customDatePickerRow.classList.add("hidden");
      }
    });
  });

  // 4. Platform Segmented Control
  platformSegmented.querySelectorAll(".segment-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      platformSegmented.querySelectorAll(".segment-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedPlatform = btn.dataset.platform;
    });
  });

  // 5. Status & Log Handling
  function setStatus(status, type = "ready") {
    statusText.textContent = status;
    statusPill.className = "status-indicator-pill " + type;
  }

  function appendLog(text, logType = "normal") {
    const line = document.createElement("div");
    line.className = "log-line";
    
    if (text.includes("[✓]") || text.includes("SUCCESS") || logType === "success") {
      line.classList.add("text-success");
    } else if (text.includes("[!]") || logType === "warn") {
      line.classList.add("text-warn");
    } else if (text.includes("Error") || text.includes("Exception") || logType === "error") {
      line.classList.add("text-error");
    } else if (text.includes("[*]") || text.includes("[🔗]") || text.includes("[REPORT")) {
      line.classList.add("text-highlight");
    }

    line.textContent = text;
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  clearLogsBtn.addEventListener("click", () => {
    terminalLogs.innerHTML = '<div class="log-line text-muted">Logs cleared.</div>';
  });

  // 6. Connect SSE Log Stream
  function initLogStream() {
    if (eventSource) {
      eventSource.close();
    }
    eventSource = new EventSource("/api/stream");
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "log" && data.text) {
          appendLog(data.text);
        } else if (data.type === "sheet_ready" && data.url) {
          liveSheetLink.href = data.url;
          liveSheetLink.classList.remove("hidden");
          appendLog(`[🔗] Google Sheet Updated: ${data.url}`, "success");
        } else if (data.type === "done") {
          setStatus("Completed", "ready");
          setRunningState(false);
          if (data.sheet_url) {
            liveSheetLink.href = data.sheet_url;
            liveSheetLink.classList.remove("hidden");
          }
        } else if (data.type === "error") {
          setStatus("Error", "error");
          setRunningState(false);
          appendLog(`[!] Error: ${data.message}`, "error");
        }
      } catch (err) {
        // Keepalive or raw text
      }
    };

    eventSource.onerror = () => {
      // Reconnect automatically handled by EventSource
    };
  }

  function setRunningState(running) {
    isRunning = running;
    generateBtn.disabled = running;
    if (running) {
      btnText.textContent = "Running Automation...";
      btnSpinner.classList.remove("hidden");
      setStatus("Running...", "running");
      executionPanel.classList.remove("hidden");
    } else {
      btnText.textContent = "Generate & Sync Report";
      btnSpinner.classList.add("hidden");
    }
  }

  // 7. Run Automation Click
  generateBtn.addEventListener("click", async () => {
    if (isRunning) return;

    const selectedOpt = outletSelect.options[outletSelect.selectedIndex];
    if (!selectedOpt) {
      alert("Please select or enter an outlet.");
      return;
    }

    const outletName = selectedOpt.dataset.name || selectedOpt.textContent.split("(")[0].trim();
    const zomatoId = selectedOpt.value;
    const swiggyId = selectedOpt.dataset.swiggy || "";

    const payload = {
      outlet_name: outletName,
      zomato_id: zomatoId,
      swiggy_id: swiggyId,
      range_type: selectedRangeType,
      weeks: parseInt(selectedRangeType, 10) || 1,
      start_date: selectedRangeType === "custom" ? customStartDate.value : null,
      end_date: selectedRangeType === "custom" ? customEndDate.value : null,
      platform: selectedPlatform,
      worksheet_name: "Automated Reports",
      export_excel: false,
    };

    setRunningState(true);
    appendLog(`\n[*] Initiating sync for: ${outletName} (ZID: ${zomatoId})...`, "highlight");

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Failed to start automation");
      }
    } catch (err) {
      alert("Failed to start: " + err.message);
      setRunningState(false);
      setStatus("Error", "error");
      appendLog(`[!] Start error: ${err.message}`, "error");
    }
  });

  // 8. Google Login Setup Button
  setupLoginBtn.addEventListener("click", async () => {
    if (confirm("This will launch a browser window to complete Google Login. Proceed?")) {
      executionPanel.classList.remove("hidden");
      appendLog("[*] Launching browser window for Google Login setup...", "highlight");
      try {
        await fetch("/api/setup-login", { method: "POST" });
        alert("Browser window opened. Complete sign in on Zomato, then return here.");
      } catch (err) {
        alert("Error launching login: " + err.message);
      }
    }
  });

  // Init
  fetchOutlets();
  initLogStream();
});
