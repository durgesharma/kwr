import csv
import io
import json
import os
import sys
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from flask import Flask, render_template_string, request, jsonify, Response, redirect, url_for
except ImportError:
    try:
        import subprocess
        print("[*] Required dependency 'flask' is missing. Auto-installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
        from flask import Flask, render_template_string, request, jsonify, Response, redirect, url_for
        print("[OK] Flask installed successfully!")
    except Exception as e:
        print(f"\n[!] Fatal: Flask could not be imported or installed: {e}")
        print("    Please run: pip install -r requirements.txt (or: pip install flask requests)\n")
        sys.exit(1)

from engine import (
    load_all_keywords, execute_harvest, update_row_in_csv, 
    delete_keywords_from_csv, init_csv, get_active_sheet, 
    set_active_sheet, list_available_sheets, create_new_sheet, 
    toggle_bookmark_in_csv, COLUMNS
)

try:
    from sheets_sync import get_sheets_status, sync_keywords_to_sheet, save_sheets_config
except ImportError:
    def get_sheets_status():
        return {
            "configured": False,
            "sheet_id_or_url": "",
            "credentials_path": "",
            "credentials_exist": False,
            "client_email": "",
            "worksheet_name": "Keywords"
        }
    def sync_keywords_to_sheet(*args, **kwargs):
        return {
            "success": False,
            "message": "Google Sheets sync is unavailable. Run: pip install gspread google-auth"
        }
    def save_sheets_config(*args, **kwargs):
        return {}

app = Flask(__name__)
init_csv()

# Global background task state
class HarvestManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.is_running = False
        self.stop_requested = False
        self.progress = 0
        self.current_query = ""
        self.added_count = 0
        self.total_queries = 0
        self.error_msg = None

    def start_job(self, seed, mode, locations, negatives, gl, hl):
        with self.lock:
            if self.is_running:
                return False, "A harvest job is already in progress."
            self.is_running = True
            self.stop_requested = False
            self.progress = 0
            self.current_query = "Initializing..."
            self.added_count = 0
            self.total_queries = 0
            self.error_msg = None

        thread = threading.Thread(
            target=self._worker, 
            args=(seed, mode, locations, negatives, gl, hl), 
            daemon=True
        )
        thread.start()
        return True, "Harvest started."

    def stop_job(self):
        with self.lock:
            if self.is_running:
                self.stop_requested = True
                return True
        return False

    def _worker(self, seed, mode, locations, negatives, gl, hl):
        def on_progress(p):
            with self.lock:
                self.progress = p.get("percent", 0)
                self.current_query = p.get("current_query", "")
                self.added_count = p.get("added_count", 0)
                self.total_queries = p.get("total_queries", 0)

        def should_stop():
            with self.lock:
                return self.stop_requested

        try:
            execute_harvest(
                seed=seed,
                mode=mode,
                locations=locations,
                negative_words=negatives,
                gl=gl,
                hl=hl,
                progress_callback=on_progress,
                stop_check=should_stop
            )
        except Exception as e:
            with self.lock:
                self.error_msg = str(e)
        finally:
            with self.lock:
                self.is_running = False
                self.progress = 100

    def get_status(self):
        with self.lock:
            return {
                "running": self.is_running,
                "progress": self.progress,
                "current_query": self.current_query,
                "added_count": self.added_count,
                "total_queries": self.total_queries,
                "error": self.error_msg
            }

harvest_manager = HarvestManager()

# ==================== STREAMLINED MINIMAL DASHBOARD ====================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <title>KWR // Keyword Research</title>
    <style>
        :root {
            --bg: #16171a;
            --surface: #1e2025;
            --surface-hover: #262930;
            --border: #2c3038;
            --border-subtle: #24272e;
            --text: #c0c6cf;
            --text-dim: #737a87;
            --text-strong: #e1e5eb;
            --accent: #2e3540;
            --accent-hover: #38414f;
            --btn-harvest: #25382d;
            --btn-harvest-hover: #2f4538;
            --text-harvest: #a1c7aa;
            --star: #a68c4e;
            --pill-tx-bg: #29241b;
            --pill-tx-text: #b59b67;
            --pill-comm-bg: #1c242e;
            --pill-comm-text: #7b97b0;
            --pill-info-bg: #1c2720;
            --pill-info-text: #7ba687;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
            line-height: 1.45;
            padding: 12px;
            -webkit-font-smoothing: antialiased;
        }

        /* Top Bar */
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 10px;
        }
        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .logo {
            font-size: 16px;
            font-weight: 800;
            color: var(--text-strong);
            letter-spacing: -0.4px;
        }
        .logo-sub {
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-dim);
            background: #1c2026;
            border: 1px solid #282f3a;
            padding: 2px 6px;
            border-radius: 3px;
            font-weight: 700;
        }
        .guide-btn {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-dim);
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            text-decoration: none;
            transition: all 0.15s ease;
        }
        .guide-btn:hover {
            background: var(--surface-hover);
            color: var(--text-strong);
            border-color: #4a5463;
        }
        .guide-badge {
            width: 14px;
            height: 14px;
            border-radius: 3px;
            background: #2b313b;
            color: #ffffff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: bold;
        }

        /* Sheet Bar */
        .sheet-bar {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
        }
        .sheet-picker {
            flex: 1;
            display: flex;
            align-items: center;
            gap: 8px;
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 6px 10px;
            border-radius: 4px;
            min-width: 0;
        }
        .sheet-picker select {
            background: transparent;
            border: none;
            color: var(--text-strong);
            font-weight: 600;
            outline: none;
            cursor: pointer;
            font-size: 12px;
            width: 100%;
            padding: 0;
            text-overflow: ellipsis;
            white-space: nowrap;
            overflow: hidden;
        }
        .sheet-picker select option {
            background: var(--surface);
            color: var(--text);
        }
        .btn-new-sheet {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-dim);
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.15s ease;
            flex-shrink: 0;
        }
        .btn-new-sheet:hover {
            background: var(--surface-hover);
            color: var(--text-strong);
            border-color: #4a5463;
        }

        /* Unified Metrics Strip & Tabs */
        .metrics-strip {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-bottom: 12px;
        }
        .metric-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 8px 10px;
            text-align: left;
            cursor: pointer;
            text-decoration: none;
            display: flex;
            flex-direction: column;
            justify-content: center;
            transition: all 0.15s ease;
            min-width: 0;
            font-family: inherit;
            font-size: inherit;
        }
        .metric-card:hover {
            background: var(--surface-hover);
            border-color: #3e4653;
        }
        .metric-card.active {
            background: #1c222b;
            border-color: #4f5b6d;
        }
        .metric-card.saved-active {
            background: #23221b;
            border-color: var(--star);
        }
        .metric-lbl {
            font-size: 10px;
            text-transform: uppercase;
            color: var(--text-dim);
            letter-spacing: 0.4px;
            font-weight: 600;
            margin-bottom: 2px;
            display: flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .metric-val {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-strong);
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .metric-card.saved-active .metric-val {
            color: var(--star);
        }
        .export-card:hover .metric-val {
            color: #93c5fd;
        }

        /* Card panels */
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 12px;
            margin-bottom: 14px;
        }

        /* Harvest Form */
        .harvest-main {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }
        .harvest-main input[type="text"] {
            flex: 2;
            min-width: 220px;
        }
        .harvest-main select {
            flex: 1.2;
            min-width: 170px;
        }
        input[type="text"], select {
            background: #121316;
            border: 1px solid var(--border);
            color: var(--text-strong);
            padding: 8px 11px;
            font-size: 13px;
            border-radius: 4px;
            outline: none;
            width: 100%;
        }
        input[type="text"]:focus, select:focus {
            border-color: #485261;
        }

        button.btn {
            background: var(--accent);
            color: var(--text-strong);
            border: 1px solid #3a424f;
            padding: 8px 15px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 4px;
            cursor: pointer;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            height: 35px;
        }
        button.btn:hover { background: var(--accent-hover); }
        button.btn-green { background: var(--btn-harvest); border-color: #354d3e; color: var(--text-harvest); }
        button.btn-green:hover { background: var(--btn-harvest-hover); }
        button.btn-danger { background: #2b1f1f; border-color: #452b2b; color: #b87b7b; }
        button.btn-danger:hover { background: #382525; color: #d18a8a; }
        button.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
        button.btn-outline:hover { background: var(--surface-hover); color: var(--text-strong); }

        .options-toggle {
            font-size: 11px;
            color: var(--text-dim);
            cursor: pointer;
            margin-top: 8px;
            display: inline-block;
            user-select: none;
        }
        .options-toggle:hover { color: var(--text); }
        .harvest-options {
            display: none;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px dashed var(--border);
        }
        .field-lbl { font-size: 11px; color: var(--text-dim); margin-bottom: 4px; display: block; }

        /* Progress Banner */
        #progressContainer {
            display: none;
            background: #171d24;
            border: 1px solid #283645;
            border-radius: 4px;
            padding: 10px 12px;
            margin-bottom: 14px;
        }
        .progress-line {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
        }
        .progress-bar-bg {
            background: #1f252e;
            height: 5px;
            border-radius: 3px;
            overflow: hidden;
            margin: 8px 0;
        }
        .progress-bar-fill {
            background: #3f614d;
            height: 100%;
            width: 0%;
            transition: width 0.2s;
        }

        /* Filter & Table Bar */
        .filter-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 10px;
        }
        .search-wrap {
            position: relative;
            min-width: 200px;
            max-width: 260px;
            flex: 1;
        }
        .search-wrap input { padding-right: 60px; }
        .search-indicator {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 11px;
            color: var(--text-dim);
            display: none;
        }
        .controls-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            flex: 2;
        }
        .filter-controls-left {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }
        .filter-controls-left select {
            width: auto;
            min-width: 85px;
            height: 30px;
            font-size: 11px;
            padding: 2px 6px;
        }
        .actions-right {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .icon-btn {
            height: 30px;
            width: 30px;
            min-width: 30px;
            padding: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 4px;
            box-sizing: border-box;
            cursor: pointer;
        }
        .table-info-line {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-top: 6px;
            margin-top: 8px;
            margin-bottom: 6px;
            border-top: 1px solid var(--border-subtle);
        }
        .row-count-text {
            font-size: 11px;
            color: var(--text-dim);
            white-space: nowrap;
        }

        /* Pagination Bar */
        .pagination-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
            padding: 10px 4px 4px 4px;
            margin-top: 8px;
            border-top: 1px solid var(--border-subtle);
            font-size: 11px;
            color: var(--text-dim);
        }
        .pagination-info {
            white-space: nowrap;
            font-weight: 500;
        }
        .pagination-controls {
            display: flex;
            align-items: center;
            gap: 4px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .page-btn {
            background: #1a1c21;
            border: 1px solid var(--border);
            color: var(--text);
            min-width: 28px;
            height: 28px;
            padding: 0 7px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .page-btn:hover:not(:disabled) {
            background: #252830;
            border-color: #3b4252;
            color: #fff;
        }
        .page-btn.active {
            background: #1e293b;
            border-color: #60a5fa;
            color: #93c5fd;
            font-weight: 600;
        }
        .page-btn:disabled {
            opacity: 0.35;
            cursor: not-allowed;
        }
        .page-dots {
            padding: 0 3px;
            color: var(--text-dim);
        }
        .pagination-size {
            display: flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
        }
        .pagination-size select {
            width: auto;
            min-width: 65px;
            height: 28px;
            padding: 2px 6px;
            font-size: 11px;
            background: #1a1c21;
            border: 1px solid var(--border);
            color: var(--text);
            border-radius: 4px;
        }

        /* Table Design */
        .table-wrap {
            overflow-x: auto;
            max-height: 62vh;
            border: 1px solid var(--border);
            border-radius: 4px;
            background: #121316;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            text-align: left;
        }
        th, td {
            padding: 7px 10px;
            border-bottom: 1px solid var(--border-subtle);
            white-space: nowrap;
        }
        th {
            background: #1a1c21;
            color: var(--text-dim);
            font-size: 11px;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 5;
            user-select: none;
        }
        tr:hover td { background: #191b20; }
        #keywordsTable tbody tr {
            content-visibility: auto;
            contain-intrinsic-size: auto 35px;
        }
        #keywordsTable tbody tr.empty-row {
            content-visibility: visible;
        }
        tr.empty-row:hover td {
            background: transparent !important;
        }
        .empty-row td {
            padding: 56px 16px;
            text-align: center;
            border-bottom: none;
            background: transparent !important;
        }
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        .empty-icon {
            color: var(--text-dim);
            opacity: 0.55;
            margin-bottom: 4px;
        }
        .empty-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-strong);
            letter-spacing: -0.01em;
        }
        .empty-desc {
            font-size: 11px;
            color: var(--text-dim);
            max-width: 280px;
            line-height: 1.4;
        }
        #keywordsTable tbody tr.row-selected td {
            background: #1b222c;
        }

        .kw-cell {
            color: var(--text-strong);
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .quick-link {
            color: var(--text-dim);
            text-decoration: none;
            font-size: 10px;
            border: 1px solid var(--border);
            padding: 1px 4px;
            border-radius: 3px;
        }
        .quick-link:hover { color: var(--text-strong); border-color: #485261; }

        /* Star Button */
        .star-btn {
            background: transparent;
            border: none;
            color: #474b54;
            font-size: 15px;
            cursor: pointer;
            padding: 0 4px;
            line-height: 1;
        }
        .star-btn:hover { color: var(--star); }
        .star-btn.active { color: var(--star); }

        /* Subtle Badges */
        .pill {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 600;
        }
        .pill-tx { background: var(--pill-tx-bg); color: var(--pill-tx-text); border: 1px solid #3d3423; }
        .pill-comm { background: var(--pill-comm-bg); color: var(--pill-comm-text); border: 1px solid #283645; }
        .pill-info { background: var(--pill-info-bg); color: var(--pill-info-text); border: 1px solid #263b2f; }

        select.table-select {
            background: #17181c;
            border: 1px solid var(--border);
            color: var(--text);
            font-size: 11px;
            padding: 2px 4px;
            border-radius: 3px;
            width: auto;
        }

        /* Square Row Delete Button */
        .row-del-btn {
            width: 24px;
            height: 24px;
            min-width: 24px;
            padding: 0;
            border-radius: 4px;
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-dim);
            font-size: 14px;
            font-weight: 600;
            line-height: 1;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.15s ease;
            font-family: inherit;
        }
        .row-del-btn:hover {
            background: #2b1f1f;
            border-color: #452b2b;
            color: #d18a8a;
        }

        /* Toast Message */
        #toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #25382d;
            border: 1px solid #354d3e;
            color: #a1c7aa;
            padding: 8px 14px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            display: none;
            z-index: 100;
            box-shadow: 0 3px 8px rgba(0,0,0,0.4);
        }

        /* Icons */
        .icon {
            vertical-align: -2px;
            display: inline-block;
            flex-shrink: 0;
        }
        .icon-left {
            margin-right: 5px;
        }

        /* Responsive Mobile Tweak */
        @media (max-width: 768px) {
            body { padding: 6px; font-size: 12px; }

            .topbar {
                display: flex;
                flex-direction: row;
                align-items: center;
                justify-content: space-between;
                padding-bottom: 8px;
                margin-bottom: 8px;
            }
            .guide-btn {
                padding: 4px 8px;
                font-size: 11px;
            }

            .sheet-bar {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-bottom: 8px;
            }
            .sheet-picker {
                padding: 5px 8px;
            }
            .sheet-picker select {
                font-size: 11px;
            }
            .btn-new-sheet {
                padding: 5px 8px;
                font-size: 11px;
            }

            .metrics-strip {
                grid-template-columns: repeat(3, 1fr);
                gap: 6px;
                margin-bottom: 8px;
            }
            .metric-card {
                padding: 6px 8px;
            }
            .metric-lbl {
                font-size: 9px;
            }
            .metric-val {
                font-size: 13px;
            }

            .harvest-main { flex-direction: column; align-items: stretch; gap: 6px; }
            .harvest-main input, .harvest-main select, .harvest-main button { width: 100%; }

            .filter-row {
                flex-direction: column;
                align-items: stretch;
                gap: 6px;
            }
            .search-wrap {
                width: 100%;
                max-width: 100%;
            }
            .controls-row {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 4px;
            }
            .filter-controls-left {
                display: flex;
                align-items: center;
                gap: 4px;
                flex-wrap: wrap;
                flex: 1;
            }
            .filter-controls-left select {
                font-size: 11px;
                padding: 2px 4px;
                min-width: 72px;
                max-width: 88px;
                height: 28px;
            }
            .actions-right {
                display: flex;
                align-items: center;
                gap: 4px;
                flex-shrink: 0;
            }
            .actions-right .icon-btn {
                height: 29px;
                width: 29px;
                min-width: 29px;
                padding: 0;
            }
            .table-info-line {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                padding-top: 5px;
                margin-top: 6px;
                margin-bottom: 6px;
                border-top: 1px solid var(--border-subtle);
            }
            .row-count-text {
                font-size: 11px;
                color: var(--text-dim);
                white-space: nowrap;
            }
            .pagination-container {
                flex-direction: column;
                align-items: center;
                gap: 6px;
            }
            .pagination-controls {
                width: 100%;
                justify-content: center;
            }
        }
    </style>
</head>
<body>

    <!-- 1. APP HEADER -->
    <div class="topbar">
        <div class="brand-wrap">
            <span class="logo">KWR</span>
            <span class="logo-sub">RESEARCH</span>
        </div>
        <a href="/guide" target="_blank" class="guide-btn" title="How to use manual">
            <span class="guide-badge">?</span>
            <span>Guide</span>
        </a>
    </div>

    <!-- 2. ACTIVE SHEET BAR -->
    <div class="sheet-bar">
        <div class="sheet-picker">
            <svg class="icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <select id="sheetSelect" onchange="switchSheet(this.value)">
                {% for s in available_sheets %}
                <option value="{{ s }}" {% if s == active_sheet %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
            </select>
        </div>
        <button type="button" class="btn-new-sheet" onclick="promptNewSheet()" title="Create new sheet on device">
            <svg class="icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            <span>New</span>
        </button>
    </div>

    <!-- 3. UNIFIED METRICS STRIP & TABS -->
    <div class="metrics-strip">
        <button type="button" class="metric-card active" id="tabAll" onclick="setViewTab('all')">
            <span class="metric-lbl">Keywords</span>
            <span class="metric-val" id="statTotal">{{ total_count }}</span>
            <span id="countAll" style="display:none;">{{ all_total_count }}</span>
        </button>

        <button type="button" class="metric-card" id="tabSaved" onclick="setViewTab('saved')">
            <span class="metric-lbl">
                <svg class="icon" viewBox="0 0 24 24" width="11" height="11" fill="currentColor" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                Saved
            </span>
            <span class="metric-val" id="statSaved">{{ saved_count }}</span>
            <span id="countSaved" style="display:none;">{{ saved_count }}</span>
        </button>

        <a href="/export" class="metric-card export-card" title="Download CSV (Selected or Current View)" onclick="exportKeywordsCSV(event)">
            <span class="metric-lbl">Export</span>
            <span class="metric-val">
                <svg class="icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                CSV
            </span>
        </a>
    </div>

    <form id="exportForm" method="POST" action="/export" style="display:none;">
        <input type="hidden" name="keywords_json" id="exportKeywordsInput" value="">
        <input type="hidden" name="export_mode" id="exportModeInput" value="all">
    </form>

    <!-- HARVESTER PANEL -->
    <div class="card">
        <form id="harvestForm" onsubmit="startHarvest(event)">
            <div class="harvest-main">
                <input type="text" id="seedInput" placeholder="Enter seed keyword..." required>
                <select id="modeSelect">
                    <option value="az_suffix" selected>All variations (A to Z scan)</option>
                    <option value="questions">Questions (How, What, Why, Where)</option>
                    <option value="commercial">Buying & Pricing (Cost, Best, Near Me)</option>
                    <option value="deep_harvest">Deep Scan (Combines all methods)</option>
                    <option value="standard">Quick Search (Direct suggestions)</option>
                    <option value="algo_multiseed">Multi-Word Smart Scan (algos)</option>
                    <option value="algo_recursive">Recursive Snowball Graph (algos)</option>
                    <option value="algo_wildcard">Wildcard & Gap Fill (algos)</option>
                    <option value="algo_semantic">Semantic & Buyer Matrix (algos)</option>
                    <option value="algo_questions_deep">Answer & Question Miner (algos)</option>
                    <option value="algo_ultra">Ultra Deep All-In-One (algos)</option>
                </select>
                <button type="submit" class="btn btn-green" id="runBtn"><svg class="icon icon-left" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Harvest</button>
            </div>

            <div class="options-toggle" onclick="toggleOptions()"><svg class="icon icon-left" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> Optional Settings (Country, City, Negative Words)</div>

            <div class="harvest-options" id="harvestOptions">
                <div>
                    <label class="field-lbl">Country & Language</label>
                    <select id="regionSelect">
                        <option value="in:en" selected>India (English)</option>
                        <option value="us:en">United States (English)</option>
                        <option value="uk:en">United Kingdom (English)</option>
                        <option value="ae:en">UAE (English)</option>
                        <option value="in:hi">India (Hindi)</option>
                    </select>
                </div>
                <div>
                    <label class="field-lbl">City or Area (optional)</label>
                    <input type="text" id="locationsInput" value="" placeholder="e.g. Mumbai, New York, London">
                </div>
                <div>
                    <label class="field-lbl">Exclude Words (optional)</label>
                    <input type="text" id="negativesInput" value="" placeholder="Skip words like: free, jobs, login">
                </div>
            </div>
        </form>
    </div>

    <!-- PROGRESS BANNER -->
    <div id="progressContainer">
        <div class="progress-line">
            <span id="progressText" style="color: #93c5fd; font-weight: 600;">Harvesting keywords...</span>
            <button class="btn btn-danger" style="height: 24px; padding: 2px 8px; font-size: 11px;" onclick="stopHarvest()">Stop</button>
        </div>
        <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="progressFill"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim);">
            <span id="currentQueryText">Query: -</span>
            <span id="harvestCountText">New: 0</span>
        </div>
    </div>

    <!-- FILTER & TABLE BAR -->
    <div class="card" style="padding: 10px;">
        <div class="filter-row">
            <div class="search-wrap">
                <input type="text" id="tableFilter" placeholder="Filter keywords..." oninput="triggerFilterLoading()">
                <span class="search-indicator" id="searchLoading">filtering...</span>
            </div>

            <div class="controls-row">
                <div class="filter-controls-left">
                    <select id="filterDateOrder" onchange="applyFilterAndSort()" title="Filter by date">
                        <option value="all">All Dates</option>
                        <option value="desc" selected>Date: Newest</option>
                        <option value="asc">Date: Oldest</option>
                    </select>

                    <select id="filterWords" onchange="applyFilterAndSort()" title="Filter by word count">
                        <option value="0">All Words</option>
                        <option value="2">2+ Words</option>
                        <option value="3">3+ Words</option>
                        <option value="4">4+ Words</option>
                        <option value="5">5+ Words</option>
                    </select>

                    <select id="filterPriority" onchange="applyFilterAndSort()" title="Filter by priority">
                        <option value="all">All Priority</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                    </select>

                    <select id="filterStatus" onchange="applyFilterAndSort()" title="Filter by validation status">
                        <option value="all">All Status</option>
                        <option value="target">Target</option>
                        <option value="unverified">Unverified</option>
                        <option value="discard">Discard</option>
                    </select>
                </div>

                <div class="actions-right">
                    <button type="button" class="btn btn-outline icon-btn" onclick="copyVisibleKeywords()" title="Copy selected or visible keywords"><svg class="icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>
                    <button type="button" class="btn btn-danger icon-btn" onclick="deleteSelected()" title="Delete selected keywords"><svg class="icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
                </div>
            </div>
        </div>

        <!-- Horizontal line with number of rows on the right -->
        <div class="table-info-line">
            <span id="rowCountLabel" class="row-count-text">{{ total_count }} rows</span>
        </div>

        <div class="table-wrap">
            <table id="keywordsTable">
                <thead>
                    <tr>
                        <th style="width: 24px;"><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this)"></th>
                        <th style="width: 32px;" title="Bookmark"><svg class="icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg></th>
                        <th>KEYWORD</th>
                        <th onclick="toggleDateSort()" style="cursor: pointer;" title="Click to sort by date">DATE <span id="dateSortArrow">↓</span></th>
                        <th>WORDS</th>
                        <th>PRIORITY</th>
                        <th>STATUS</th>
                        <th style="width: 28px;"></th>
                    </tr>
                </thead>
                <tbody id="keywordsTableBody">
                    <tr id="emptyRow" class="empty-row" style="display: {% if rows %}none{% else %}table-row{% endif %};">
                        <td colspan="8">
                            <div class="empty-state">
                                <svg class="empty-icon" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                                    <circle cx="11" cy="11" r="7"></circle>
                                    <line x1="21" y1="21" x2="16" y2="16"></line>
                                </svg>
                                <div class="empty-title" id="emptyTitle">No keywords</div>
                                <div class="empty-desc" id="emptyDesc">Enter a seed keyword above and tap Harvest to begin.</div>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Pagination Controls Bar -->
        <div class="pagination-container" id="paginationContainer">
            <div class="pagination-info" id="paginationInfo">Showing 0–0 of 0</div>
            <div class="pagination-controls" id="paginationControls"></div>
            <div class="pagination-size">
                <span>Rows:</span>
                <select id="pageSizeSelect" onchange="changePageSize(this.value)">
                    <option value="50">50</option>
                    <option value="100" selected>100</option>
                    <option value="250">250</option>
                    <option value="500">500</option>
                    <option value="0">All</option>
                </select>
            </div>
        </div>
    </div>

    <div id="toast">Copied to clipboard</div>
    <script id="initialRowsData" type="application/json">{{ rows_json | safe }}</script>

    <script>
        let pollTimer = null;
        let filterDebounce = null;
        let currentTab = 'all';
        let allKeywords = [];
        let filteredKeywords = [];
        let selectedKeywords = new Set();
        let currentPage = 1;
        let pageSize = 100;

        function initDataset() {
            try {
                const rawEl = document.getElementById("initialRowsData");
                const raw = JSON.parse(rawEl ? rawEl.textContent : "[]");
                allKeywords = raw.map((r, i) => {
                    const kw = (r['Keyword'] || '').trim();
                    const bm = r['Bookmarked'];
                    const isBookmarked = bm === 1 || bm === '1' || bm === true || bm === 'true';
                    const wc = parseInt(r['Word Count'], 10) || (kw ? kw.split(/\\s+/).filter(Boolean).length : 0);
                    const prio = (r['Priority'] || 'Medium').trim();
                    const stat = (r['Validation Status'] || 'Unverified').trim();
                    const dt = (r['Collection Date'] || '').trim();
                    return {
                        origIndex: i + 1,
                        keyword: kw,
                        keywordLower: kw.toLowerCase(),
                        date: dt,
                        words: wc,
                        priority: prio,
                        status: stat,
                        bookmarked: isBookmarked
                    };
                });
            } catch (e) {
                console.error("Failed to parse initial rows data:", e);
                allKeywords = [];
            }
        }

        function updateStatsCounters() {
            const total = allKeywords.length;
            let saved = 0;
            for (let i = 0; i < allKeywords.length; i++) {
                if (allKeywords[i].bookmarked) saved++;
            }
            const statTotal = document.getElementById("statTotal");
            const countAll = document.getElementById("countAll");
            const statSaved = document.getElementById("statSaved");
            const countSaved = document.getElementById("countSaved");
            if (statTotal) statTotal.textContent = total;
            if (countAll) countAll.textContent = total;
            if (statSaved) statSaved.textContent = saved;
            if (countSaved) countSaved.textContent = saved;
        }

        function escapeHtml(str) {
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function updateSelectionUI() {
            const totalFiltered = filteredKeywords.length;
            let selectedFilteredCount = 0;
            for (let i = 0; i < totalFiltered; i++) {
                if (selectedKeywords.has(filteredKeywords[i].keyword)) {
                    selectedFilteredCount++;
                }
            }

            const selectAll = document.getElementById("selectAll");
            if (selectAll) {
                if (totalFiltered === 0) {
                    selectAll.checked = false;
                    selectAll.indeterminate = false;
                } else if (selectedFilteredCount === totalFiltered) {
                    selectAll.checked = true;
                    selectAll.indeterminate = false;
                } else if (selectedFilteredCount > 0) {
                    selectAll.checked = false;
                    selectAll.indeterminate = true;
                } else {
                    selectAll.checked = false;
                    selectAll.indeterminate = false;
                }
            }

            const label = document.getElementById("rowCountLabel");
            if (label) {
                if (selectedKeywords.size > 0) {
                    label.innerHTML = `<span style="color: #93c5fd; font-weight: 600;">${selectedKeywords.size} selected</span> · ${totalFiltered} rows`;
                } else {
                    label.textContent = `${totalFiltered} rows`;
                }
            }
        }

        function renderCurrentPage() {
            const tbody = document.getElementById("keywordsTableBody");
            if (!tbody) return;
            const emptyRow = document.getElementById("emptyRow");
            const emptyTitle = document.getElementById("emptyTitle");
            const emptyDesc = document.getElementById("emptyDesc");

            // Remove existing rendered data rows
            const oldRows = tbody.querySelectorAll("tr:not(#emptyRow)");
            for (let i = 0; i < oldRows.length; i++) {
                oldRows[i].remove();
            }

            if (filteredKeywords.length === 0) {
                if (emptyRow) {
                    emptyRow.style.display = "";
                    if (allKeywords.length === 0) {
                        if (emptyTitle) emptyTitle.textContent = "No keywords";
                        if (emptyDesc) emptyDesc.textContent = "Enter a seed keyword above and tap Harvest to begin.";
                    } else {
                        if (emptyTitle) emptyTitle.textContent = "No keywords match filter";
                        if (emptyDesc) emptyDesc.textContent = "Try clearing your search filter or switching tabs.";
                    }
                }
                return;
            }

            if (emptyRow) {
                emptyRow.style.display = "none";
            }

            const start = (pageSize === 0) ? 0 : (currentPage - 1) * pageSize;
            const end = (pageSize === 0) ? filteredKeywords.length : Math.min(start + pageSize, filteredKeywords.length);
            const pageRows = filteredKeywords.slice(start, end);

            let html = "";
            for (let i = 0; i < pageRows.length; i++) {
                const item = pageRows[i];
                const isSelected = selectedKeywords.has(item.keyword);
                const escapedKw = escapeHtml(item.keyword);
                const encodedKw = encodeURIComponent(item.keyword);
                const isBm = item.bookmarked;

                html += `<tr class="${isSelected ? 'row-selected' : ''}" data-keyword="${escapedKw}">
                    <td>
                        <input type="checkbox" class="row-select" value="${escapedKw}" ${isSelected ? 'checked' : ''} onchange="onRowCheckboxChange(this, '${escapedKw.replace(/'/g, "\\'")}')">
                    </td>
                    <td>
                        <button type="button" class="star-btn ${isBm ? 'active' : ''}" onclick="toggleBookmarkRow(this, '${escapedKw.replace(/'/g, "\\'")}')" title="Toggle save">
                            <svg class="star-icon" viewBox="0 0 24 24" width="14" height="14" fill="${isBm ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                        </button>
                    </td>
                    <td>
                        <div class="kw-cell">
                            <span>${escapedKw}</span>
                            <span style="display: inline-flex; gap: 4px;">
                                <a class="quick-link" href="https://www.google.com/search?q=${encodedKw}" target="_blank" rel="noopener">serp</a>
                                <a class="quick-link" href="https://trends.google.com/trends/explore?q=${encodedKw}&geo=IN" target="_blank" rel="noopener">trends</a>
                            </span>
                        </div>
                    </td>
                    <td style="color: var(--text-dim); font-size: 11px;">${escapeHtml(item.date || '-')}</td>
                    <td>${item.words || '-'}</td>
                    <td>
                        <select class="table-select" onchange="updateRowField(this, 'Priority', this.value, '${escapedKw.replace(/'/g, "\\'")}')">
                            <option value="High" ${item.priority === 'High' ? 'selected' : ''}>High</option>
                            <option value="Medium" ${item.priority === 'Medium' || !item.priority ? 'selected' : ''}>Medium</option>
                            <option value="Low" ${item.priority === 'Low' ? 'selected' : ''}>Low</option>
                        </select>
                    </td>
                    <td>
                        <select class="table-select" onchange="updateRowField(this, 'Validation Status', this.value, '${escapedKw.replace(/'/g, "\\'")}')">
                            <option value="Unverified" ${item.status === 'Unverified' || !item.status ? 'selected' : ''}>Unverified</option>
                            <option value="Target" ${item.status === 'Target' ? 'selected' : ''}>Target</option>
                            <option value="Discard" ${item.status === 'Discard' ? 'selected' : ''}>Discard</option>
                        </select>
                    </td>
                    <td>
                        <button type="button" class="row-del-btn" onclick="deleteSingleKeyword('${escapedKw.replace(/'/g, "\\'")}')" title="Delete keyword">×</button>
                    </td>
                </tr>`;
            }

            if (emptyRow) {
                emptyRow.insertAdjacentHTML('afterend', html);
            } else {
                tbody.innerHTML = html;
            }
        }

        function renderPaginationUI() {
            const container = document.getElementById("paginationContainer");
            const infoEl = document.getElementById("paginationInfo");
            const controlsEl = document.getElementById("paginationControls");
            if (!container || !infoEl || !controlsEl) return;

            const total = filteredKeywords.length;
            if (total === 0) {
                infoEl.textContent = "Showing 0–0 of 0";
                controlsEl.innerHTML = "";
                return;
            }

            const totalPages = (pageSize === 0) ? 1 : Math.max(1, Math.ceil(total / pageSize));
            const startNum = (pageSize === 0) ? 1 : (currentPage - 1) * pageSize + 1;
            const endNum = (pageSize === 0) ? total : Math.min(currentPage * pageSize, total);
            infoEl.textContent = `Showing ${startNum}–${endNum} of ${total}`;

            if (pageSize === 0 || totalPages <= 1) {
                controlsEl.innerHTML = `<button type="button" class="page-btn active" disabled>1</button>`;
                return;
            }

            let btns = [];
            btns.push(`<button type="button" class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">« Prev</button>`);

            if (totalPages <= 7) {
                for (let p = 1; p <= totalPages; p++) {
                    btns.push(`<button type="button" class="page-btn ${p === currentPage ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`);
                }
            } else {
                btns.push(`<button type="button" class="page-btn ${1 === currentPage ? 'active' : ''}" onclick="goToPage(1)">1</button>`);
                if (currentPage > 4) {
                    btns.push(`<span class="page-dots">…</span>`);
                }
                let startPage = Math.max(2, currentPage - 1);
                let endPage = Math.min(totalPages - 1, currentPage + 1);
                if (currentPage <= 4) {
                    startPage = 2;
                    endPage = 4;
                } else if (currentPage >= totalPages - 3) {
                    startPage = totalPages - 3;
                    endPage = totalPages - 1;
                }
                for (let p = startPage; p <= endPage; p++) {
                    btns.push(`<button type="button" class="page-btn ${p === currentPage ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`);
                }
                if (currentPage < totalPages - 3) {
                    btns.push(`<span class="page-dots">…</span>`);
                }
                btns.push(`<button type="button" class="page-btn ${totalPages === currentPage ? 'active' : ''}" onclick="goToPage(${totalPages})">${totalPages}</button>`);
            }

            btns.push(`<button type="button" class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">Next »</button>`);
            controlsEl.innerHTML = btns.join("");
        }

        function goToPage(page) {
            const totalPages = (pageSize === 0) ? 1 : Math.max(1, Math.ceil(filteredKeywords.length / pageSize));
            if (page < 1 || page > totalPages) return;
            currentPage = page;
            renderCurrentPage();
            renderPaginationUI();
            updateSelectionUI();
            const tbl = document.getElementById("keywordsTable");
            if (tbl) {
                const rect = tbl.getBoundingClientRect();
                if (rect.top < 0) {
                    tbl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        }

        function changePageSize(size) {
            pageSize = parseInt(size, 10);
            currentPage = 1;
            renderCurrentPage();
            renderPaginationUI();
            updateSelectionUI();
        }

        function onRowCheckboxChange(cb, kw) {
            if (cb.checked) {
                selectedKeywords.add(kw);
                const tr = cb.closest("tr");
                if (tr) tr.classList.add("row-selected");
            } else {
                selectedKeywords.delete(kw);
                const tr = cb.closest("tr");
                if (tr) tr.classList.remove("row-selected");
            }
            updateSelectionUI();
        }

        function toggleSelectAll(master) {
            if (master.checked) {
                for (let i = 0; i < filteredKeywords.length; i++) {
                    selectedKeywords.add(filteredKeywords[i].keyword);
                }
            } else {
                for (let i = 0; i < filteredKeywords.length; i++) {
                    selectedKeywords.delete(filteredKeywords[i].keyword);
                }
            }
            renderCurrentPage();
            updateSelectionUI();
        }

        function applyFilterAndSort(forceSort = false) {
            const query = (document.getElementById("tableFilter")?.value || "").trim().toLowerCase();
            const dateOrder = document.getElementById("filterDateOrder") ? document.getElementById("filterDateOrder").value : "desc";
            const minWords = parseInt(document.getElementById("filterWords")?.value, 10) || 0;
            const prioFilter = document.getElementById("filterPriority") ? document.getElementById("filterPriority").value.toLowerCase() : "all";
            const statusFilter = document.getElementById("filterStatus") ? document.getElementById("filterStatus").value.toLowerCase() : "all";
            const onlySaved = (currentTab === 'saved');

            filteredKeywords = allKeywords.filter(item => {
                if (onlySaved && !item.bookmarked) return false;
                if (query && !item.keywordLower.includes(query)) return false;
                if (minWords > 0 && item.words < minWords) return false;
                if (prioFilter !== "all" && item.priority.toLowerCase() !== prioFilter) return false;
                if (statusFilter !== "all" && item.status.toLowerCase() !== statusFilter) return false;
                return true;
            });

            if (dateOrder === "asc") {
                filteredKeywords.sort((a, b) => a.date.localeCompare(b.date) || (a.origIndex - b.origIndex));
            } else if (dateOrder === "desc") {
                filteredKeywords.sort((a, b) => b.date.localeCompare(a.date) || (a.origIndex - b.origIndex));
            } else {
                filteredKeywords.sort((a, b) => a.origIndex - b.origIndex);
            }

            const arrow = document.getElementById("dateSortArrow");
            if (arrow) {
                if (dateOrder === "asc") arrow.textContent = "↑";
                else if (dateOrder === "desc") arrow.textContent = "↓";
                else arrow.textContent = "↕";
            }

            const totalPages = (pageSize === 0) ? 1 : Math.max(1, Math.ceil(filteredKeywords.length / pageSize));
            if (currentPage > totalPages) currentPage = totalPages;
            if (currentPage < 1) currentPage = 1;

            renderCurrentPage();
            renderPaginationUI();
            updateSelectionUI();
        }

        function triggerFilterLoading() {
            const loader = document.getElementById("searchLoading");
            if (loader) loader.style.display = "inline";
            if (filterDebounce) clearTimeout(filterDebounce);
            filterDebounce = setTimeout(() => {
                applyFilterAndSort();
                if (loader) loader.style.display = "none";
            }, 30);
        }

        function toggleDateSort() {
            const sel = document.getElementById("filterDateOrder");
            if (!sel) return;
            if (sel.value === "desc") sel.value = "asc";
            else if (sel.value === "asc") sel.value = "all";
            else sel.value = "desc";
            applyFilterAndSort(true);
        }

        function setViewTab(tab) {
            currentTab = tab;
            const tabAll = document.getElementById("tabAll");
            const tabSaved = document.getElementById("tabSaved");
            if (tabAll && tabSaved) {
                if (tab === 'saved') {
                    tabAll.classList.remove("active");
                    tabSaved.classList.add("saved-active");
                } else {
                    tabAll.classList.add("active");
                    tabSaved.classList.remove("saved-active");
                }
            }
            currentPage = 1;
            applyFilterAndSort();
        }

        function saveFormState() {
            try {
                const seedEl = document.getElementById("seedInput");
                const modeEl = document.getElementById("modeSelect");
                const regEl = document.getElementById("regionSelect");
                const locEl = document.getElementById("locationsInput");
                const negEl = document.getElementById("negativesInput");
                if (seedEl) localStorage.setItem("kwr_seed", seedEl.value);
                if (modeEl) localStorage.setItem("kwr_mode", modeEl.value);
                if (regEl) localStorage.setItem("kwr_region", regEl.value);
                if (locEl) localStorage.setItem("kwr_locations", locEl.value);
                if (negEl) localStorage.setItem("kwr_negatives", negEl.value);
            } catch (e) {}
        }

        function restoreFormState() {
            try {
                const seedEl = document.getElementById("seedInput");
                const modeEl = document.getElementById("modeSelect");
                const regEl = document.getElementById("regionSelect");
                const locEl = document.getElementById("locationsInput");
                const negEl = document.getElementById("negativesInput");
                const savedSeed = localStorage.getItem("kwr_seed");
                const savedMode = localStorage.getItem("kwr_mode");
                const savedReg = localStorage.getItem("kwr_region");
                const savedLoc = localStorage.getItem("kwr_locations");
                const savedNeg = localStorage.getItem("kwr_negatives");
                if (seedEl && savedSeed !== null) seedEl.value = savedSeed;
                if (modeEl && savedMode) modeEl.value = savedMode;
                if (regEl && savedReg) regEl.value = savedReg;
                if (locEl && savedLoc !== null) locEl.value = savedLoc;
                if (negEl && savedNeg !== null) negEl.value = savedNeg;

                ["seedInput", "locationsInput", "negativesInput"].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.addEventListener("input", saveFormState);
                });
                ["modeSelect", "regionSelect"].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.addEventListener("change", saveFormState);
                });
            } catch (e) {}
        }

        async function switchSheet(sheetName) {
            saveFormState();
            const res = await fetch("/api/switch_sheet", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sheet_name: sheetName })
            });
            const data = await res.json();
            if (data.success) {
                location.reload();
            }
        }

        async function promptNewSheet() {
            const name = prompt("Enter new sheet name:");
            if (!name) return;
            saveFormState();
            const res = await fetch("/api/create_sheet", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sheet_name: name })
            });
            const data = await res.json();
            if (data.success) {
                location.reload();
            } else {
                alert(data.message || "Could not create sheet.");
            }
        }

        function showToast(msg) {
            const t = document.getElementById("toast");
            if (!t) return;
            t.innerText = msg;
            t.style.display = "block";
            setTimeout(() => { t.style.display = "none"; }, 2200);
        }

        function fallbackCopyText(text, toastMsg) {
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.style.position = "fixed";
            ta.style.opacity = "0";
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try {
                document.execCommand("copy");
                showToast(toastMsg);
            } catch (e) {
                alert("Could not copy to clipboard.");
            }
            document.body.removeChild(ta);
        }

        function copyVisibleKeywords() {
            let targetKws = [];
            let isSelectedMode = false;
            if (selectedKeywords.size > 0) {
                targetKws = Array.from(selectedKeywords);
                isSelectedMode = true;
            } else {
                targetKws = filteredKeywords.map(k => k.keyword);
            }
            if (!targetKws.length) {
                showToast("No keywords to copy");
                return;
            }
            const label = isSelectedMode 
                ? `Copied ${targetKws.length} selected keyword${targetKws.length > 1 ? 's' : ''}`
                : `Copied ${targetKws.length} keyword${targetKws.length > 1 ? 's' : ''}`;
            
            const text = targetKws.join("\n");
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => showToast(label)).catch(() => fallbackCopyText(text, label));
            } else {
                fallbackCopyText(text, label);
            }
        }

        async function deleteSelected() {
            if (selectedKeywords.size === 0) {
                showToast("Select keywords using checkboxes first");
                return;
            }
            const toDelete = Array.from(selectedKeywords);
            if (!confirm(`Delete ${toDelete.length} selected keyword${toDelete.length > 1 ? 's' : ''}?`)) return;
            
            const res = await fetch("/api/delete_keywords", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keywords: toDelete })
            });
            const data = await res.json();
            if (data.success) {
                const delSet = new Set(toDelete);
                allKeywords = allKeywords.filter(k => !delSet.has(k.keyword));
                selectedKeywords.clear();
                updateStatsCounters();
                applyFilterAndSort();
                showToast(`Deleted ${toDelete.length} selected keyword${toDelete.length > 1 ? 's' : ''}`);
            } else {
                alert(data.message || "Failed to delete keywords.");
            }
        }

        async function deleteSingleKeyword(keyword) {
            if (!confirm(`Delete '${keyword}'?`)) return;
            const res = await fetch("/api/delete_keywords", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keywords: [keyword] })
            });
            const data = await res.json();
            if (data.success) {
                allKeywords = allKeywords.filter(k => k.keyword !== keyword);
                selectedKeywords.delete(keyword);
                updateStatsCounters();
                applyFilterAndSort();
                showToast("Deleted keyword");
            } else {
                alert(data.message || "Could not delete keyword.");
            }
        }

        async function toggleBookmarkRow(btn, keyword) {
            const res = await fetch("/api/toggle_bookmark", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword })
            });
            const data = await res.json();
            if (data.success) {
                const item = allKeywords.find(k => k.keyword === keyword);
                if (item) {
                    item.bookmarked = data.is_bookmarked;
                }
                if (data.is_bookmarked) {
                    showToast("Saved to bookmarks");
                } else {
                    showToast("Removed bookmark");
                }
                updateStatsCounters();
                if (currentTab === 'saved' && !data.is_bookmarked) {
                    applyFilterAndSort();
                } else {
                    const svg = btn ? btn.querySelector("svg") : null;
                    if (btn) btn.classList.toggle("active", data.is_bookmarked);
                    if (svg) svg.setAttribute("fill", data.is_bookmarked ? "currentColor" : "none");
                }
            }
        }

        async function updateRowField(selectEl, field, value, keyword) {
            await fetch("/api/update_row", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword, field, value })
            });
            const item = allKeywords.find(k => k.keyword === keyword);
            if (item) {
                if (field === 'Priority') item.priority = value;
                if (field === 'Validation Status') item.status = value;
            }
            showToast(`Updated ${field}`);
            const prioFilter = document.getElementById("filterPriority") ? document.getElementById("filterPriority").value.toLowerCase() : "all";
            const statusFilter = document.getElementById("filterStatus") ? document.getElementById("filterStatus").value.toLowerCase() : "all";
            if (prioFilter !== 'all' || statusFilter !== 'all') {
                applyFilterAndSort();
            }
        }

        function exportKeywordsCSV(event) {
            if (event) event.preventDefault();
            let targetKws = [];
            let mode = "all";
            if (selectedKeywords.size > 0) {
                targetKws = Array.from(selectedKeywords);
                mode = "selected";
            } else {
                targetKws = filteredKeywords.map(k => k.keyword);
                mode = (currentTab === "saved" ? "saved" : "all");
            }
            if (!targetKws.length) {
                showToast("No keywords to export");
                return;
            }
            const kwInput = document.getElementById("exportKeywordsInput");
            const modeInput = document.getElementById("exportModeInput");
            const form = document.getElementById("exportForm");
            if (kwInput && modeInput && form) {
                kwInput.value = JSON.stringify(targetKws);
                modeInput.value = mode;
                form.submit();
                if (mode === "selected") {
                    showToast(`Exporting ${targetKws.length} selected keyword${targetKws.length > 1 ? 's' : ''}...`);
                } else if (currentTab === "saved") {
                    showToast(`Exporting ${targetKws.length} saved keyword${targetKws.length > 1 ? 's' : ''}...`);
                } else {
                    showToast(`Exporting ${targetKws.length} keyword${targetKws.length > 1 ? 's' : ''}...`);
                }
            } else {
                window.location.href = "/export?view=" + encodeURIComponent(currentTab);
            }
        }

        async function startHarvest(e) {
            e.preventDefault();
            saveFormState();
            const seed = document.getElementById("seedInput").value.trim();
            const mode = document.getElementById("modeSelect").value;
            const regVal = document.getElementById("regionSelect").value.split(":");
            const gl = regVal[0];
            const hl = regVal[1];
            const locations = document.getElementById("locationsInput").value.split(",").map(s => s.trim()).filter(Boolean);
            const negatives = document.getElementById("negativesInput").value.split(",").map(s => s.trim()).filter(Boolean);

            document.getElementById("runBtn").disabled = true;
            document.getElementById("progressContainer").style.display = "block";
            document.getElementById("progressFill").style.width = "0%";
            document.getElementById("progressText").innerText = "Harvesting...";

            const res = await fetch("/api/harvest", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ seed, mode, locations, negatives, gl, hl })
            });
            const data = await res.json();
            if (!data.success) {
                alert(data.message);
                document.getElementById("runBtn").disabled = false;
                document.getElementById("progressContainer").style.display = "none";
                return;
            }

            if (pollTimer) clearInterval(pollTimer);
            pollTimer = setInterval(checkStatus, 700);
        }

        async function checkStatus() {
            const res = await fetch("/api/status");
            const st = await res.json();
            
            document.getElementById("progressFill").style.width = st.progress + "%";
            document.getElementById("progressText").innerText = `Harvesting: ${st.progress}%`;
            document.getElementById("currentQueryText").innerText = `Query: ${st.current_query || '-'}`;
            document.getElementById("harvestCountText").innerText = `New: ${st.added_count}`;

            if (!st.running) {
                clearInterval(pollTimer);
                document.getElementById("runBtn").disabled = false;
                showToast(`Harvest complete! Added ${st.added_count} keywords.`);
                setTimeout(() => { location.reload(); }, 1000);
            }
        }

        async function stopHarvest() {
            await fetch("/api/stop", { method: "POST" });
            document.getElementById("progressText").innerText = "Stopping...";
        }

        // Initialize dataset and view state
        document.addEventListener("DOMContentLoaded", () => {
            restoreFormState();
            initDataset();
            if (window.location.search.includes("view=saved") || window.location.pathname.includes("saved")) {
                setViewTab('saved');
            } else {
                applyFilterAndSort();
            }
        });
    </script>
</body>
</html>
"""

# ==================== FIELD MANUAL (HOW TO USE) ====================

GUIDE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Field Manual: Google Autocomplete Keyword Intelligence</title>
    <style>
        body {
            background-color: #16171a;
            color: #c0c6cf;
            font-family: "Charter", "Bitstream Charter", "Georgia", "Cambria", serif;
            font-size: 18px;
            line-height: 1.65;
            margin: 0;
            padding: 40px 20px 80px 20px;
            -webkit-font-smoothing: antialiased;
        }
        .container {
            max-width: 780px;
            margin: 0 auto;
        }
        header {
            border-bottom: 2px solid #2c3038;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }
        h1 {
            font-size: 2.2rem;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 8px;
            color: #e1e5eb;
        }
        .subtitle {
            font-style: italic;
            color: #737a87;
            font-size: 1.05rem;
            margin-bottom: 12px;
        }
        .meta-nav {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 15px;
        }
        .meta-nav a {
            color: #a1c7aa;
            font-weight: bold;
            text-decoration: underline;
        }
        .toc {
            background: #1e2025;
            border: 1px solid #2c3038;
            border-left: 4px solid #3f614d;
            padding: 20px 25px;
            margin: 35px 0 45px 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            border-radius: 4px;
        }
        .toc h3 {
            margin-top: 0;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 13px;
            color: #e1e5eb;
        }
        .toc ol {
            margin: 0;
            padding-left: 20px;
        }
        .toc li {
            margin-bottom: 6px;
        }
        .toc a {
            color: #c0c6cf;
            text-decoration: none;
        }
        .toc a:hover {
            color: #e1e5eb;
            text-decoration: underline;
        }
        h2 {
            font-size: 1.5rem;
            border-bottom: 1px solid #2c3038;
            padding-bottom: 6px;
            margin-top: 45px;
            margin-bottom: 16px;
            color: #e1e5eb;
        }
        h3 {
            font-size: 1.2rem;
            margin-top: 25px;
            margin-bottom: 10px;
            color: #e1e5eb;
        }
        strong {
            color: #e1e5eb;
        }
        a {
            color: #93c5fd;
        }
        p {
            margin-bottom: 18px;
            text-align: justify;
        }
        ul, ol {
            margin-bottom: 18px;
            padding-left: 28px;
        }
        li {
            margin-bottom: 8px;
        }
        code, pre {
            font-family: Consolas, Menlo, Monaco, "Courier New", monospace;
            background: #1e2025;
            color: #e1e5eb;
            border-radius: 3px;
            font-size: 14px;
        }
        code {
            padding: 2px 6px;
            border: 1px solid #2c3038;
        }
        pre {
            padding: 14px;
            overflow-x: auto;
            border: 1px solid #2c3038;
            margin-bottom: 20px;
            line-height: 1.4;
        }
        hr {
            border: 0;
            border-top: 1px solid #2c3038;
            margin: 40px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>FIELD MANUAL</h1>
            <div class="subtitle">Tactical Keyword Mining Through Search Engine Autocomplete Algorithms</div>
            <div class="meta-nav">
                <a href="/">← Return to Command Center Dashboard</a>
            </div>
        </header>

        <div class="toc">
            <h3>Table of Contents</h3>
            <ol>
                <li><a href="#ch1">Chapter 1: What's New & Core Architecture</a></li>
                <li><a href="#ch2">Chapter 2: Multi-Word Comma-Separated Seeds (word , word , word)</a></li>
                <li><a href="#ch3">Chapter 3: Standard Discovery Modes & Advanced (algos)</a></li>
                <li><a href="#ch4">Chapter 4: Sheet Workspaces, Persistent Form State & Selection Actions</a></li>
                <li><a href="#ch5">Chapter 5: Search Intent Dissection & Long-Tail Filtering</a></li>
                <li><a href="#ch6">Chapter 6: Local Geo-Targeting & Negative Keyword Pruning</a></li>
                <li><a href="#ch7">Chapter 7: Extracting Search Volume with Google Keyword Planner</a></li>
            </ol>
        </div>

        <section id="ch1">
            <h2>Chapter 1: What's New & Core Architecture</h2>
            <p>
                <strong>KWR Command Center</strong> queries Google's live public Autocomplete JSON endpoint directly using a high-speed concurrent worker pool (<code>ThreadPoolExecutor</code> + persistent HTTP connection pooling). It never fabricates synthetic keywords—every phrase stored in your sheet is an authentic search query actively typed by real Google users, verified by token-boundary matching.
            </p>
            <h3>Latest Platform Updates</h3>
            <ul>
                <li><strong>Multi-Word Comma-Separated Seed Harvesting:</strong> Enter multiple seeds separated by commas (e.g., <code>seo audit , technical seo , local seo</code>) in a single run. Each seed is expanded independently and verified for real relevance.</li>
                <li><strong>6 Advanced <code>(algos)</code> Discovery Engines:</strong> Added <em>Multi-Word Smart Scan (algos)</em>, <em>Recursive Snowball Graph (algos)</em>, <em>Wildcard &amp; Gap Fill (algos)</em>, <em>Semantic &amp; Buyer Matrix (algos)</em>, <em>Answer &amp; Question Miner (algos)</em>, and <em>Ultra Deep All-In-One (algos)</em> directly in the Expansion Mode selector.</li>
                <li><strong>Persistent Seed &amp; Form Inputs:</strong> Your entered Seed Keyword, Mode, Country/Region, Locations, and Negative words are automatically saved across sheet switches and Harvest reloads so your input is never lost.</li>
                <li><strong>Selection-Aware Copy, Delete &amp; Export CSV:</strong> Select specific rows with checkboxes to Copy, Delete, or Export only those rows—or leave checkboxes unchecked to act on your currently visible tab (<code>Keywords</code> or <code>Saved</code>).</li>
                <li><strong>60fps Large-Table Rendering:</strong> In-memory row caching, <code>DocumentFragment</code> batch sorting, and CSS <code>content-visibility: auto</code> allow instant filtering and sorting even with thousands of rows.</li>
            </ul>
        </section>

        <hr>

        <section id="ch2">
            <h2>Chapter 2: Multi-Word Comma-Separated Seeds (word , word , word)</h2>
            <p>
                You can research a single seed phrase or batch-harvest multiple independent seeds in one click by separating each word or phrase with a comma (<code>,</code>) inside the <strong>Enter Seed Keyword</strong> box:
            </p>
            <pre>
cloud hosting , dedicated server , vps pricing , managed kubernetes
            </pre>
            <p>
                <strong>How Independent Multi-Seed Harvesting Works:</strong>
            </p>
            <ol>
                <li><strong>Clean Tokenization &amp; Deduplication:</strong> The engine splits your input on commas, trims extra spaces, and removes duplicate seeds while preserving order.</li>
                <li><strong>Independent Query Matrix per Seed:</strong> Every individual seed runs through your selected expansion mode independently, tagged with its own parent seed name in the table.</li>
                <li><strong>Pairwise Cross-Seed Probes:</strong> When 2 or more seeds are provided, the engine also tests natural 2-seed combinations to uncover real multi-concept queries that users actually type into Google.</li>
                <li><strong>Strict Word-Stem Verification:</strong> Every returned Google Autocomplete suggestion is verified against your seed tokens before saving, guaranteeing high-signal results with zero unrelated noise.</li>
            </ol>
        </section>

        <hr>

        <section id="ch3">
            <h2>Chapter 3: Standard Discovery Modes & Advanced (algos)</h2>
            <p>
                Below the seed input box, the <strong>Expansion Mode</strong> dropdown provides both classic autocomplete sweeps and 6 deep-mining <code>(algos)</code> engines:
            </p>
            <h3>Standard Expansion Modes</h3>
            <ul>
                <li><strong>Standard (A-Z + Intent):</strong> Balanced sweep combining alphabet suffixes (<code>seed a-z</code>), high-intent commercial modifiers, and question stems.</li>
                <li><strong>A-Z Suffix Only (seed a-z):</strong> Appends every letter <code>a</code> through <code>z</code> after your seed to uncover specifications, sub-types, and categories.</li>
                <li><strong>A-Z Prefix Only (a-z seed):</strong> Places every letter <code>a</code> through <code>z</code> before your seed to uncover adjectives and leading qualifiers.</li>
                <li><strong>Questions Only (who, what, how...):</strong> Focuses strictly on informational question queries for blog guides and FAQ schemas.</li>
                <li><strong>Commercial &amp; Buyer Intent:</strong> Queries pricing, quotes, agency/provider terms, and location modifiers.</li>
                <li><strong>Deep Scan (All Combinations):</strong> Combines all standard modes with numeric expansions (<code>0-9</code>).</li>
            </ul>

            <h3>Advanced Discovery Algorithms — <code>(algos)</code></h3>
            <ul>
                <li><strong>Multi-Word Smart Scan (algos):</strong> Optimized for comma-separated seeds; runs base + high-intent modifiers + A–Z suffixes + question prefixes + cross-seed combinations.</li>
                <li><strong>Recursive Snowball Graph (algos):</strong> 2-hop Breadth-First Search (BFS) across Google's live suggestion graph. Harvests Layer-1 autocomplete suggestions and automatically re-queries the top discovered phrases to uncover deep Layer-2 long-tail keywords.</li>
                <li><strong>Wildcard &amp; Gap Fill (algos):</strong> Injects internal gap probes (<code>seed * word</code>, <code>* seed</code>, <code>seed a..z lastword</code>) and natural connectors (<code>for</code>, <code>with</code>, <code>vs</code>, <code>without</code>, <code>near</code>, <code>under</code>) to find middle-of-phrase completions.</li>
                <li><strong>Semantic &amp; Buyer Matrix (algos):</strong> Exhaustive commercial, transactional, comparison, and customer-segment matrix (<code>cost</code>, <code>pricing</code>, <code>software</code>, <code>agency</code>, <code>alternatives</code>, <code>for small business</code>, <code>for enterprise</code>).</li>
                <li><strong>Answer &amp; Question Miner (algos):</strong> Deep People-Also-Ask style interrogative, problem/troubleshooting, and comparison harvester (<code>how to</code>, <code>why does</code>, <code>is it worth</code>, <code>pros and cons</code>, <code>vs</code>).</li>
                <li><strong>Ultra Deep All-In-One (algos):</strong> Maximum yield engine combining Multi-Word Smart Scan + Wildcard Gap Fill + Semantic Matrix + Question Miner + 2-Hop Recursive Snowball expansion.</li>
            </ul>
        </section>

        <hr>

        <section id="ch4">
            <h2>Chapter 4: Sheet Workspaces, Pagination & Full-Dataset Selection Actions</h2>
            <p>
                Manage large campaigns (1,000+ keywords) with zero lag using the top navigation bar, pagination controls, and selection toolbar:
            </p>
            <ul>
                <li><strong>High-Performance Pagination:</strong> Handles thousands of keywords with instant sub-millisecond page rendering. Choose between <code>50</code>, <code>100</code>, <code>250</code>, <code>500</code>, or <code>All</code> rows per page using the bottom-right selector. Navigate smoothly across pages with numbered controls and previous/next buttons.</li>
                <li><strong>Global Cross-Page Select All:</strong> Checking the master checkbox in the table header selects <em>all</em> filtered keywords across <em>all pages</em> (not just the visible page). The top count updates in real time (e.g. <code>1,250 selected · 1,250 rows</code>).</li>
                <li><strong>Selection-Aware Copy, Delete &amp; Export CSV:</strong>
                    <ul>
                        <li><strong>When checkboxes are selected:</strong> Clicking <strong>Copy</strong>, <strong>Delete</strong>, or <strong>Export CSV</strong> operates strictly on all selected keywords across all pages.</li>
                        <li><strong>When no checkboxes are selected:</strong> Clicking <strong>Copy</strong> or <strong>Export CSV</strong> exports all currently filtered rows in your active tab (e.g., all bookmarked rows when viewing the <strong>Saved</strong> tab, or all filtered rows in the <strong>Keywords</strong> tab).</li>
                    </ul>
                </li>
                <li><strong>Sheet Selector &amp; New Sheet (<code>+</code>):</strong> Switch between CSV sheets at the top-left or click <code>+</code> to create a dedicated workspace for a new client or niche.</li>
                <li><strong>Persistent Seed &amp; Settings:</strong> Switching sheets or clicking <strong>Harvest</strong> automatically preserves your entered Seed Keyword, Mode, Country, Locations, and Negative filters so you never have to retype them.</li>
            </ul>
        </section>

        <hr>

        <section id="ch5">
            <h2>Chapter 5: Multi-Dimensional Filtering & Search Intent Dissection</h2>
            <p>
                Every harvested keyword is automatically scored for <strong>Priority</strong> (High, Medium, Low), <strong>Validation Status</strong> (Target, Unverified, Discard), <strong>Word Count</strong>, and <strong>Search Intent</strong>:
            </p>
            <ul>
                <li><strong>Multi-Dimensional Filter Bar:</strong> Combine real-time instant search with <strong>Priority</strong> (High / Medium / Low), <strong>Status</strong> (Target / Unverified / Discard), <strong>Word Count</strong> (2+, 3+, 4+, 5+ words), and <strong>Date Sort</strong> (Newest / Oldest) with zero DOM thrashing.</li>
                <li><strong>Transactional Intent (High Commercial Value):</strong> Queries containing direct purchase signals such as <code>cost</code>, <code>price</code>, <code>quote</code>, <code>buy</code>, <code>service</code>, or <code>near me</code>.</li>
                <li><strong>Commercial Investigation (Comparison Stage):</strong> Queries evaluating options such as <code>best</code>, <code>top</code>, <code>reviews</code>, <code>vs</code>, or <code>alternatives</code>.</li>
                <li><strong>Informational Intent (Educational / Top of Funnel):</strong> Queries asking <code>how</code>, <code>what</code>, <code>why</code>, <code>guide</code>, or <code>tutorial</code>.</li>
            </ul>
        </section>

        <hr>

        <section id="ch6">
            <h2>Chapter 6: Local Geo-Targeting & Negative Keyword Pruning</h2>
            <p>
                Open the <strong>Advanced Filters (Locations &amp; Negative Words)</strong> drawer below the mode selector to tailor harvesting to your exact market:
            </p>
            <ul>
                <li><strong>Location Modifiers (Geo-Targeting):</strong> Enter target cities, regions, or neighborhoods separated by commas (e.g., <code>New York, Austin, Chicago, Seattle</code>). The engine pairs your seeds with each location and marks matching suggestions with <strong>Local Commercial</strong> intent.</li>
                <li><strong>Negative Keywords (Noise Blocking):</strong> Enter unwanted terms separated by commas (e.g., <code>jobs, salary, vacancy, free, pdf, course, login</code>). Any suggestion containing a negative word is automatically blocked before saving.</li>
            </ul>
        </section>

        <hr>

        <section id="ch7">
            <h2>Chapter 7: Extracting Search Volume with Google Keyword Planner</h2>
            <p>
                To pair your live Google Autocomplete keywords with historical monthly search volume and CPC bid data for free:
            </p>
            <ol>
                <li>Filter or select your target keywords in the KWR Dashboard (or switch to your curated <strong>Saved</strong> tab).</li>
                <li>Click <strong>Copy</strong> to copy the exact keyword strings to your clipboard, or click <strong>Export CSV</strong> to download the spreadsheet.</li>
                <li>Open <a href="https://ads.google.com/home/tools/keyword-planner/" target="_blank">Google Keyword Planner</a> and choose <strong>"Get search volume and forecasts"</strong>.</li>
                <li>Paste your copied keywords and click <strong>Get Started</strong> to inspect monthly search volumes, 3-month trends, and top-of-page bid estimates.</li>
            </ol>
        </section>
    </div>
</body>
</html>
"""

# ==================== BACKEND CONTROLLER ====================

def get_stats_and_data(rows):
    total_count = len(rows)
    saved_count = sum(1 for r in rows if str(r.get("Bookmarked", "0")) in ("1", "true", "True", "yes"))
    tx_count = sum(1 for r in rows if r.get("Search Intent") == "Transactional")
    comm_count = sum(1 for r in rows if r.get("Search Intent") == "Commercial")
    info_count = sum(1 for r in rows if r.get("Search Intent") == "Informational")
    
    total_words = 0
    valid_word_rows = 0
    clusters = set()
    for r in rows:
        c = r.get("Topic Cluster")
        if c:
            clusters.add(c)
        try:
            w = int(r.get("Word Count", 0))
            if w > 0:
                total_words += w
                valid_word_rows += 1
        except:
            pass

    avg_words = round(total_words / valid_word_rows, 1) if valid_word_rows > 0 else 0
    return {
        "total_count": total_count,
        "saved_count": saved_count,
        "tx_count": tx_count,
        "comm_count": comm_count,
        "info_count": info_count,
        "avg_words": avg_words,
        "clusters": sorted(list(clusters))
    }

@app.route("/", strict_slashes=False)
def index():
    active_sheet = get_active_sheet()
    rows = load_all_keywords(active_sheet)
    stats = get_stats_and_data(rows)
    available_sheets = list_available_sheets()
    rows_json = json.dumps(rows).replace("</", "<\\/")

    return render_template_string(
        DASHBOARD_HTML,
        rows=rows,
        rows_json=rows_json,
        active_sheet=active_sheet,
        available_sheets=available_sheets,
        is_saved_view=False,
        all_total_count=len(rows),
        **stats
    )

@app.route("/saved", strict_slashes=False)
def saved_view():
    active_sheet = get_active_sheet()
    all_rows = load_all_keywords(active_sheet)
    saved_rows = [r for r in all_rows if str(r.get("Bookmarked", "0")) in ("1", "true", "True", "yes")]
    stats = get_stats_and_data(all_rows)
    stats["total_count"] = len(saved_rows)
    available_sheets = list_available_sheets()
    rows_json = json.dumps(saved_rows).replace("</", "<\\/")

    return render_template_string(
        DASHBOARD_HTML,
        rows=saved_rows,
        rows_json=rows_json,
        active_sheet=active_sheet,
        available_sheets=available_sheets,
        is_saved_view=True,
        all_total_count=len(all_rows),
        **stats
    )

@app.route("/guide", strict_slashes=False)
def guide():
    return render_template_string(GUIDE_HTML)

@app.route("/api/harvest", methods=["POST"])
def api_harvest():
    data = request.get_json() or {}
    seed = data.get("seed", "").strip()
    if not seed:
        return jsonify({"success": False, "message": "Seed keyword is required."}), 400

    mode = data.get("mode", "az_suffix")
    locations = data.get("locations", [])
    negatives = data.get("negatives", [])
    gl = data.get("gl", "in")
    hl = data.get("hl", "en")

    started, msg = harvest_manager.start_job(seed, mode, locations, negatives, gl, hl)
    return jsonify({"success": started, "message": msg})

@app.route("/api/status")
def api_status():
    return jsonify(harvest_manager.get_status())

@app.route("/api/stop", methods=["POST"])
def api_stop():
    stopped = harvest_manager.stop_job()
    return jsonify({"success": stopped})

@app.route("/api/toggle_bookmark", methods=["POST"])
def api_toggle_bookmark():
    data = request.get_json() or {}
    kw = data.get("keyword")
    if not kw:
        return jsonify({"success": False, "message": "Keyword required"}), 400
    
    is_bm = toggle_bookmark_in_csv(kw)
    return jsonify({"success": True, "is_bookmarked": is_bm})

@app.route("/api/switch_sheet", methods=["POST"])
def api_switch_sheet():
    data = request.get_json() or {}
    name = data.get("sheet_name")
    if not name:
        return jsonify({"success": False, "message": "Sheet name required"}), 400
    active = set_active_sheet(name)
    return jsonify({"success": True, "active_sheet": active})

@app.route("/api/create_sheet", methods=["POST"])
def api_create_sheet():
    data = request.get_json() or {}
    name = data.get("sheet_name")
    if not name:
        return jsonify({"success": False, "message": "Sheet name required"}), 400
    created = create_new_sheet(name)
    return jsonify({"success": True, "sheet_name": created})

@app.route("/api/update_row", methods=["POST"])
def api_update_row():
    data = request.get_json() or {}
    kw = data.get("keyword")
    field = data.get("field")
    val = data.get("value")
    if not kw or not field:
        return jsonify({"success": False, "message": "Invalid request"}), 400

    ok = update_row_in_csv(kw, {field: val})
    return jsonify({"success": ok})

@app.route("/api/delete_keywords", methods=["POST"])
def api_delete_keywords():
    data = request.get_json() or {}
    kws = data.get("keywords", [])
    if not kws:
        return jsonify({"success": False, "message": "No keywords provided"}), 400

    count = delete_keywords_from_csv(kws)
    return jsonify({"success": True, "deleted": count})

@app.route("/api/sheets_status")
def api_sheets_status():
    return jsonify(get_sheets_status())

@app.route("/api/sheets_sync", methods=["POST"])
def api_sheets_sync():
    data = request.get_json() or {}
    sheet_url = data.get("sheet_id_or_url")
    creds_path = data.get("credentials_path")
    worksheet_name = data.get("worksheet_name", "Keywords")
    
    res = sync_keywords_to_sheet(sheet_url, creds_path, worksheet_name)
    return jsonify(res)

@app.route("/export", methods=["GET", "POST"])
def export_csv():
    active_sheet = get_active_sheet()
    rows = load_all_keywords(active_sheet)
    if not rows:
        return "No keywords found to export.", 404

    headers = list(rows[0].keys())
    export_rows = rows
    suffix = ""

    if request.method == "POST":
        kw_json = request.form.get("keywords_json", "")
        export_mode = request.form.get("export_mode", "all")
        if not kw_json and request.is_json:
            body = request.get_json(silent=True) or {}
            if "keywords" in body:
                kw_json = json.dumps(body["keywords"])
            export_mode = body.get("export_mode", export_mode)

        if kw_json:
            try:
                selected_kws = json.loads(kw_json)
                if isinstance(selected_kws, list):
                    row_map = {r.get("Keyword", "").strip().lower(): r for r in rows}
                    export_rows = [row_map[k.strip().lower()] for k in selected_kws if isinstance(k, str) and k.strip().lower() in row_map]
            except Exception:
                pass

        if export_mode == "selected":
            suffix = "_selected"
        elif export_mode == "saved":
            suffix = "_saved"
    else:
        view_param = request.args.get("view", "").strip().lower()
        if view_param == "saved":
            export_rows = [r for r in rows if str(r.get("Bookmarked", "0")) in ("1", "true", "True", "yes")]
            suffix = "_saved"

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(export_rows)

    clean_base = active_sheet.replace(".csv", "")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={clean_base}{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
