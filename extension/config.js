// Extension Configuration & Credentials

export const CONFIG = {
  // Google Sheets Integration
  SPREADSHEET_ID: "1KLnQnbQhOwb11W-kmT_UxHJPaCjQuUQinp-lYZs_zRE",
  DEFAULT_WORKSHEET_NAME: "Automated Reports",
  GOOGLE_SHEET_URL: "https://docs.google.com/spreadsheets/d/1KLnQnbQhOwb11W-kmT_UxHJPaCjQuUQinp-lYZs_zRE/edit?usp=sharing",

  // Service Account Credentials for Google Sheets API v4
  SERVICE_ACCOUNT: {
    client_email: "juno-digitals@juno-digitals-automation.iam.gserviceaccount.com",
    private_key_id: "71ac90290d5e2c31a724dfa1bc21c03e57e9ce62",
    private_key: "-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQDkGkItKtVF/wbI\nJPp6nBaZnDPEKX1mze/iz1EvLz3TDLLnf+kpxuLzqvAGmgSHihgTIF2qwEgt20SK\ntPY9f8ec+TaNv9fgkHblIOd5iTEXukxDCLW3DShnpajXF7496z8Gj936PUqJNxk9\nxtE/y+y4aJmKnvYj1KrWFPHuJaIto6lCS6WIEtlhzpIUayvm2QFcbh4jZdjxeNrw\ncTs2F7mYBSA2MJv+ptpdRf55iCrp7mTaudyFM+1LaSU7RtUn8IvaM2tkSO3KOFP1\nIPO7utc92lyI2RvSpY3EwZwVQrTPx8QuZWZraKpzAzRWF2voCNmxHxAtJUF1Bvgh\n8ykquqYhAgMBAAECggEAFsKM/FtEBRQ1jcZszMui0Kh+nNHj/pxJVZkImXvuAA9K\nEaHYds/uyM/zW8FF9u0/SjdGSVmeyh6RGAMG9+t2VDIksJ+mD3TyvBmcpyqagKrY\n3a5yjUWNlMv5jR7EH4MH2qSDymqPs6HRDbI3IlW7dMoRGf0TA8++TRaxbikIpeN4\nr4S/CZspVocfnQa5Hwp3kCC/A4lAm8cig98i0QR3R2WAXgbOGHEuMQVDYuLj+eUS\n4Eyh0bBfbAJCaYpQMVNu/8qHLHLH5xafECAfIK7JUomiMPbvLEkai4LRUK3GIXLi\nf3UnkB0+HbqUlogxWB0iL4xQ8AuC9FfnfjjYGVbNfQKBgQD0r1AmAxHI4Z4MjJ3t\nO3sQ7iajgvWgeHxbt9TYtJqtjSUDDnqQc7nPGCZRqasNpPg7oqmfPdCCrIudTV0J\n8O4ZCWBOSew/JhGH9GJ2O6t+AoEvvuVyykDCXzTwLoXTTPHBrI6FVcYwudpyJmap\nKX5B27gxWhnNMzx4GKWq9disRQKBgQDupqMydklTEJvcSW9rmenFxmtLSRQW4drY\n7dT01fqVcsYM6FLKL1FvNSIqI57LtmQ+t2IGcHACEfG5iblgvu/hJ+2q1wxnoaeo\nOLgFV6mQH+C3ejY09aGCoBxfMMX9hc+F55HhM4Mq3r5cYH9Pw4Yb0xKLstZohyrN\nJ0Rq6LvGLQKBgQCRXI1K58vrAU45ulggFZQZDMJbpXNy7+FBQ8bpLvItZIq2dCWQ\nJ5AdXgV1wkxigL0QAKSwe7KhzwvqWYmKXF229gEGwZfeNCl6EU9lWjGZXLeOu+Pn\n/AvY7WKvxZOvYijFnFPXFov1apRB+FpI6OOfEH8uoo5tf6DO4CWbmQ4t2QKBgQC4\nlRhKkmSaI5F5ay8LeWrvdk1MWIR6QkvjVuhMSihbaP83woUuLjT9H4qCLzTF+RdF\nzs65jkODxl9BEv3Xjza33gscBOJqUQT8vonOUAQtHgrPvm2ovociIjZvhajNMq7U\nscwJ866y/L8dceFmTyMt6C5C8JqXFFyNep6XVdTOLQKBgQCb3cu7vlxh77sBKzJn\nObv+jEJ04BGv90iMxgdtGdEymetALbmlj2cwVzMqBAXOE5EEdAS7NPUXSUpz/nyn\n+8Q+R2tkUWuxb0XnjFVr9FcsKH7bjEWX0KDe4Z+xp8HDJNCmAeP/6UGhk3dBhE/a\nDRrbrIEt+9TU4Q0wSYXEffb0EQ==\n-----END PRIVATE KEY-----\n",
    token_uri: "https://oauth2.googleapis.com/token",
    scopes: [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive"
    ]
  },

  // Zomato URLs
  ZOMATO: {
    BASE_URL: "https://www.zomato.com/partners/onlineordering",
    REPORTING_URL: "https://www.zomato.com/partners/onlineordering/reporting",
    PAYOUTS_URL: "https://www.zomato.com/partners/onlineordering/finance/payouts"
  },

  // Swiggy URLs
  SWIGGY: {
    BASE_URL: "https://partner.swiggy.com",
    REPORTS_URL: "https://partner.swiggy.com/business-metrics",
    FINANCE_URL: "https://partner.swiggy.com/finance"
  },

  // Default Pre-loaded Outlets
  DEFAULT_OUTLETS: [
    { id: "1", name: "The Paneer Story", zomato_id: "22749423", swiggy_id: "1394282" },
    { id: "2", name: "The Spice Meridian", zomato_id: "22663260", swiggy_id: "1363315" },
    { id: "3", name: "Babbu Hotel", zomato_id: "3300011", swiggy_id: "215500" },
    { id: "4", name: "Biryani Lovers", zomato_id: "22317789", swiggy_id: "1263351" }
  ]
};
