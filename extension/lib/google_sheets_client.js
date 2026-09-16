// In-Browser Google Sheets API v4 Client with Web Crypto RS256 Auth

import { CONFIG } from "../config.js";
import { MetricCalculator } from "./metric_calculator.js";

function hexToRgb(hexStr) {
  const hex = hexStr.replace(/^#/, "");
  const r = parseInt(hex.substring(0, 2), 16) / 255.0;
  const g = parseInt(hex.substring(2, 4), 16) / 255.0;
  const b = parseInt(hex.substring(4, 6), 16) / 255.0;
  return { red: r, green: g, blue: b };
}

function base64UrlEncode(strOrBuffer) {
  let base64 = "";
  if (typeof strOrBuffer === "string") {
    base64 = btoa(unescape(encodeURIComponent(strOrBuffer)));
  } else {
    const bytes = new Uint8Array(strOrBuffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    base64 = btoa(binary);
  }
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function pemToArrayBuffer(pem) {
  const b64 = pem
    .replace(/-----BEGIN PRIVATE KEY-----/g, "")
    .replace(/-----END PRIVATE KEY-----/g, "")
    .replace(/\s+/g, "");
  const binary = atob(b64);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return buffer;
}

function colIndexToA1(cIdx) {
  let result = "";
  cIdx += 1;
  while (cIdx > 0) {
    const remainder = (cIdx - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    cIdx = Math.floor((cIdx - 1) / 26);
  }
  return result;
}

export class GoogleSheetsClient {
  constructor(serviceAccount = CONFIG.SERVICE_ACCOUNT, defaultSpreadsheetId = CONFIG.SPREADSHEET_ID) {
    this.serviceAccount = serviceAccount;
    this.spreadsheetId = defaultSpreadsheetId;
    this.accessToken = null;
    this.tokenExpiry = 0;
    this.cryptoKey = null;

    // Palette
    this.COLOR_TITLE_BG = hexToRgb("CCA9C2");        // Light mauve
    this.COLOR_REPORT_TYPE_BG = hexToRgb("434343");  // Dark grey
    this.COLOR_REPORT_TYPE_TXT = hexToRgb("FFFFFF"); // White text
    this.COLOR_LINE_ITEMS_BG = hexToRgb("8EA6B4");   // Muted teal/blue
    this.COLOR_ZOMATO_BG = hexToRgb("D32F2F");       // Zomato Red
    this.COLOR_SWIGGY_BG = hexToRgb("E69138");       // Swiggy Orange
    this.COLOR_ZS_BG = hexToRgb("A9D18E");           // Light Green
    this.COLOR_HIGHLIGHT_ROW = hexToRgb("F9CB9C");   // Peach / Light Orange
    this.COLOR_BORDER = hexToRgb("000000");          // Black
  }

  async getAccessToken() {
    const nowSec = Math.floor(Date.now() / 1000);
    if (this.accessToken && this.tokenExpiry > nowSec + 60) {
      return this.accessToken;
    }

    if (!this.cryptoKey) {
      const keyBuffer = pemToArrayBuffer(this.serviceAccount.private_key);
      this.cryptoKey = await crypto.subtle.importKey(
        "pkcs8",
        keyBuffer,
        { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
        false,
        ["sign"]
      );
    }

    const header = { alg: "RS256", typ: "JWT" };
    const claims = {
      iss: this.serviceAccount.client_email,
      scope: this.serviceAccount.scopes.join(" "),
      aud: this.serviceAccount.token_uri,
      exp: nowSec + 3600,
      iat: nowSec
    };

    const headerB64 = base64UrlEncode(JSON.stringify(header));
    const claimsB64 = base64UrlEncode(JSON.stringify(claims));
    const payloadToSign = `${headerB64}.${claimsB64}`;

    const enc = new TextEncoder();
    const signatureBuffer = await crypto.subtle.sign(
      "RSASSA-PKCS1-v1_5",
      this.cryptoKey,
      enc.encode(payloadToSign)
    );

    const sigB64 = base64UrlEncode(signatureBuffer);
    const jwt = `${payloadToSign}.${sigB64}`;

    // Exchange JWT for Access Token
    const res = await fetch(this.serviceAccount.token_uri, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
        assertion: jwt
      })
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Google OAuth2 token exchange failed (${res.status}): ${errText}`);
    }

    const tokenData = await res.json();
    this.accessToken = tokenData.access_token;
    this.tokenExpiry = nowSec + (tokenData.expires_in || 3600);
    return this.accessToken;
  }

  async getSpreadsheet(spreadsheetId = this.spreadsheetId) {
    const token = await this.getAccessToken();
    const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) {
      throw new Error(`Failed to load spreadsheet (${res.status}): ${await res.text()}`);
    }
    return await res.json();
  }

  async getOrCreateWorksheet(worksheetName = CONFIG.DEFAULT_WORKSHEET_NAME, spreadsheetId = this.spreadsheetId) {
    const spreadsheet = await this.getSpreadsheet(spreadsheetId);
    let sheet = spreadsheet.sheets.find(s => s.properties.title === worksheetName);

    if (!sheet) {
      const token = await this.getAccessToken();
      const addRes = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}:batchUpdate`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          requests: [
            {
              addSheet: {
                properties: {
                  title: worksheetName,
                  gridProperties: { rowCount: 50, columnCount: 50 }
                }
              }
            }
          ]
        })
      });

      if (!addRes.ok) {
        throw new Error(`Failed to create worksheet tab '${worksheetName}': ${await addRes.text()}`);
      }
      const addData = await addRes.json();
      sheet = addData.replies[0].addSheet;
    }

    return sheet.properties;
  }

  async findNextStartColumn(worksheetName, spreadsheetId = this.spreadsheetId) {
    const token = await this.getAccessToken();
    const range = encodeURIComponent(`'${worksheetName}'!1:25`);
    const res = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${range}`, {
      headers: { Authorization: `Bearer ${token}` }
    });

    if (!res.ok) {
      return 0;
    }

    const data = await res.json();
    const rows = data.values || [];
    if (rows.length === 0) {
      return 0;
    }

    let maxColUsed = 0;
    for (const row of rows) {
      for (let c = row.length - 1; c >= 0; c--) {
        if (row[c] !== undefined && row[c] !== null && String(row[c]).trim() !== "") {
          if (c + 1 > maxColUsed) {
            maxColUsed = c + 1;
          }
          break;
        }
      }
    }

    if (maxColUsed === 0) return 0;
    // Leave 1 blank column gap between side-by-side tables
    return maxColUsed + 1;
  }

  async generateReport({
    zomatoMetrics = null,
    swiggyMetrics = null,
    restaurantName = "Restaurant",
    restaurantId = "N/A",
    dateRangeLabel = "Weekly Report",
    reportTitle = "Weekly Report",
    worksheetName = CONFIG.DEFAULT_WORKSHEET_NAME,
    spreadsheetId = this.spreadsheetId,
    startCol = null
  }) {
    const token = await this.getAccessToken();
    const sheetProps = await this.getOrCreateWorksheet(worksheetName, spreadsheetId);
    const sheetId = sheetProps.sheetId;

    if (startCol === null) {
      startCol = await this.findNextStartColumn(worksheetName, spreadsheetId);
    }

    const endCol = startCol + 4; // 4 columns: Line Items, Zomato, Swiggy, Z+S
    const rowsConfig = MetricCalculator.buildRowsConfig(zomatoMetrics, swiggyMetrics);

    const titleText = `${restaurantName} (Id: ${restaurantId})`;

    // 1. Grid values array (25 rows)
    const tableValues = [
      [titleText, "", "", ""],
      [dateRangeLabel, "", "", ""],
      [reportTitle, "", "", ""],
      ["Line Items", "Zomato", "Swiggy", "Z+S"]
    ];

    for (const item of rowsConfig) {
      tableValues.push([item.name, item.z_val, item.s_val, item.zs_val]);
    }

    // 2. Ensure enough columns exist in sheet
    if (sheetProps.gridProperties.columnCount < endCol + 2) {
      const neededCols = (endCol + 5) - sheetProps.gridProperties.columnCount;
      await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}:batchUpdate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          requests: [
            {
              appendDimension: {
                sheetId: sheetId,
                dimension: "COLUMNS",
                length: neededCols
              }
            }
          ]
        })
      });
    }

    // 3. Write Cell Values using values.update
    const startColA1 = colIndexToA1(startCol);
    const endColA1 = colIndexToA1(endCol - 1);
    const writeRange = `'${worksheetName}'!${startColA1}1:${endColA1}25`;

    const valRes = await fetch(
      `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(writeRange)}?valueInputOption=USER_ENTERED`,
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ values: tableValues })
      }
    );

    if (!valRes.ok) {
      throw new Error(`Failed to write values to Google Sheet: ${await valRes.text()}`);
    }

    // 4. Build formatting requests
    const requests = [];

    // Merges for Row 1, Row 2, Row 3
    for (let rIdx = 0; rIdx < 3; rIdx++) {
      requests.push({
        mergeCells: {
          range: {
            sheetId: sheetId,
            startRowIndex: rIdx,
            endRowIndex: rIdx + 1,
            startColumnIndex: startCol,
            endColumnIndex: endCol
          },
          mergeType: "MERGE_ALL"
        }
      });
    }

    // Thin borders on all cells
    const thinBorder = {
      style: "SOLID",
      width: 1,
      color: this.COLOR_BORDER
    };
    requests.push({
      updateBorders: {
        range: {
          sheetId: sheetId,
          startRowIndex: 0,
          endRowIndex: 25,
          startColumnIndex: startCol,
          endColumnIndex: endCol
        },
        top: thinBorder,
        bottom: thinBorder,
        left: thinBorder,
        right: thinBorder,
        innerHorizontal: thinBorder,
        innerVertical: thinBorder
      }
    });

    // Format Row 1 & 2 (Title & Date Range)
    requests.push({
      repeatCell: {
        range: {
          sheetId: sheetId,
          startRowIndex: 0,
          endRowIndex: 2,
          startColumnIndex: startCol,
          endColumnIndex: endCol
        },
        cell: {
          userEnteredFormat: {
            backgroundColor: this.COLOR_TITLE_BG,
            horizontalAlignment: "CENTER",
            verticalAlignment: "MIDDLE",
            textFormat: { fontSize: 11, bold: true }
          }
        },
        fields: "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
      }
    });

    // Format Row 3 (Report Title / "Weekly Report")
    requests.push({
      repeatCell: {
        range: {
          sheetId: sheetId,
          startRowIndex: 2,
          endRowIndex: 3,
          startColumnIndex: startCol,
          endColumnIndex: endCol
        },
        cell: {
          userEnteredFormat: {
            backgroundColor: this.COLOR_REPORT_TYPE_BG,
            horizontalAlignment: "CENTER",
            verticalAlignment: "MIDDLE",
            textFormat: { fontSize: 11, bold: true, foregroundColor: this.COLOR_REPORT_TYPE_TXT }
          }
        },
        fields: "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
      }
    });

    // Format Row 4 (Headers)
    const headersBg = [
      this.COLOR_LINE_ITEMS_BG,
      this.COLOR_ZOMATO_BG,
      this.COLOR_SWIGGY_BG,
      this.COLOR_ZS_BG
    ];
    headersBg.forEach((bg, cOffset) => {
      requests.push({
        repeatCell: {
          range: {
            sheetId: sheetId,
            startRowIndex: 3,
            endRowIndex: 4,
            startColumnIndex: startCol + cOffset,
            endColumnIndex: startCol + cOffset + 1
          },
          cell: {
            userEnteredFormat: {
              backgroundColor: bg,
              horizontalAlignment: "CENTER",
              verticalAlignment: "MIDDLE",
              textFormat: { bold: true, italic: true }
            }
          },
          fields: "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
        }
      });
    });

    // Format Data Rows (Rows 5-25, 0-indexed 4-25)
    requests.push({
      repeatCell: {
        range: {
          sheetId: sheetId,
          startRowIndex: 4,
          endRowIndex: 25,
          startColumnIndex: startCol,
          endColumnIndex: endCol
        },
        cell: {
          userEnteredFormat: {
            horizontalAlignment: "CENTER",
            verticalAlignment: "MIDDLE",
            textFormat: { fontSize: 10, bold: false }
          }
        },
        fields: "userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat)"
      }
    });

    // Highlights & Bold Rows
    rowsConfig.forEach((item, idx) => {
      const rNum = 4 + idx;
      if (item.highlight) {
        requests.push({
          repeatCell: {
            range: {
              sheetId: sheetId,
              startRowIndex: rNum,
              endRowIndex: rNum + 1,
              startColumnIndex: startCol,
              endColumnIndex: endCol
            },
            cell: {
              userEnteredFormat: {
                backgroundColor: this.COLOR_HIGHLIGHT_ROW,
                textFormat: { bold: true }
              }
            },
            fields: "userEnteredFormat(backgroundColor,textFormat)"
          }
        });
      } else if (item.bold) {
        requests.push({
          repeatCell: {
            range: {
              sheetId: sheetId,
              startRowIndex: rNum,
              endRowIndex: rNum + 1,
              startColumnIndex: startCol,
              endColumnIndex: endCol
            },
            cell: {
              userEnteredFormat: {
                textFormat: { bold: true }
              }
            },
            fields: "userEnteredFormat(textFormat)"
          }
        });
      }
    });

    // Column Dimensions (Widths)
    requests.push({
      updateDimensionProperties: {
        range: {
          sheetId: sheetId,
          dimension: "COLUMNS",
          startIndex: startCol,
          endIndex: startCol + 1
        },
        properties: { pixelSize: 170 },
        fields: "pixelSize"
      }
    });
    requests.push({
      updateDimensionProperties: {
        range: {
          sheetId: sheetId,
          dimension: "COLUMNS",
          startIndex: startCol + 1,
          endIndex: endCol
        },
        properties: { pixelSize: 110 },
        fields: "pixelSize"
      }
    });
    requests.push({
      updateDimensionProperties: {
        range: {
          sheetId: sheetId,
          dimension: "COLUMNS",
          startIndex: endCol,
          endIndex: endCol + 1
        },
        properties: { pixelSize: 30 },
        fields: "pixelSize"
      }
    });

    // Send batchUpdate formatting request
    const batchRes = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}:batchUpdate`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ requests })
    });

    if (!batchRes.ok) {
      throw new Error(`Failed to format Google Sheet table: ${await batchRes.text()}`);
    }

    const tabUrl = `https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit#gid=${sheetId}`;
    return tabUrl;
  }
}
