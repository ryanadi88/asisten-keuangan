"""
Google Sheets Professional Styler & Formatter.
Applies executive-grade UI, color palettes, custom badges, accounting number formats,
frozen headers, and column dimensions to Google Sheets.
Supports separate Income and Expenses worksheets.
"""

import logging
from typing import Optional, Dict, Any, List

import gspread

logger = logging.getLogger(__name__)

# Colors Palette (RGB 0.0 - 1.0)
COLOR_NAVY_HEADER = {"red": 0.118, "green": 0.161, "blue": 0.231}  # #1E293B
COLOR_WHITE_TEXT = {"red": 1.0, "green": 1.0, "blue": 1.0}
COLOR_BORDER_GRAY = {"red": 0.886, "green": 0.910, "blue": 0.941}  # #E2E8F0

# Badges
COLOR_GREEN_BG = {"red": 0.863, "green": 0.988, "blue": 0.906}   # #DCFCE7
COLOR_GREEN_TEXT = {"red": 0.086, "green": 0.502, "blue": 0.239} # #166534

COLOR_RED_BG = {"red": 1.000, "green": 0.894, "blue": 0.902}     # #FFE4E6
COLOR_RED_TEXT = {"red": 0.624, "green": 0.071, "blue": 0.224}   # #9F1239

COLOR_AMBER_BG = {"red": 0.996, "green": 0.953, "blue": 0.780}   # #FEF3C7
COLOR_AMBER_TEXT = {"red": 0.573, "green": 0.251, "blue": 0.055} # #92400E

# Tab Colors
TAB_COLOR_INCOME = {"red": 0.13, "green": 0.77, "blue": 0.36}       # Emerald Green
TAB_COLOR_EXPENSES = {"red": 0.96, "green": 0.25, "blue": 0.37}     # Rose Red
TAB_COLOR_GOALS = {"red": 0.96, "green": 0.62, "blue": 0.05}        # Gold / Amber
TAB_COLOR_SUBSCRIPTIONS = {"red": 0.54, "green": 0.36, "blue": 0.96} # Purple / Violet
TAB_COLOR_QUOTATIONS = {"red": 0.05, "green": 0.58, "blue": 0.53}   # Teal / Emerald
TAB_COLOR_TERMINS = {"red": 0.01, "green": 0.52, "blue": 0.78}      # Sky Blue
TAB_COLOR_SUMMARY = {"red": 0.23, "green": 0.51, "blue": 0.96}      # Royal Blue
TAB_COLOR_INVOICES = {"red": 0.96, "green": 0.62, "blue": 0.15}     # Amber
TAB_COLOR_SETTINGS = {"red": 0.45, "green": 0.55, "blue": 0.65}     # Slate


def apply_professional_styling(spreadsheet: gspread.Spreadsheet) -> None:
    """Apply complete executive UI formatting and design system to all sheets."""
    logger.info("Applying executive-grade professional styling to Google Spreadsheet '%s'...", spreadsheet.title)
    
    requests: List[Dict[str, Any]] = []

    for ws in spreadsheet.worksheets():
        sheet_id = ws.id
        title = ws.title

        # 1. Tab Color determination
        if "Income" in title:
            tab_color = TAB_COLOR_INCOME
        elif "Expense" in title:
            tab_color = TAB_COLOR_EXPENSES
        elif "Goal" in title or "Wishlist" in title:
            tab_color = TAB_COLOR_GOALS
        elif "Sub" in title or "Langganan" in title:
            tab_color = TAB_COLOR_SUBSCRIPTIONS
        elif "Quote" in title or "Penawaran" in title or "SPH" in title:
            tab_color = TAB_COLOR_QUOTATIONS
        elif "Termin" in title or "Milestone" in title:
            tab_color = TAB_COLOR_TERMINS
        elif "Summary" in title:
            tab_color = TAB_COLOR_SUMMARY
        elif "Invoice" in title:
            tab_color = TAB_COLOR_INVOICES
        else:
            tab_color = TAB_COLOR_SETTINGS

        # Freeze row 1 and set tab color
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": 1,
                    },
                    "tabColor": tab_color,
                },
                "fields": "gridProperties.frozenRowCount,tabColor",
            }
        })

        # 2. Header Row Styling (Row 0): Dark Slate Navy background, bold white text, vertically centered
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_NAVY_HEADER,
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {
                            "foregroundColor": COLOR_WHITE_TEXT,
                            "bold": True,
                            "fontSize": 10,
                        },
                        "wrapStrategy": "CLIP",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
            }
        })

        # 3. Header row height: 38 pixels
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {
                    "pixelSize": 38,
                },
                "fields": "pixelSize",
            }
        })

        # 4. Default Data formatting (Rows 1 to 1000): Middle vertical alignment
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 1000,
                },
                "cell": {
                    "userEnteredFormat": {
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {
                            "fontSize": 10,
                        },
                    }
                },
                "fields": "userEnteredFormat(verticalAlignment,textFormat)",
            }
        })

        # Sheet-specific column widths and number formats
        if "Income" in title or "Expense" in title or "Transactions" in title:
            col_widths = [90, 110, 165, 110, 130, 140, 180, 110, 350]
            for col_idx, width in enumerate(col_widths):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": col_idx,
                            "endIndex": col_idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                })

            # Currency format for Col 5 (amount)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 1000,
                        "startColumnIndex": 5,
                        "endColumnIndex": 6,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "\"Rp\"#,##0"},
                            "horizontalAlignment": "RIGHT",
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)",
                }
            })

            # Center alignment for Col 0 (ID), Col 2 (Timestamp), Col 3 (Type), Col 4 (Category)
            for c_idx in [0, 2, 3, 4]:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 1000,
                            "startColumnIndex": c_idx,
                            "endColumnIndex": c_idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment)",
                    }
                })

        elif "Summary" in title:
            col_widths = [110, 110, 140, 140, 140, 140, 140, 140, 140, 140]
            for col_idx, width in enumerate(col_widths):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": col_idx,
                            "endIndex": col_idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                })

            # Currency format for Cols 2 to 10
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 500,
                        "startColumnIndex": 2,
                        "endColumnIndex": 10,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "\"Rp\"#,##0"},
                            "horizontalAlignment": "RIGHT",
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
                }
            })

            # Center alignment for Col 0 (Month Year)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 500,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "horizontalAlignment": "CENTER",
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(horizontalAlignment,textFormat)",
                }
            })

        elif "Invoice" in title:
            col_widths = [140, 110, 180, 180, 220, 140, 90, 110, 110, 110, 220, 220, 220, 110]
            for col_idx, width in enumerate(col_widths):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": col_idx,
                            "endIndex": col_idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                })

            # Currency format for Col 5 (amount)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 500,
                        "startColumnIndex": 5,
                        "endColumnIndex": 6,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "\"Rp\"#,##0"},
                            "horizontalAlignment": "RIGHT",
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,horizontalAlignment)",
                }
            })

            # Conditional Formatting Badges for Status (Col 9: PAID, UNPAID, OVERDUE)
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 500,
                            "startColumnIndex": 9,
                            "endColumnIndex": 10,
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "PAID"}],
                            },
                            "format": {
                                "backgroundColor": COLOR_GREEN_BG,
                                "textFormat": {"foregroundColor": COLOR_GREEN_TEXT, "bold": True},
                            },
                        },
                    },
                    "index": 0,
                }
            })
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 500,
                            "startColumnIndex": 9,
                            "endColumnIndex": 10,
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "UNPAID"}],
                            },
                            "format": {
                                "backgroundColor": COLOR_AMBER_BG,
                                "textFormat": {"foregroundColor": COLOR_AMBER_TEXT, "bold": True},
                            },
                        },
                    },
                    "index": 1,
                }
            })
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 500,
                            "startColumnIndex": 9,
                            "endColumnIndex": 10,
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "OVERDUE"}],
                            },
                            "format": {
                                "backgroundColor": COLOR_RED_BG,
                                "textFormat": {"foregroundColor": COLOR_RED_TEXT, "bold": True},
                            },
                        },
                    },
                    "index": 2,
                }
            })

        elif "Goal" in title or "Wishlist" in title:
            col_widths = [90, 110, 180, 140, 140, 110, 110, 110, 120, 120]
            for col_idx, width in enumerate(col_widths):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": col_idx,
                            "endIndex": col_idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                })

            # Currency format for Col 3 (target_amount) and Col 4 (current_amount)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 200,
                        "startColumnIndex": 3,
                        "endColumnIndex": 5,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "\"Rp\"#,##0"},
                            "horizontalAlignment": "RIGHT",
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)",
                }
            })

            # Center alignment for Col 0, 5, 6, 7, 8, 9
            for c_idx in [0, 5, 6, 7, 8, 9]:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 200,
                            "startColumnIndex": c_idx,
                            "endColumnIndex": c_idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment)",
                    }
                })

        elif "Sub" in title or "Langganan" in title:
            col_widths = [90, 110, 180, 140, 110, 100, 130, 100]
            for col_idx, width in enumerate(col_widths):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": col_idx,
                            "endIndex": col_idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                })

            # Currency format for Col 3 (amount)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 200,
                        "startColumnIndex": 3,
                        "endColumnIndex": 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": "\"Rp\"#,##0"},
                            "horizontalAlignment": "RIGHT",
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(numberFormat,horizontalAlignment,textFormat)",
                }
            })

            # Center alignment for Col 0, 4, 5, 6, 7
            for c_idx in [0, 4, 5, 6, 7]:
                requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 200,
                            "startColumnIndex": c_idx,
                            "endColumnIndex": c_idx + 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "CENTER",
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment)",
                    }
                })

    try:
        spreadsheet.batch_update({"requests": requests})
        logger.info("Executive styling applied successfully to spreadsheet: %s", spreadsheet.url)
    except Exception as e:
        logger.warning("Failed to apply full batch styling: %s", e)
