from google.auth import default
from googleapiclient.discovery import build


def get_sheets_service():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)
