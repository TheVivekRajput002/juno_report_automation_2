# Report Automation Rules

## Excel Generation & Cell Values
- Never write raw uncalculated formula strings (e.g., `"=B6-B7"`, `"=IF(B5>0,B8/B5,0)"`) into Excel cells.
- Always write direct evaluated values (`z_val`, `zs_val`).

## Percentage Line Items Format
All percentage fields must be formatted as formatted string `f"{val:.2f}%"` (`value * 100 %`):
- Discount %: `(total_discount / subtotal) * 100` -> `"XX.XX%"`
- Commission %: `(commission / sales_after_discount) * 100` -> `"XX.XX%"`
- Ads %: `(ads / subtotal) * 100` -> `"XX.XX%"`
- Payout %: `(cash_in_bank / subtotal) * 100` -> `"XX.XX%"`
- Visibility: `"XX.XX%"`
- I2M: `"XX.XX%"`
- C2O: `"XX.XX%"`
- M2O: `"XX.XX%"`

## Derived Metrics Rules
- Sales after discount = `subtotal - total_discount` (numeric)
- Net order value = `round(sales_after_discount / orders, 2)` (numeric)
