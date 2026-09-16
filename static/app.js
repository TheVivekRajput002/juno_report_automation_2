// ==========================================================================
// Report Automation Web App Logic (app.js)
// Self-Contained Multi-Outlet Cards & Sequential Batch Execution
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  // Global Elements
  const currentOutletNameDisplay = document.getElementById("currentOutletNameDisplay");
  const statusPill = document.getElementById("statusPill");
  const statusText = document.getElementById("statusText");
  const cardCountBadge = document.getElementById("cardCountBadge");
  const cardsContainer = document.getElementById("cardsContainer");
  const addCardBtnTop = document.getElementById("addCardBtnTop");
  const addCardBtnBottom = document.getElementById("addCardBtnBottom");
  const addAllSavedBtn = document.getElementById("addAllSavedBtn");

  const generateBtn = document.getElementById("generateBtn");
  const btnText = generateBtn.querySelector(".btn-text");
  const btnSpinner = generateBtn.querySelector(".btn-spinner");

  const executionPanel = document.getElementById("executionPanel");
  const terminalLogs = document.getElementById("terminalLogs");
  const liveSheetLink = document.getElementById("liveSheetLink");
  const clearLogsBtn = document.getElementById("clearLogsBtn");
  const setupLoginBtn = document.getElementById("setupLoginBtn");
  const setupSwiggyLoginBtn = document.getElementById("setupSwiggyLoginBtn");

  // State
  let storedOutlets = [];
  let cards = [];
  let cardIdCounter = 1;
  let isRunning = false;
  let eventSource = null;

  function getDefaultCustomDates() {
    const today = new Date();
    const dayOfWeek = today.getDay(); // 0 is Sunday, 1 is Monday
    const prevMonday = new Date(today);
    prevMonday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1) - 7);
    const prevSunday = new Date(prevMonday);
    prevSunday.setDate(prevMonday.getDate() + 6);
    return {
      start: prevMonday.toISOString().split("T")[0],
      end: prevSunday.toISOString().split("T")[0],
    };
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // --------------------------------------------------------------------------
  // 1. Fetch & Store Outlets
  // --------------------------------------------------------------------------
  async function fetchOutlets() {
    try {
      const res = await fetch("/api/outlets");
      storedOutlets = await res.json();
      if (cards.length === 0) {
        // Initialize with first saved outlet
        addCard("saved", storedOutlets[0] || null);
      } else {
        renderCards();
      }
    } catch (err) {
      console.error("Failed to load outlets:", err);
    }
  }

  // --------------------------------------------------------------------------
  // 2. Card Model & Creation
  // --------------------------------------------------------------------------
  function createCardObject(mode = "saved", initialData = null) {
    const cardId = cardIdCounter++;
    const defaultDates = getDefaultCustomDates();

    const baseConfig = {
      id: cardId,
      mode: mode,
      name: "",
      zomato_id: "",
      swiggy_id: "",
      range_type: "1", // "1", "2", "3", "custom"
      start_date: defaultDates.start,
      end_date: defaultDates.end,
      platform: "both", // "both", "z", "s"
    };

    if (initialData) {
      baseConfig.name = initialData.name || "";
      baseConfig.zomato_id = initialData.zomato_id || "";
      baseConfig.swiggy_id = initialData.swiggy_id || "";
      if (initialData.range_type) baseConfig.range_type = initialData.range_type;
      if (initialData.start_date) baseConfig.start_date = initialData.start_date;
      if (initialData.end_date) baseConfig.end_date = initialData.end_date;
      if (initialData.platform) baseConfig.platform = initialData.platform;
      return baseConfig;
    }

    if (mode === "saved" && storedOutlets.length > 0) {
      const usedZids = new Set(cards.map((c) => c.zomato_id));
      const unused = storedOutlets.find((o) => !usedZids.has(o.zomato_id)) || storedOutlets[0];
      baseConfig.name = unused.name;
      baseConfig.zomato_id = unused.zomato_id;
      baseConfig.swiggy_id = unused.swiggy_id || "";
      return baseConfig;
    }

    return baseConfig;
  }

  function addCard(mode = "saved", initialData = null) {
    const newCard = createCardObject(mode, initialData);
    cards.push(newCard);
    renderCards();
  }

  function duplicateCard(cardId) {
    const target = cards.find((c) => c.id === cardId);
    if (!target) return;
    const cloned = createCardObject(target.mode, target);
    const index = cards.findIndex((c) => c.id === cardId);
    cards.splice(index + 1, 0, cloned);
    renderCards();
  }

  function removeCard(cardId) {
    if (cards.length <= 1) return;
    cards = cards.filter((c) => c.id !== cardId);
    renderCards();
  }

  function addAllSavedAsCards() {
    if (!storedOutlets || storedOutlets.length === 0) return;
    const defaultDates = getDefaultCustomDates();
    cards = storedOutlets.map((o) => ({
      id: cardIdCounter++,
      mode: "saved",
      name: o.name,
      zomato_id: o.zomato_id,
      swiggy_id: o.swiggy_id || "",
      range_type: "1",
      start_date: defaultDates.start,
      end_date: defaultDates.end,
      platform: "both",
    }));
    renderCards();
  }

  function updateHeaderDisplays() {
    const count = cards.length;
    if (cardCountBadge) {
      cardCountBadge.textContent = `${count} Card${count > 1 ? "s" : ""}`;
    }

    if (count === 0) {
      currentOutletNameDisplay.textContent = "No Outlets Configured";
    } else if (count === 1) {
      currentOutletNameDisplay.textContent = cards[0].name || "Card 1";
    } else {
      const firstName = cards[0].name || "Card 1";
      currentOutletNameDisplay.textContent = `${firstName} (+${count - 1} more)`;
    }

    if (!isRunning) {
      btnText.textContent = count > 1 ? `Run All Configurations (${count} Cards)` : "Run All Configurations";
    }
  }

  // --------------------------------------------------------------------------
  // 3. Render Self-Contained Cards
  // --------------------------------------------------------------------------
  function renderCards() {
    cardsContainer.innerHTML = "";

    cards.forEach((card, index) => {
      const cardEl = document.createElement("div");
      cardEl.className = "outlet-card";
      cardEl.dataset.cardId = card.id;

      const isSingleCard = cards.length === 1;

      // Card Header
      const headerHtml = `
        <div class="outlet-card-top">
          <div class="outlet-card-meta">
            <span class="card-index-pill">Card #${index + 1}</span>
            <span class="card-outlet-title">${escapeHtml(card.name) || "Select or Enter Outlet"}</span>
          </div>
          <div class="outlet-card-controls">
            <div class="card-mode-toggle">
              <button type="button" class="mode-toggle-btn ${card.mode === "saved" ? "active" : ""}" data-mode="saved" title="Select from saved outlets">Saved</button>
              <button type="button" class="mode-toggle-btn ${card.mode === "custom" ? "active" : ""}" data-mode="custom" title="Enter custom outlet details">Custom</button>
            </div>
            <button type="button" class="btn-card-action btn-duplicate" title="Duplicate this card configuration">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
            <button type="button" class="btn-card-action danger btn-remove" title="Remove this card" ${isSingleCard ? "disabled" : ""}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
      `;

      // Outlet section (Saved dropdown or Custom inputs)
      let outletSectionHtml = "";
      if (card.mode === "saved") {
        let optionsHtml = "";
        storedOutlets.forEach((o) => {
          const sPart = o.swiggy_id ? ` | S: ${o.swiggy_id}` : "";
          const isSelected = (card.zomato_id && card.zomato_id === o.zomato_id) || (!card.zomato_id && card.name === o.name);
          optionsHtml += `<option value="${escapeHtml(o.zomato_id)}" data-name="${escapeHtml(o.name)}" data-swiggy="${escapeHtml(o.swiggy_id || "")}" ${isSelected ? "selected" : ""}>${escapeHtml(o.name)} (Z: ${escapeHtml(o.zomato_id)}${sPart})</option>`;
        });

        outletSectionHtml = `
          <div class="saved-mode-view">
            <div class="custom-select-wrapper">
              <select class="form-select card-outlet-select">
                ${optionsHtml}
              </select>
              <div class="select-arrow">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
            </div>
            <div class="outlet-id-badges">
              <span class="id-tag zomato"><span class="tag-lbl">Zomato ID:</span> ${escapeHtml(card.zomato_id) || "None"}</span>
              <span class="id-tag swiggy ${card.swiggy_id ? "" : "dim"}"><span class="tag-lbl">Swiggy ID:</span> ${escapeHtml(card.swiggy_id) || "None"}</span>
            </div>
          </div>
        `;
      } else {
        outletSectionHtml = `
          <div class="custom-mode-view">
            <div class="custom-inputs-grid">
              <div class="input-field">
                <label>Outlet Name</label>
                <input type="text" class="custom-name-input" placeholder="e.g. Spice Route" value="${escapeHtml(card.name)}" />
              </div>
              <div class="input-field">
                <label>Zomato ID</label>
                <input type="text" class="custom-zid-input" placeholder="e.g. 22663260" value="${escapeHtml(card.zomato_id)}" />
              </div>
              <div class="input-field">
                <label>Swiggy ID (Optional)</label>
                <input type="text" class="custom-sid-input" placeholder="e.g. 1363315" value="${escapeHtml(card.swiggy_id)}" />
              </div>
            </div>
            <div class="custom-card-foot">
              <button type="button" class="btn-save-as-stored" title="Save this custom outlet to persistent list">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                Save to Saved List
              </button>
            </div>
          </div>
        `;
      }

      // Card Controls Grid: Date Range + Platform
      const isCustomDate = card.range_type === "custom";
      const controlsGridHtml = `
        <div class="card-controls-grid">
          <!-- Date Range Block -->
          <div class="card-control-block">
            <label class="card-control-label">DATE RANGE</label>
            <div class="card-segmented-control range-segmented">
              <button type="button" class="card-segment-btn ${card.range_type === "1" ? "active" : ""}" data-range="1">1 Wk</button>
              <button type="button" class="card-segment-btn ${card.range_type === "2" ? "active" : ""}" data-range="2">2 Wks</button>
              <button type="button" class="card-segment-btn ${card.range_type === "3" ? "active" : ""}" data-range="3">3 Wks</button>
              <button type="button" class="card-segment-btn ${card.range_type === "custom" ? "active" : ""}" data-range="custom">Custom</button>
            </div>
            <div class="card-custom-date-row ${isCustomDate ? "" : "hidden"}">
              <div class="card-date-wrap">
                <label>Start</label>
                <input type="date" class="custom-start-input" value="${escapeHtml(card.start_date)}" />
              </div>
              <span class="date-sep" style="font-size:10px; color:var(--text-dim); padding:0 2px;">to</span>
              <div class="card-date-wrap">
                <label>End</label>
                <input type="date" class="custom-end-input" value="${escapeHtml(card.end_date)}" />
              </div>
            </div>
          </div>

          <!-- Platform Block -->
          <div class="card-control-block">
            <label class="card-control-label">PLATFORM</label>
            <div class="card-segmented-control platform-segmented">
              <button type="button" class="card-segment-btn ${card.platform === "both" ? "active" : ""}" data-platform="both">Both</button>
              <button type="button" class="card-segment-btn ${card.platform === "z" ? "active" : ""}" data-platform="z">Z</button>
              <button type="button" class="card-segment-btn ${card.platform === "s" ? "active" : ""}" data-platform="s" title="Swiggy">S</button>
            </div>
          </div>
        </div>
      `;

      cardEl.innerHTML = headerHtml + outletSectionHtml + controlsGridHtml;
      cardsContainer.appendChild(cardEl);

      // Event Listeners for this card
      // Mode toggle
      cardEl.querySelectorAll(".mode-toggle-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const mode = btn.dataset.mode;
          if (card.mode !== mode) {
            card.mode = mode;
            if (mode === "saved" && storedOutlets.length > 0) {
              const matched = storedOutlets.find((o) => o.zomato_id === card.zomato_id) || storedOutlets[0];
              card.name = matched.name;
              card.zomato_id = matched.zomato_id;
              card.swiggy_id = matched.swiggy_id || "";
            }
            renderCards();
          }
        });
      });

      // Duplicate Card
      const duplicateBtn = cardEl.querySelector(".btn-duplicate");
      if (duplicateBtn) {
        duplicateBtn.addEventListener("click", () => duplicateCard(card.id));
      }

      // Remove Card
      const removeBtn = cardEl.querySelector(".btn-remove");
      if (removeBtn) {
        removeBtn.addEventListener("click", () => removeCard(card.id));
      }

      // Saved Mode Select Change
      const selectEl = cardEl.querySelector(".card-outlet-select");
      if (selectEl) {
        selectEl.addEventListener("change", () => {
          const opt = selectEl.options[selectEl.selectedIndex];
          if (opt) {
            card.zomato_id = opt.value;
            card.name = opt.dataset.name || opt.textContent.split("(")[0].trim();
            card.swiggy_id = opt.dataset.swiggy || "";
            renderCards();
          }
        });
      }

      // Custom Mode Inputs
      const nameInp = cardEl.querySelector(".custom-name-input");
      const zidInp = cardEl.querySelector(".custom-zid-input");
      const sidInp = cardEl.querySelector(".custom-sid-input");

      if (nameInp) {
        nameInp.addEventListener("input", (e) => {
          card.name = e.target.value.trim();
          const titleEl = cardEl.querySelector(".card-outlet-title");
          if (titleEl) titleEl.textContent = card.name || "Enter Outlet Details";
          updateHeaderDisplays();
        });
      }
      if (zidInp) {
        zidInp.addEventListener("input", (e) => {
          card.zomato_id = e.target.value.trim();
        });
      }
      if (sidInp) {
        sidInp.addEventListener("input", (e) => {
          card.swiggy_id = e.target.value.trim();
        });
      }

      // Date Range Segmented buttons
      cardEl.querySelectorAll(".range-segmented .card-segment-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const range = btn.dataset.range;
          card.range_type = range;
          const customRow = cardEl.querySelector(".card-custom-date-row");
          if (customRow) {
            if (range === "custom") {
              customRow.classList.remove("hidden");
            } else {
              customRow.classList.add("hidden");
            }
          }
          cardEl.querySelectorAll(".range-segmented .card-segment-btn").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
        });
      });

      // Custom Date Inputs
      const startInp = cardEl.querySelector(".custom-start-input");
      const endInp = cardEl.querySelector(".custom-end-input");
      if (startInp) {
        startInp.addEventListener("change", (e) => {
          card.start_date = e.target.value;
        });
      }
      if (endInp) {
        endInp.addEventListener("change", (e) => {
          card.end_date = e.target.value;
        });
      }

      // Platform Segmented buttons
      cardEl.querySelectorAll(".platform-segmented .card-segment-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          card.platform = btn.dataset.platform;
          cardEl.querySelectorAll(".platform-segmented .card-segment-btn").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
        });
      });

      // Save custom outlet to server
      const saveAsStoredBtn = cardEl.querySelector(".btn-save-as-stored");
      if (saveAsStoredBtn) {
        saveAsStoredBtn.addEventListener("click", async () => {
          const name = (nameInp ? nameInp.value : card.name).trim();
          const zId = (zidInp ? zidInp.value : card.zomato_id).trim();
          const sId = (sidInp ? sidInp.value : card.swiggy_id).trim();

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
              card.mode = "saved";
              card.name = name;
              card.zomato_id = zId;
              card.swiggy_id = sId;
              renderCards();
              appendLog(`[✓] Saved outlet '${name}' (ZID: ${zId}) to persistent list.`, "success");
            }
          } catch (err) {
            alert("Error saving outlet: " + err.message);
          }
        });
      }
    });

    updateHeaderDisplays();
  }

  // Add Card Buttons
  if (addCardBtnTop) {
    addCardBtnTop.addEventListener("click", () => addCard("saved"));
  }
  if (addCardBtnBottom) {
    addCardBtnBottom.addEventListener("click", () => addCard("saved"));
  }
  if (addAllSavedBtn) {
    addAllSavedBtn.addEventListener("click", () => addAllSavedAsCards());
  }

  // --------------------------------------------------------------------------
  // 4. Status & Terminal Log Handling
  // --------------------------------------------------------------------------
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
    } else if (text.includes("[*]") || text.includes("[🔗]") || text.includes("[CARD") || text.includes("[REPORT")) {
      line.classList.add("text-highlight");
    }

    line.textContent = text;
    terminalLogs.appendChild(line);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  clearLogsBtn.addEventListener("click", () => {
    terminalLogs.innerHTML = '<div class="log-line text-muted">Logs cleared.</div>';
  });

  // --------------------------------------------------------------------------
  // 5. Connect SSE Log Stream
  // --------------------------------------------------------------------------
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
        } else if (data.type === "card_start") {
          setStatus(`Card ${data.card_index}/${data.total_cards}: ${data.outlet_name}`, "running");
        } else if (data.type === "step") {
          if (data.total_cards && data.total_cards > 1) {
            setStatus(`Card ${data.card_index}/${data.total_cards} (${data.step}/${data.total})`, "running");
          } else {
            setStatus(`Report ${data.step}/${data.total}`, "running");
          }
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
      btnSpinner.classList.add("hidden");
      updateHeaderDisplays();
    }
  }

  // --------------------------------------------------------------------------
  // 6. Validation & Execution Trigger
  // --------------------------------------------------------------------------
  function validateAndCollectCards() {
    if (!cards || cards.length === 0) {
      alert("Please add at least one outlet card.");
      return null;
    }

    const collected = [];
    for (let i = 0; i < cards.length; i++) {
      const card = cards[i];
      const name = (card.name || "").trim();
      const zId = (card.zomato_id || "").trim();
      const sId = (card.swiggy_id || "").trim();

      if (!name && !zId && !sId) {
        alert(`Card #${i + 1} is empty. Please select or enter an outlet.`);
        return null;
      }

      if (card.mode === "custom" && !name) {
        alert(`Please enter an Outlet Name for Card #${i + 1}.`);
        return null;
      }

      if (card.mode === "custom" && !zId && !sId) {
        alert(`Please enter at least a Zomato ID or Swiggy ID for Card #${i + 1}.`);
        return null;
      }

      if (card.range_type === "custom") {
        if (!card.start_date || !card.end_date) {
          alert(`Please select both Start Date and End Date for Card #${i + 1}.`);
          return null;
        }
      }

      collected.push({
        outlet_name: name || (zId ? `ID: ${zId}` : `Card ${i + 1}`),
        zomato_id: zId,
        swiggy_id: sId,
        range_type: card.range_type,
        weeks: parseInt(card.range_type, 10) || 1,
        start_date: card.range_type === "custom" ? card.start_date : null,
        end_date: card.range_type === "custom" ? card.end_date : null,
        platform: card.platform || "both",
      });
    }

    return collected;
  }

  generateBtn.addEventListener("click", async () => {
    if (isRunning) return;

    const validatedCards = validateAndCollectCards();
    if (!validatedCards) return;

    const payload = {
      cards: validatedCards,
      worksheet_name: "Automated Reports",
      export_excel: false,
    };

    setRunningState(true);
    const summary = validatedCards.map((c) => `${c.outlet_name} [${c.platform.toUpperCase()}]`).join(", ");
    appendLog(`\n[*] Initiating sequential extraction for ${validatedCards.length} card(s): ${summary}...`, "highlight");

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

  // --------------------------------------------------------------------------
  // 7. Login Setup Buttons
  // --------------------------------------------------------------------------
  setupLoginBtn.addEventListener("click", async () => {
    if (confirm("This will launch a browser window to complete Zomato Login. Proceed?")) {
      executionPanel.classList.remove("hidden");
      appendLog("[*] Launching browser window for Zomato Google Login setup...", "highlight");
      try {
        await fetch("/api/setup-login", { method: "POST" });
        alert("Browser window opened. Complete sign in on Zomato, then return here.");
      } catch (err) {
        alert("Error launching login: " + err.message);
      }
    }
  });

  setupSwiggyLoginBtn.addEventListener("click", async () => {
    if (confirm("This will launch a browser window to complete Swiggy Partner Login. Proceed?")) {
      executionPanel.classList.remove("hidden");
      appendLog("[*] Launching browser window for Swiggy Partner Login setup...", "highlight");
      try {
        await fetch("/api/setup-login-swiggy", { method: "POST" });
        alert("Browser window opened. Complete sign in on Swiggy Partner portal, then return here.");
      } catch (err) {
        alert("Error launching Swiggy login: " + err.message);
      }
    }
  });

  // Init
  fetchOutlets();
  initLogStream();
});
