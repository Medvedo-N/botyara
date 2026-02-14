import os

VERSION = "2.0-fixed+2"
ENV = os.getenv("ENV", "staging")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", "")
SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_ID") or os.getenv("SPREADSHEET_ID", "TEST_SHEET_ID")
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "")
