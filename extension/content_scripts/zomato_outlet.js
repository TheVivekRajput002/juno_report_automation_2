// Zomato Outlet Selector Content Script

(function() {
  if (window.__ZOMATO_OUTLET_SCRIPT_LOADED__) return;
  window.__ZOMATO_OUTLET_SCRIPT_LOADED__ = true;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function selectOutlet(restaurantNameOrId) {
    if (!restaurantNameOrId) return { success: false, message: "No outlet ID or name provided" };

    const target = String(restaurantNameOrId).trim().toLowerCase();
    console.log(`[*] Selecting Zomato outlet matching: "${target}"`);

    // Check if current page already displays the target outlet
    const bodyText = document.body ? document.body.innerText.toLowerCase() : "";
    if (bodyText.includes(target)) {
      console.log(`[+] Current page already contains target outlet reference "${target}".`);
    }

    // Look for outlet selector triggers / dropdowns
    const selectorTriggers = [
      "[class*='outlet-selector']",
      "[class*='res-select']",
      "[class*='restaurant-select']",
      "[class*='outlet-dropdown']",
      "[class*='res-dropdown']",
      "header button",
      "[role='combobox']",
      "button[class*='dropdown']",
      "[class*='select-outlet']"
    ];

    let trigger = null;
    for (const sel of selectorTriggers) {
      const el = document.querySelector(sel);
      if (el && (el.innerText || "").toLowerCase().includes("change") || (el.innerText || "").includes("ID:") || (el.innerText || "").length < 50) {
        trigger = el;
        break;
      }
    }

    if (trigger) {
      try {
        trigger.click();
        await sleep(1500);
      } catch (e) {
        console.warn("[!] Error clicking outlet trigger:", e);
      }
    }

    // Look for search input inside modal / dropdown
    const searchInputs = document.querySelectorAll("input[type='text'], input[placeholder*='Search'], input[placeholder*='search'], input[placeholder*='Outlet']");
    for (const inp of searchInputs) {
      try {
        inp.focus();
        inp.value = target;
        inp.dispatchEvent(new Event("input", { bubbles: true }));
        inp.dispatchEvent(new Event("change", { bubbles: true }));
        await sleep(1000);
        break;
      } catch (e) {}
    }

    // Look for matching option / list item
    const options = document.querySelectorAll("li, [role='option'], div[class*='item'], div[class*='card'], tr, div[class*='outlet']");
    for (const opt of options) {
      const optText = (opt.innerText || "").toLowerCase();
      if (optText.includes(target) && opt.children.length < 6) {
        try {
          opt.click();
          console.log(`[+] Clicked matching outlet element: "${opt.innerText.trim()}"`);
          await sleep(2000);
          return { success: true, matched: opt.innerText.trim() };
        } catch (e) {
          console.warn("[!] Error clicking outlet option:", e);
        }
      }
    }

    return { success: true, message: "Outlet checked" };
  }

  // Listen for messages from background service worker
  chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
    if (req.action === "SELECT_OUTLET") {
      selectOutlet(req.outletId || req.outletName).then(res => sendResponse(res));
      return true; // Async response
    }
  });
})();
