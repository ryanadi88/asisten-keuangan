"""
Unit tests for Telegram Bot Application builder and handler registration.
"""

import pytest
from main import create_bot_application
from telegram.ext import CommandHandler


def test_bot_application_builder():
    app = create_bot_application()
    assert app is not None

    # Check registered command handlers
    registered_handlers = app.handlers[0]  # Group 0
    cmd_names = []
    for h in registered_handlers:
        if isinstance(h, CommandHandler):
            cmd_names.extend(list(h.commands))

    expected_cmds = [
        "start",
        "help",
        "status",
        "report",
        "buffer",
        "draw_buffer",
        "history",
        "settings",
        "invoice",
        "invoices",
        "unpaid",
        "pay_invoice",
        "remind_invoice",
        "export",
        "set_salary",
        "set_tax",
        "set_needs",
        "set_wants",
        "set_ops",
        "set_name",
        "set_bank",
    ]

    for expected in expected_cmds:
        assert expected in cmd_names, f"Command /{expected} should be registered in bot"
