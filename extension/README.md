# Restaurant Report Automation — Chrome Extension

A Google Chrome extension to extract restaurant business, operational, and financial settlement data from **Zomato Partner Portal** and automatically populate styled, side-by-side analytical tables in **Google Sheets**.

---

## 🚀 Quick Setup Guide (Load in Chrome)

### Step 1: Open Chrome Extensions
1. Open Google Chrome.
2. In the address bar, type `chrome://extensions` and press **Enter**.
3. In the top-right corner of the Extensions page, toggle **Developer mode** to **ON**.

---

### Step 2: Load the Extension
1. Click the **"Load unpacked"** button in the top-left corner.
2. Navigate to your project folder and select the `extension` folder:
   ```
   /home/tvr002/Documents/Coding Files/Automations/report_automation Main/extension
   ```
3. Click **Select Folder**.
4. You will see **"Restaurant Report Automation"** appear in your list of extensions.

---

### Step 3: Pin the Extension
1. Click the **Extensions (puzzle piece)** icon in your Chrome toolbar.
2. Click the **Pin** icon next to **Restaurant Report Automation** so it stays visible on your toolbar.

---

## 📖 How to Generate Reports

1. **Log in to Zomato Partner**:
   - Open a tab in Chrome and make sure you are logged into your [Zomato Restaurant Partner Portal](https://www.zomato.com/partners/onlineordering).
2. **Open the Extension**:
   - Click the **Report Automation** icon in your toolbar.
3. **Select Outlet & Date Range**:
   - Pick an outlet from the dropdown (or choose *"➕ Enter Custom Outlet..."* and type your Outlet Name & Zomato Res ID).
   - Select the number of previous weeks (1 to 4 weeks) or choose **Custom** to enter custom start/end dates.
   - Enter your target Google Sheet tab name (default: `Automated Reports`).
4. **Click "🚀 Run Report Automation"**:
   - The extension will automatically open the Zomato reporting and payout tabs, extract the matrix table and financial breakdown, compute the reconciled metrics, and write the formatted side-by-side table to your Google Sheet.
5. **Open Google Sheet**:
   - When finished, click **"🔗 Open Live Google Sheet"** to view your report.

---

## 📊 Extracted Metrics & Formulas

- **Orders**: Delivered orders from Business Reports tab.
- **Subtotal**: Item subtotal under Net Order Value (Payouts side-drawer).
- **Total Discount**: `Promos + Flat offs / Freebies / Gold + Delivery discount`.
- **Sales after discount**: `Subtotal - Total Discount`.
- **Net order value**: `Sales after discount / Orders`.
- **Commission**: `Order level deductions + GST on service and payment mechanism fees @18%`.
- **ads**: Investments in growth.
- **Cash in Bank**: Estimated payout / Net payout (Highlighted in Peach `#F9CB9C`, Bold).
- **Percentages**: `Discount %`, `Commission %`, `Ads %`, `Payout %`, `Visibility`, `I2M`, `C2O`, `M2O` formatted as `"XX.XX%"`.

---

## 📁 Technical Architecture Reference
For deep technical documentation, data structures, and Google Sheets API integration details, see:
- [`extension-details.md`](./extension-details.md)
