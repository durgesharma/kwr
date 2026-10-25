#!/usr/bin/env python3
"""
KWR - Keyword Research Intelligence Command-Line Interface & Hub
"""
import sys
import os
import subprocess

# Ensure UTF-8 output handling on Windows consoles if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except:
        pass

BANNER = r"""
========================================================================
   _  ___          _____     ____   _   _  _____ _____ _   _ _____ 
  | |/ /\ \        / /  __ \   |  _ \ | \ | |/ ____|_   _| \ | |  ___|
  | ' /  \ \  /\  / /| |__) |  | |_) ||  \| | |  __  | | |  \| | |__  
  |  <    \ \/  \/ / |  _  /   |  _ < | . ` | | |_ | | | | . ` |  __| 
  | . \    \  /\  /  | | \ \   | |_) || |\  | |__| |_| |_| |\  | |___ 
  |_|\_\    \/  \/   |_|  \_\  |____/ |_| \_|\_____|_____|_| \_|_____|
========================================================================
  Google Autocomplete Intelligence & Keyword Discovery Suite
"""

HELP_TEXT = """
[1] QUICK START (Friction-Free Setup):
  Step 1: Install required dependencies
          pip install -r requirements.txt

  Step 2: Launch the interactive web dashboard
          python kwr.py start
          (or run: python app.py)
          Open in browser: http://127.0.0.1:5000

[2] COMMAND-LINE OPERATIONS:
  python kwr.py help               Show this complete command guide
  python kwr.py check              Verify python dependencies & configuration
  python kwr.py start              Start the web dashboard on port 5000
  python kwr.py harvest "<seed>"   Run keyword expansion from terminal
  python kwr.py sync-sheets        Sync local keywords into your Google Sheet

[3] KEYWORD HARVEST MODES:
  --mode az_suffix      Alphabet Soup Suffix: [seed] + a..z (Default)
  --mode az_prefix      Alphabet Soup Prefix: a..z + [seed]
  --mode commercial     Commercial Buyer Intent: price, cost, contractor
  --mode questions      Questions: how, what, why, which, can
  --mode numbers        Numbers: [seed] + 0..9 (sizes, dimensions, 2bhk)
  --mode deep_harvest   Full Deep Harvest (Runs all above modes)

  Example:
    python kwr.py harvest "modular kitchen" --mode commercial --loc "Navi Mumbai, Thane"

[4] GOOGLE SHEETS SETUP (Optional):
  To automatically sync keywords to your own Google Sheet:
  1. Go to Google Cloud Console (https://console.cloud.google.com).
  2. Create a project and enable 'Google Sheets API' & 'Google Drive API'.
  3. Create a Service Account and download the JSON key.
  4. Rename the key to 'credentials.json' and place it in this folder.
  5. Create a new Google Spreadsheet and click 'Share' -> paste your Service
     Account email with 'Editor' permissions.
  6. In the web dashboard, click '[Sync Google Sheet]' or run:
     python kwr.py sync-sheets --url "<YOUR_GOOGLE_SHEET_URL>"

[5] FILES & STORAGE:
  smartwood_keywords.csv   Local keyword database
  requirements.txt         Python package list
  credentials.json         Your Google Cloud Service Account key (optional)
  sheets_config.json       Saved Google Sheet settings (auto-generated)
"""

def print_banner():
    print(BANNER)

def cmd_check():
    print_banner()
    print("[*] Running System & Dependency Check...\n")
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  Python Version: {python_ver} (Minimum required: 3.8)")

    packages = {
        "flask": "Flask (Web Dashboard)",
        "requests": "Requests (Autocomplete HTTP Client)",
        "gspread": "gspread (Google Sheets Sync)",
        "google.oauth2": "google-auth (Google Cloud Authentication)"
    }

    all_ok = True
    for mod, desc in packages.items():
        try:
            __import__(mod)
            print(f"  [OK] {desc:<45} : Installed")
        except ImportError:
            print(f"  [!]  {desc:<45} : MISSING")
            all_ok = False

    print("\n" + ("=" * 70))
    if all_ok:
        print("[OK] All dependencies are installed! You are ready to run KWR.")
        print("     Run 'python kwr.py start' to launch the dashboard.")
    else:
        print("[!]  Some dependencies are missing. Install them with:")
        print("     pip install -r requirements.txt")
    print("=" * 70)

def cmd_start():
    print_banner()
    print("[*] Launching KWR Web Command Center...")
    print("[*] Address: http://127.0.0.1:5000")
    print("[*] Press Ctrl+C to stop the server.\n")
    try:
        from app import app
        app.run(host="127.0.0.1", port=5000, debug=False)
    except ImportError as e:
        print(f"[!] Error: Missing dependency: {e}")
        print("[!] Please run: pip install -r requirements.txt")
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")

def cmd_harvest(args):
    if not args:
        print("[!] Error: Missing seed keyword.")
        print("    Usage: python kwr.py harvest \"modular kitchen\" [--mode az_suffix] [--loc \"Navi Mumbai\"]")
        return

    seed = args[0]
    mode = "az_suffix"
    locs = []

    i = 1
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]
            i += 2
        elif args[i] == "--loc" and i + 1 < len(args):
            locs = [l.strip() for l in args[i + 1].split(",") if l.strip()]
            i += 2
        else:
            i += 1

    print_banner()
    print(f"[*] Starting CLI Harvest:")
    print(f"    Seed: '{seed}'")
    print(f"    Mode: {mode}")
    print(f"    Locations: {locs or 'None'}\n")

    from engine import execute_harvest, load_all_keywords

    def on_progress(p):
        sys.stdout.write(f"\r[{p['percent']}%] Query: {p['current_query'][:40]:<40} | New Keywords: {p['added_count']}")
        sys.stdout.flush()

    new_count = execute_harvest(
        seed=seed,
        mode=mode,
        locations=locs,
        progress_callback=on_progress
    )

    print(f"\n\n[OK] Harvest finished! Added {new_count} unique keywords.")
    print(f"[OK] Total database records: {len(load_all_keywords())}")

def cmd_sync_sheets(args):
    print_banner()
    print("[*] Running Google Sheets Synchronization...")
    from sheets_sync import sync_keywords_to_sheet, get_sheets_status, save_sheets_config

    sheet_url = None
    if len(args) >= 2 and args[0] == "--url":
        sheet_url = args[1]
        save_sheets_config(sheet_url)

    status = get_sheets_status()
    if not status["credentials_exist"]:
        print(f"[!] Error: Credentials file '{status['credentials_path']}' not found.")
        print("    Place your Google Service Account JSON file as 'credentials.json' in this folder.")
        print("    Run 'python kwr.py help' for step-by-step setup instructions.")
        return

    target_sheet = sheet_url or status.get("sheet_id_or_url")
    if not target_sheet:
        print("[!] Error: No Google Spreadsheet specified.")
        print("    Provide the sheet URL: python kwr.py sync-sheets --url \"<YOUR_GOOGLE_SHEET_URL>\"")
        return

    res = sync_keywords_to_sheet(sheet_id_or_url=target_sheet)
    if res.get("success"):
        print(f"[OK] {res['message']}")
        print(f"[OK] Sheet URL: {res.get('sheet_url')}")
    else:
        print(f"[!] Sync failed: {res.get('message')}")

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        print_banner()
        print(HELP_TEXT)
        return

    action = sys.argv[1].lower()
    rest = sys.argv[2:]

    if action in ("start", "run", "serve"):
        cmd_start()
    elif action in ("check", "setup", "doctor"):
        cmd_check()
    elif action in ("harvest", "find", "scrape"):
        cmd_harvest(rest)
    elif action in ("sync-sheets", "sync", "sheets"):
        cmd_sync_sheets(rest)
    else:
        print_banner()
        print(f"[!] Unknown command: '{action}'")
        print("    Run 'python kwr.py help' for available commands.")

if __name__ == "__main__":
    main()
