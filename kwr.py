#!/usr/bin/env python3
"""
KWR - Keyword Research Intelligence Command-Line Interface & Hub
"""
import sys
import os
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

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
[1] ZERO-FRICTION SETUP (First Time Users):
  Step 1: Install required dependencies
          pip install -r requirements.txt
          (or run: python kwr.py setup)

  Step 2: Launch the interactive web dashboard
          python kwr.py start
          (Windows: double-click start.bat | Mac/Linux: ./start.sh)
          Open in browser: http://127.0.0.1:5000

[2] TERMINAL COMMANDS:
  python kwr.py help               Show this setup and user guide
  python kwr.py setup              Auto-check and install any missing packages
  python kwr.py check              Verify dependencies without installing
  python kwr.py start              Start the web dashboard on port 5000
  python kwr.py harvest "<seed>"   Run keyword research directly in terminal
  python kwr.py sync-sheets        Sync local keywords into your Google Sheet

[3] SEARCH MODES & ADVANCED ALGORITHMS (Supports comma-separated seeds: "word1, word2, word3"):
  --mode az_suffix            All Variations: [seed] + a..z (Default)
  --mode questions            Questions: how, what, why, which, can
  --mode commercial           Buying Intent: cost, price, near me, best
  --mode deep_harvest         Deep Scan: combines all angles & methods
  --mode standard             Quick Search: top direct suggestions
  --mode algo_multiseed       Multi-Word Smart Scan (algos)
  --mode algo_recursive       Recursive Snowball Graph (algos)
  --mode algo_wildcard        Wildcard & Gap Fill (algos)
  --mode algo_semantic        Semantic & Buyer Matrix (algos)
  --mode algo_questions_deep  Answer & Question Miner (algos)
  --mode algo_ultra           Ultra Deep All-In-One (algos)

  Examples:
    python kwr.py harvest "marketing tools, seo software, keyword planner" --mode algo_multiseed
    python kwr.py harvest "interior designer" --mode commercial --loc "Mumbai"
    python kwr.py harvest "solar panel" --mode algo_recursive

[4] CONNECTING YOUR GOOGLE SHEET (Optional):
  To automatically sync discovered keywords to your personal Google Sheet:
  1. Open Google Cloud Console (https://console.cloud.google.com).
  2. Create a project and enable 'Google Sheets API' & 'Google Drive API'.
  3. Create a Service Account, generate a JSON key, and save it here as:
     credentials.json
  4. Create a new Google Spreadsheet in Google Drive, click 'Share', and paste
     the Service Account email with 'Editor' permissions.
  5. Run sync anytime:
     python kwr.py sync-sheets --url "<YOUR_GOOGLE_SHEET_URL>"

[5] FILES & STORAGE:
  keywords.csv             Local keyword database (no setup required)
  requirements.txt         Python package list
  credentials.json         Google Cloud Service Account key (optional)
  sheets_config.json       Saved Google Sheet settings (auto-generated)
"""

def print_banner():
    print(BANNER)

def cmd_setup():
    print_banner()
    print("[*] Running Automatic Setup & Health Check...\n")
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  Python Version: {python_ver} (Minimum required: 3.8)\n")

    core_packages = {
        "flask": "Flask (Web Dashboard)",
        "requests": "Requests (Autocomplete HTTP Client)"
    }
    optional_packages = {
        "gspread": "gspread (Google Sheets Sync - Optional)",
        "google.oauth2": "google-auth (Google Cloud Authentication - Optional)"
    }

    missing_core = []
    print("  [Core Packages - Required]:")
    for mod, desc in core_packages.items():
        try:
            __import__(mod)
            print(f"  [OK] {desc:<45} : Installed")
        except ImportError:
            print(f"  [!]  {desc:<45} : MISSING")
            missing_core.append(mod)

    if missing_core:
        print(f"\n[*] Installing missing core dependencies ({', '.join(missing_core)})...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_core)
            print("[OK] Core dependencies installed successfully!\n")
        except Exception as e:
            print(f"[!] Pip install error: {e}")
            print(f"    Please run manually: pip install {' '.join(missing_core)}")

    print("\n  [Cloud Sync Packages - Optional]:")
    missing_opt = []
    for mod, desc in optional_packages.items():
        try:
            __import__(mod)
            print(f"  [OK] {desc:<45} : Installed")
        except ImportError:
            print(f"  [-]  {desc:<45} : Not installed (Optional)")
            missing_opt.append(mod)

    if missing_opt:
        print("\n[*] Attempting to install optional Google Sheets sync packages...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "gspread", "google-auth"])
            print("[OK] Optional packages installed successfully!")
        except Exception:
            print("[-] Optional Google Sheets packages could not be installed (not required for local keyword harvesting).")

    try:
        from engine import init_csv, get_active_sheet
        active = get_active_sheet()
        init_csv(active)
        print(f"\n  [OK] Local keyword database initialized     : {active}")
    except Exception as e:
        print(f"  [!]  Database init note: {e}")

    print("\n" + ("=" * 70))
    print("[OK] KWR IS READY TO USE!")
    print("     To launch: python kwr.py start")
    print("     (Windows: double-click start.bat | Mac/Linux: ./start.sh)")
    print("     Open http://127.0.0.1:5000 in your browser.")
    print("=" * 70)

def cmd_check():
    print_banner()
    print("[*] Running System & Dependency Check...\n")
    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  Python Version: {python_ver} (Minimum required: 3.8)\n")

    core_packages = {
        "flask": "Flask (Web Dashboard)",
        "requests": "Requests (Autocomplete HTTP Client)"
    }
    optional_packages = {
        "gspread": "gspread (Google Sheets Sync - Optional)",
        "google.oauth2": "google-auth (Google Cloud Authentication - Optional)"
    }

    core_ok = True
    print("  [Core Packages - Required]:")
    for mod, desc in core_packages.items():
        try:
            __import__(mod)
            print(f"  [OK] {desc:<45} : Installed")
        except ImportError:
            print(f"  [!]  {desc:<45} : MISSING")
            core_ok = False

    print("\n  [Cloud Sync Packages - Optional]:")
    for mod, desc in optional_packages.items():
        try:
            __import__(mod)
            print(f"  [OK] {desc:<45} : Installed")
        except ImportError:
            print(f"  [-]  {desc:<45} : Not installed (Optional)")

    print("\n" + ("=" * 70))
    if core_ok:
        print("[OK] All core dependencies are installed! You are ready to run KWR.")
        print("     Run 'python kwr.py start' to launch the dashboard.")
    else:
        print("[!]  Essential dependencies are missing. Install them with:")
        print("     pip install -r requirements.txt (or: pip install flask requests)")
    print("=" * 70)

def cmd_start():
    print_banner()
    # Check and auto-install essential dependencies if missing
    missing_core = []
    for mod in ["flask", "requests"]:
        try:
            __import__(mod)
        except ImportError:
            missing_core.append(mod)

    if missing_core:
        print(f"[*] Missing essential dependency: {', '.join(missing_core)}. Auto-installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_core)
            print("[OK] Essential packages installed successfully!\n")
        except Exception as e:
            print(f"[!] Could not auto-install: {e}")
            print(f"    Please run: pip install {' '.join(missing_core)}\n")
            return

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
        print("    Usage: python kwr.py harvest \"seo audit, technical seo\" [--mode algo_multiseed] [--loc \"New York\"]")
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
    elif action in ("setup", "init", "install"):
        cmd_setup()
    elif action in ("check", "doctor", "health"):
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
