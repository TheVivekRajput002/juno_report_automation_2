# Report Automation Guidelines & Rules

## 1. Google Sheets & Excel Z+S Formula Rules
- **Dynamic Formulas for Z+S**: The Z+S combined column must always contain live spreadsheet formulas referencing the Zomato and Swiggy columns (e.g. `={Z_col}{r}+{S_col}{r}`, `=IFERROR(ROUND({ZS_col}{r_sales}/{ZS_col}{r_orders}, 2), 0)`, `=IFERROR(AVERAGE({Z_col}{r}, {S_col}{r}), 0)`). This ensures the combined column dynamically recalculates whenever platform data is updated.
- **Cell Number Formatting**: Cells containing formulas (such as percentages and currency) must have explicit `numberFormat` applied (`0.00%` for percentages, `#,##0` for integer numbers/currencies, `#,##0.00` for decimals, `0.0` for KPT).

## 2. Percentage Metrics Representation
All percentage metrics in reports must consistently be written as formatted percentage strings with the `%` symbol (`value * 100 %`, e.g., `"21.23%"`, `"85.50%"`):
- **Discount %**: `(Total Discount / Subtotal) * 100` -> `"XX.XX%"`
- **Commission %**: `(Commission / Sales after discount) * 100` -> `"XX.XX%"`
- **Ads %**: `(Ads / Subtotal) * 100` -> `"XX.XX%"`
- **Payout %**: `(Cash in Bank / Subtotal) * 100` -> `"XX.XX%"`
- **Visibility**: Funnel metric -> `"XX.XX%"`
- **I2M**: Funnel metric -> `"XX.XX%"`
- **C2O**: Funnel metric -> `"XX.XX%"`
- **M2O**: Funnel metric -> `"XX.XX%"`

## 3. Financial & Operational Metric Definitions
- **Orders**: Delivered orders from reporting / business reports table.
- **Subtotal**: Item subtotal under Net Order Value (Payout page).
- **Total Discount**: Sum of discounts under Net Order Value (Payout page).
- **Sales after discount**: `Subtotal - Total Discount` (Numeric).
- **Net order value**: `Sales after discount / Orders` (Numeric, rounded to 2 decimal places).
- **Commission**: Order level deductions + GST on service & payment mechanism fees @18%.
- **Ads**: Investments in growth.
- **Cash in Bank**: Estimated / Net payout.
