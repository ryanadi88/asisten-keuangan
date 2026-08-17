"""
Fix and re-apply clean headers and formatting to all worksheets in Google Sheets.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.gsheets_db import (
    GoogleSheetsBackend,
    TX_HEADERS,
    SUMMARY_HEADERS,
    SETTINGS_HEADERS,
    INVOICE_HEADERS,
    GOAL_HEADERS,
    SUBSCRIPTION_HEADERS,
    QUOTATION_HEADERS,
    TERMIN_HEADERS,
)
from tools.sheet_styler import apply_professional_styling

def fix_all_headers():
    print("Connecting to Google Sheets...")
    db = GoogleSheetsBackend()
    sh = db._get_spreadsheet()
    print(f"Connected to Spreadsheet: {sh.title} ({sh.id})")

    sheets_to_headers = {
        "Income": TX_HEADERS,
        "Expenses": TX_HEADERS,
        "Monthly_Summary": SUMMARY_HEADERS,
        "Settings": SETTINGS_HEADERS,
        "Invoices": INVOICE_HEADERS,
        "Goals_Wishlist": GOAL_HEADERS,
        "Subscriptions": SUBSCRIPTION_HEADERS,
        "Quotations": QUOTATION_HEADERS,
        "Termins_Milestones": TERMIN_HEADERS,
    }

    for ws_name, headers in sheets_to_headers.items():
        try:
            ws = sh.worksheet(ws_name)
        except Exception:
            ws = sh.add_worksheet(title=ws_name, rows=200, cols=len(headers))

        # Check row 1
        curr_row1 = ws.row_values(1)
        if curr_row1 != headers:
            print(f"Updating headers for worksheet: {ws_name}")
            ws.update(range_name=f"A1:{chr(ord('A') + len(headers) - 1)}1", values=[headers])
        else:
            print(f"Headers already correct for: {ws_name}")

    print("Applying executive styling...")
    apply_professional_styling(sh)
    print("All headers and styling successfully updated in Google Sheets!")

if __name__ == "__main__":
    fix_all_headers()
