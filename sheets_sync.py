import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine import load_all_keywords, COLUMNS

CONFIG_FILE = os.path.join(BASE_DIR, "sheets_config.json")
DEFAULT_CREDS_FILE = os.path.join(BASE_DIR, "credentials.json")

def load_sheets_config():
    """Loads Google Sheets connection configuration if present."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[SheetsSync] Error reading config: {e}")
    return {
        "sheet_id_or_url": "",
        "credentials_path": DEFAULT_CREDS_FILE if os.path.exists(DEFAULT_CREDS_FILE) else "",
        "worksheet_name": "Keywords"
    }

def save_sheets_config(sheet_id_or_url, credentials_path=None, worksheet_name="Keywords"):
    """Saves Google Sheets connection configuration."""
    config = {
        "sheet_id_or_url": sheet_id_or_url.strip(),
        "credentials_path": credentials_path.strip() if credentials_path else DEFAULT_CREDS_FILE,
        "worksheet_name": worksheet_name.strip() if worksheet_name else "Keywords"
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config

def get_sheets_status():
    """Returns an object indicating whether Google Sheets integration is configured."""
    config = load_sheets_config()
    sheet_set = bool(config.get("sheet_id_or_url"))
    creds_path = config.get("credentials_path") or DEFAULT_CREDS_FILE
    creds_exist = os.path.exists(creds_path) if creds_path else False
    
    # Extract client email if creds exist
    client_email = ""
    if creds_exist:
        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                client_email = cdata.get("client_email", "")
        except:
            pass

    return {
        "configured": sheet_set and creds_exist,
        "sheet_id_or_url": config.get("sheet_id_or_url", ""),
        "credentials_path": creds_path,
        "credentials_exist": creds_exist,
        "client_email": client_email,
        "worksheet_name": config.get("worksheet_name", "Keywords")
    }

def sync_keywords_to_sheet(sheet_id_or_url=None, creds_path=None, worksheet_name="Keywords"):
    """
    Synchronizes all keywords from the local CSV database to the specified Google Spreadsheet.
    Creates headers and prevents duplicates.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return {
            "success": False, 
            "message": "Required libraries not found. Run 'pip install gspread google-auth' to enable Google Sheets sync."
        }

    config = load_sheets_config()
    target_sheet = (sheet_id_or_url or config.get("sheet_id_or_url", "")).strip()
    target_creds = (creds_path or config.get("credentials_path") or DEFAULT_CREDS_FILE).strip()
    target_ws = worksheet_name or config.get("worksheet_name", "Keywords")

    if not target_sheet:
        return {"success": False, "message": "Please provide a Google Spreadsheet URL or Sheet ID."}

    if not os.path.exists(target_creds):
        return {
            "success": False, 
            "message": f"Credentials file '{target_creds}' not found. Download your Service Account JSON from Google Cloud Console and save it as '{DEFAULT_CREDS_FILE}'."
        }

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        credentials = Credentials.from_service_account_file(target_creds, scopes=scopes)
        client = gspread.authorize(credentials)

        # Open by URL or Key/ID
        if "docs.google.com" in target_sheet:
            spreadsheet = client.open_by_url(target_sheet)
        else:
            spreadsheet = client.open_by_key(target_sheet)

        # Select or create worksheet
        try:
            worksheet = spreadsheet.worksheet(target_ws)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=target_ws, rows="1000", cols=str(len(COLUMNS)))

        # Get existing sheet data
        existing_values = worksheet.get_all_values()
        
        # If empty, write headers
        if not existing_values:
            worksheet.append_row(COLUMNS)
            existing_keywords = set()
        else:
            header_row = existing_values[0]
            existing_keywords = {row[0].strip().lower() for row in existing_values[1:] if len(row) > 0}

        local_rows = load_all_keywords()
        rows_to_append = []

        for r in local_rows:
            kw = r.get("Keyword", "").strip()
            if kw and kw.lower() not in existing_keywords:
                row_data = [str(r.get(col, "")) for col in COLUMNS]
                rows_to_append.append(row_data)
                existing_keywords.add(kw.lower())

        if rows_to_append:
            worksheet.append_rows(rows_to_append)

        # Persist working config
        save_sheets_config(target_sheet, target_creds, target_ws)

        return {
            "success": True,
            "message": f"Successfully synced {len(rows_to_append)} new keywords to Google Sheet!",
            "new_count": len(rows_to_append),
            "total_local": len(local_rows),
            "sheet_url": spreadsheet.url
        }

    except Exception as e:
        err = str(e)
        if "The caller does not have permission" in err or "PERMISSION_DENIED" in err:
            status = get_sheets_status()
            email_info = f" ({status['client_email']})" if status.get("client_email") else ""
            return {
                "success": False,
                "message": f"Permission Denied. Please open your Google Sheet, click 'Share', and give Editor access to your Service Account email{email_info}."
            }
        return {"success": False, "message": f"Google Sheets Sync Error: {err}"}
