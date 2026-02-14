from google.auth import default
from googleapiclient.discovery import build


def get_sheets_service():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


def read_range(spreadsheet_id: str, a1_range: str):
    service = get_sheets_service()
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=a1_range)
        .execute()
    )
    return resp.get("values", [])
