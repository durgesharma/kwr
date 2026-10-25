import csv
import io
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, Response, redirect, url_for
from engine import (
    load_all_keywords, execute_harvest, update_row_in_csv, 
    delete_keywords_from_csv, init_csv, get_active_sheet, 
    set_active_sheet, list_available_sheets, create_new_sheet, 
    toggle_bookmark_in_csv, COLUMNS
)
from sheets_sync import get_sheets_status, sync_keywords_to_sheet, save_sheets_config

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
            flex-wrap: wrap;
            gap: 10px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 14px;
        }
        .topbar-left {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .logo {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-strong);
            letter-spacing: -0.3px;
        }
        .sheet-control {
            display: flex;
            align-items: center;
            gap: 6px;
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
        }
        .sheet-control select {
            background: transparent;
            border: none;
            color: var(--text-strong);
            font-weight: 600;
            outline: none;
            cursor: pointer;
            font-size: 12px;
            max-width: 170px;
        }
        .sheet-control select option { background: var(--surface); color: var(--text); }
        .btn-text {
            background: none;
            border: none;
            color: var(--text-dim);
            cursor: pointer;
            font-size: 13px;
            font-weight: bold;
            padding: 0 4px;
        }
        .btn-text:hover { color: var(--text-strong); }

        .topbar-main {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .topbar-tabs {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .desktop-help { display: inline-flex; }
        .mobile-help { display: none; }

        /* Box-matching Question Mark Button */
        .help-btn {
            height: 28px;
            min-width: 28px;
            padding: 0 8px;
            border-radius: 4px;
            border: 1px solid var(--border);
            background: var(--surface);
            color: var(--text-dim);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 700;
            text-decoration: none;
            flex-shrink: 0;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .help-btn:hover {
            background: var(--surface-hover);
            color: var(--text-strong);
            border-color: #4a5463;
        }
        .nav-tab {
            text-decoration: none;
            color: var(--text-dim);
            padding: 5px 10px;
            border-radius: 4px;
            border: 1px solid var(--border);
            background: var(--surface);
            font-size: 12px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }
        .nav-tab:hover { background: var(--surface-hover); color: var(--text-strong); }
        .nav-tab.active { border-color: #4a5463; color: var(--text-strong); background: #23272f; }
        .nav-tab.saved-active { border-color: var(--star); color: var(--star); background: #24221c; }

        /* Stats Strip */
        .stats-strip {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            max-width: 320px;
            gap: 8px;
            margin-bottom: 14px;
        }
        .stat-box {
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 8px 10px;
            border-radius: 4px;
        }
        .stat-lbl { font-size: 10px; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.4px; }
        .stat-num { font-size: 16px; font-weight: 700; color: var(--text-strong); margin-top: 2px; }

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
        }
        .filter-controls-left select {
            width: auto;
            min-width: 105px;
        }
        .actions-right {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .row-count-badge {
            font-size: 11px;
            color: var(--text-dim);
            margin-left: 2px;
            white-space: nowrap;
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
            .desktop-help { display: none !important; }
            .mobile-help { display: inline-flex !important; }

            .topbar {
                flex-direction: column;
                align-items: stretch;
                gap: 6px;
                padding-bottom: 8px;
                margin-bottom: 8px;
            }
            .topbar-main {
                width: 100%;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 4px;
            }
            .topbar-left {
                display: flex;
                align-items: center;
                gap: 5px;
                min-width: 0;
            }
            .sheet-control {
                padding: 3px 6px;
                gap: 3px;
            }
            .sheet-control select {
                max-width: 120px;
                font-size: 11px;
            }
            .help-btn {
                height: 26px;
                min-width: 26px;
                padding: 0 6px;
                font-size: 12px;
            }
            .topbar-tabs {
                width: 100%;
                display: flex;
                justify-content: flex-start;
                gap: 4px;
            }
            .nav-tab {
                padding: 4px 8px;
                font-size: 11px;
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
                flex-shrink: 0;
            }
            .filter-controls-left select {
                font-size: 11px;
                padding: 3px 5px;
                min-width: 80px;
                max-width: 95px;
                height: 29px;
            }
            .actions-right {
                display: flex;
                align-items: center;
                gap: 4px;
                flex-shrink: 0;
            }
            .actions-right .btn {
                height: 29px;
                padding: 2px 7px;
                font-size: 11px;
            }
            .row-count-badge {
                font-size: 10px;
                color: var(--text-dim);
                white-space: nowrap;
            }
            .stats-strip { grid-template-columns: repeat(2, 1fr); gap: 6px; margin-bottom: 8px; }
        }
    </style>
</head>
<body>

    <!-- TOP BAR -->
    <div class="topbar">
        <div class="topbar-main">
            <div class="topbar-left">
                <span class="logo">KWR</span>
                
                <!-- Quick inline sheet switcher -->
                <div class="sheet-control">
                    <svg class="icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <select id="sheetSelect" onchange="switchSheet(this.value)">
                        {% for s in available_sheets %}
                        <option value="{{ s }}" {% if s == active_sheet %}selected{% endif %}>{{ s }}</option>
                        {% endfor %}
                    </select>
                    <button class="btn-text" onclick="promptNewSheet()" title="Create new sheet on device">+</button>
                </div>
            </div>

            <!-- On phone: Question mark box button sits in top header row with KWR and sheet switcher -->
            <a href="/guide" target="_blank" class="help-btn mobile-help" title="How to use manual">?</a>
        </div>

        <div class="topbar-tabs">
            <button type="button" class="nav-tab active" id="tabAll" onclick="setViewTab('all')">All (<span id="countAll">{{ all_total_count }}</span>)</button>
            <button type="button" class="nav-tab" id="tabSaved" onclick="setViewTab('saved')">
                <svg class="icon" viewBox="0 0 24 24" width="12" height="12" fill="currentColor" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                Saved (<span id="countSaved">{{ saved_count }}</span>)
            </button>
            <a href="/export" class="nav-tab" title="Download CSV"><svg class="icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> CSV</a>
            <!-- On bigger devices: Question mark box button sits at end of tabs row -->
            <a href="/guide" target="_blank" class="help-btn desktop-help" title="How to use manual">?</a>
        </div>
    </div>

    <!-- STATS STRIP -->
    <div class="stats-strip">
        <div class="stat-box">
            <div class="stat-lbl">Keywords</div>
            <div class="stat-num" id="statTotal">{{ total_count }}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">Saved</div>
            <div class="stat-num" style="color: var(--star);" id="statSaved">{{ saved_count }}</div>
        </div>
    </div>

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
                        <option value="all">All</option>
                        <option value="desc" selected>Date: Newest</option>
                        <option value="asc">Date: Oldest</option>
                    </select>

                    <select id="filterWords" onchange="applyFilterAndSort()">
                        <option value="0">All Words</option>
                        <option value="3">3+ Words</option>
                        <option value="4">4+ Words</option>
                        <option value="5">5+ Words</option>
                    </select>
                </div>

                <div class="actions-right">
                    <button class="btn btn-outline" style="height: 33px; font-size: 11px;" onclick="copyVisibleKeywords()" title="Copy clean list for Google Keyword Planner"><svg class="icon icon-left" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy</button>
                    <button class="btn btn-danger" style="height: 33px; font-size: 11px;" onclick="deleteSelected()"><svg class="icon icon-left" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg> Del</button>
                    <span id="rowCountLabel" class="row-count-badge">{{ total_count }} rows</span>
                </div>
            </div>
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
                        <th style="width: 24px;"></th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in rows %}
                    <tr data-index="{{ loop.index }}"
                        data-keyword="{{ r['Keyword'] | lower }}" 
                        data-date="{{ r.get('Collection Date', '') }}" 
                        data-words="{{ r.get('Word Count', '1') }}"
                        data-bookmarked="{{ r.get('Bookmarked', '0') }}">
                        <td><input type="checkbox" class="row-select" value="{{ r['Keyword'] }}"></td>
                        <td>
                            {% set is_bm = (r.get('Bookmarked') == '1' or r.get('Bookmarked') == 1) %}
                            <button type="button" class="star-btn {% if is_bm %}active{% endif %}" 
                                    onclick="toggleBookmark('{{ r['Keyword'] }}', this)" 
                                    title="Toggle save">
                                <svg class="star-icon" viewBox="0 0 24 24" width="14" height="14" fill="{% if is_bm %}currentColor{% else %}none{% endif %}" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                            </button>
                        </td>
                        <td>
                            <div class="kw-cell">
                                <span>{{ r['Keyword'] }}</span>
                                <span style="display: inline-flex; gap: 4px;">
                                    <a class="quick-link" href="https://www.google.com/search?q={{ r['Keyword'] | urlencode }}" target="_blank">serp</a>
                                    <a class="quick-link" href="https://trends.google.com/trends/explore?q={{ r['Keyword'] | urlencode }}&geo=IN" target="_blank">trends</a>
                                </span>
                            </div>
                        </td>
                        <td style="color: var(--text-dim); font-size: 11px;">{{ r.get('Collection Date', '-') }}</td>
                        <td>{{ r.get('Word Count', '-') }}</td>
                        <td>
                            <select class="table-select" onchange="updateRowField('{{ r['Keyword'] }}', 'Priority', this.value)">
                                <option value="High" {% if r.get('Priority') == 'High' %}selected{% endif %}>High</option>
                                <option value="Medium" {% if r.get('Priority') == 'Medium' or not r.get('Priority') %}selected{% endif %}>Medium</option>
                                <option value="Low" {% if r.get('Priority') == 'Low' %}selected{% endif %}>Low</option>
                            </select>
                        </td>
                        <td>
                            <select class="table-select" onchange="updateRowField('{{ r['Keyword'] }}', 'Validation Status', this.value)">
                                <option value="Unverified" {% if r.get('Validation Status') == 'Unverified' or not r.get('Validation Status') %}selected{% endif %}>Unverified</option>
                                <option value="Target" {% if r.get('Validation Status') == 'Target' %}selected{% endif %}>Target</option>
                                <option value="Discard" {% if r.get('Validation Status') == 'Discard' %}selected{% endif %}>Discard</option>
                            </select>
                        </td>
                        <td>
                            <button class="btn-text" style="color: #ef4444;" onclick="deleteSingle('{{ r['Keyword'] }}')">×</button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <div id="toast">Copied to clipboard</div>

    <script>
        let pollTimer = null;
        let filterDebounce = null;
        let currentTab = 'all';

        function showToast(msg) {
            const t = document.getElementById("toast");
            t.innerText = msg;
            t.style.display = "block";
            setTimeout(() => { t.style.display = "none"; }, 2200);
        }

        function toggleOptions() {
            const el = document.getElementById("harvestOptions");
            el.style.display = (el.style.display === "grid") ? "none" : "grid";
        }

        function toggleDateSort() {
            const sel = document.getElementById("filterDateOrder");
            if (!sel) return;
            if (sel.value === "desc") sel.value = "asc";
            else if (sel.value === "asc") sel.value = "all";
            else sel.value = "desc";
            applyFilterAndSort();
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
            applyFilterAndSort();
        }

        async function switchSheet(sheetName) {
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

        async function toggleBookmark(keyword, btn) {
            const tr = btn.closest("tr");
            const res = await fetch("/api/toggle_bookmark", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword })
            });
            const data = await res.json();
            if (data.success) {
                const svg = btn.querySelector("svg");
                const countSavedEl = document.getElementById("countSaved");
                let savedCount = countSavedEl ? (parseInt(countSavedEl.innerText, 10) || 0) : 0;

                if (data.is_bookmarked) {
                    btn.classList.add("active");
                    if (svg) svg.setAttribute("fill", "currentColor");
                    if (tr) tr.setAttribute("data-bookmarked", "1");
                    savedCount++;
                    showToast("Saved to bookmarks");
                } else {
                    btn.classList.remove("active");
                    if (svg) svg.setAttribute("fill", "none");
                    if (tr) tr.setAttribute("data-bookmarked", "0");
                    savedCount = Math.max(0, savedCount - 1);
                    showToast("Removed bookmark");
                    if (currentTab === 'saved' && tr) {
                        tr.style.display = "none";
                    }
                }
                if (countSavedEl) countSavedEl.innerText = savedCount;
                const statSaved = document.getElementById("statSaved");
                if (statSaved) statSaved.innerText = savedCount;
            }
        }

        function triggerFilterLoading() {
            const loader = document.getElementById("searchLoading");
            loader.style.display = "inline";
            if (filterDebounce) clearTimeout(filterDebounce);
            filterDebounce = setTimeout(() => {
                applyFilterAndSort();
                loader.style.display = "none";
            }, 60);
        }

        async function startHarvest(e) {
            e.preventDefault();
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

        async function updateRowField(keyword, field, value) {
            await fetch("/api/update_row", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword, field, value })
            });
            showToast(`Updated ${field}`);
        }

        async function deleteSingle(keyword) {
            if (!confirm(`Delete '${keyword}'?`)) return;
            await fetch("/api/delete_keywords", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keywords: [keyword] })
            });
            location.reload();
        }

        async function deleteSelected() {
            const checked = Array.from(document.querySelectorAll(".row-select:checked")).map(cb => cb.value);
            if (!checked.length) {
                alert("No keywords selected.");
                return;
            }
            if (!confirm(`Delete ${checked.length} selected keywords?`)) return;
            await fetch("/api/delete_keywords", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keywords: checked })
            });
            location.reload();
        }

        function toggleSelectAll(master) {
            const cbs = document.querySelectorAll(".row-select");
            cbs.forEach(cb => {
                if (cb.closest("tr").style.display !== "none") {
                    cb.checked = master.checked;
                }
            });
        }

        function applyFilterAndSort() {
            const query = document.getElementById("tableFilter").value.toLowerCase();
            const dateOrder = document.getElementById("filterDateOrder") ? document.getElementById("filterDateOrder").value : "all";
            const minWords = parseInt(document.getElementById("filterWords").value, 10);
            const onlySaved = (currentTab === 'saved');

            const tbody = document.querySelector("#keywordsTable tbody");
            const rows = Array.from(tbody.querySelectorAll("tr"));
            let visibleCount = 0;

            rows.forEach(tr => {
                const kw = tr.getAttribute("data-keyword") || "";
                const words = parseInt(tr.getAttribute("data-words") || "0", 10);
                const isBookmarked = tr.getAttribute("data-bookmarked") === "1";

                const matchQ = !query || kw.includes(query);
                const matchWords = isNaN(minWords) || minWords === 0 || words >= minWords;
                const matchSaved = !onlySaved || isBookmarked;

                if (matchQ && matchWords && matchSaved) {
                    tr.style.display = "";
                    visibleCount++;
                } else {
                    tr.style.display = "none";
                }
            });

            // Sort rows by Date or preserve original All order
            if (dateOrder === "asc") {
                rows.sort((a, b) => {
                    const dateA = a.getAttribute("data-date") || "";
                    const dateB = b.getAttribute("data-date") || "";
                    return dateA.localeCompare(dateB);
                });
                rows.forEach(tr => tbody.appendChild(tr));
            } else if (dateOrder === "desc") {
                rows.sort((a, b) => {
                    const dateA = a.getAttribute("data-date") || "";
                    const dateB = b.getAttribute("data-date") || "";
                    return dateB.localeCompare(dateA);
                });
                rows.forEach(tr => tbody.appendChild(tr));
            } else if (dateOrder === "all") {
                rows.sort((a, b) => {
                    const idxA = parseInt(a.getAttribute("data-index") || "0", 10);
                    const idxB = parseInt(b.getAttribute("data-index") || "0", 10);
                    return idxA - idxB;
                });
                rows.forEach(tr => tbody.appendChild(tr));
            }

            const arrow = document.getElementById("dateSortArrow");
            if (arrow) {
                if (dateOrder === "asc") arrow.innerText = "↑";
                else if (dateOrder === "desc") arrow.innerText = "↓";
                else arrow.innerText = "↕";
            }

            document.getElementById("rowCountLabel").innerText = `${visibleCount} rows`;
        }

        function copyVisibleKeywords() {
            const visibleRows = document.querySelectorAll("#keywordsTable tbody tr");
            const kws = [];
            visibleRows.forEach(tr => {
                if (tr.style.display !== "none") {
                    const textNode = tr.querySelector(".kw-cell span");
                    const kwText = textNode ? textNode.innerText.trim() : "";
                    if (kwText) kws.push(kwText);
                }
            });

            if (!kws.length) {
                alert("No keywords visible to copy.");
                return;
            }

            navigator.clipboard.writeText(kws.join("\\n")).then(() => {
                showToast(`Copied ${kws.length} keywords for GKP`);
            });
        }

        // Initialize view based on URL if loaded with /saved
        document.addEventListener("DOMContentLoaded", () => {
            if (window.location.search.includes("view=saved") || window.location.pathname.includes("saved")) {
                setViewTab('saved');
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
            background-color: #fcfbf9;
            color: #1a1a1a;
            font-family: "Charter", "Bitstream Charter", "Georgia", "Cambria", serif;
            font-size: 18px;
            line-height: 1.65;
            margin: 0;
            padding: 40px 20px 80px 20px;
        }
        .container {
            max-width: 780px;
            margin: 0 auto;
        }
        header {
            border-bottom: 2px solid #1a1a1a;
            padding-bottom: 20px;
            margin-bottom: 40px;
        }
        h1 {
            font-size: 2.2rem;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 8px;
        }
        .subtitle {
            font-style: italic;
            color: #4a4a4a;
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
            color: #1a1a1a;
            font-weight: bold;
            text-decoration: underline;
        }
        .toc {
            background: #f4f1ea;
            border-left: 4px solid #1a1a1a;
            padding: 20px 25px;
            margin: 35px 0 45px 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
        }
        .toc h3 {
            margin-top: 0;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 13px;
        }
        .toc ol {
            margin: 0;
            padding-left: 20px;
        }
        .toc li {
            margin-bottom: 6px;
        }
        .toc a {
            color: #1a1a1a;
            text-decoration: none;
        }
        .toc a:hover {
            text-decoration: underline;
        }
        h2 {
            font-size: 1.5rem;
            border-bottom: 1px solid #ccc;
            padding-bottom: 6px;
            margin-top: 45px;
            margin-bottom: 16px;
        }
        h3 {
            font-size: 1.2rem;
            margin-top: 25px;
            margin-bottom: 10px;
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
            background: #eeebe3;
            border-radius: 3px;
            font-size: 14px;
        }
        code {
            padding: 2px 6px;
        }
        pre {
            padding: 14px;
            overflow-x: auto;
            border: 1px solid #dcd7cc;
            margin-bottom: 20px;
            line-height: 1.4;
        }
        hr {
            border: 0;
            border-top: 1px solid #ddd;
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
                <li><a href="#ch1">Chapter 1: The Anatomy of Google Autocomplete</a></li>
                <li><a href="#ch2">Chapter 2: The Alphabet Soup Method (A-Z Mechanics)</a></li>
                <li><a href="#ch3">Chapter 3: Search Intent Dissection (Transactional vs Informational)</a></li>
                <li><a href="#ch4">Chapter 4: Local Geo-Targeting for Trades & Execution</a></li>
                <li><a href="#ch5">Chapter 5: Long-Tail Keyword Strategy (3+ and 4+ Words)</a></li>
                <li><a href="#ch6">Chapter 6: Workflow: Extracting Search Volume with Google Keyword Planner</a></li>
                <li><a href="#ch7">Chapter 7: Negative Keyword Pruning and Clean Database Maintenance</a></li>
            </ol>
        </div>

        <section id="ch1">
            <h2>Chapter 1: The Anatomy of Google Autocomplete</h2>
            <p>
                Google Autocomplete is not a random text prediction tool. It is an algorithmic projection of aggregate search volume, recency, and user intent. When a human begins typing a phrase into Google, the algorithm evaluates millions of historical queries to predict what that person is most likely searching for next.
            </p>
            <p>
                Unlike standard third-party keyword research databases (which are often updated only once every 30 to 90 days), Google's autocomplete feed reflects <strong>actual current search habits</strong>. If a term appears in autocomplete, it guarantees that genuine users are frequently typing that exact string into search boxes.
            </p>
            <p>
                This tool interacts directly with Google's public suggestion interface. It simulates search journeys programmatically, cataloging every suggested stem before standard SEO tools report on them.
            </p>
        </section>

        <hr>

        <section id="ch2">
            <h2>Chapter 2: The Alphabet Soup Method (A-Z Mechanics)</h2>
            <p>
                The primary constraint of human keyword brainstorming is mental bias. When thinking about "modular kitchen", one usually recalls only four or five obvious phrases: "price", "designs", "materials", and "cabinets".
            </p>
            <p>
                The <strong>Alphabet Soup</strong> technique breaks this constraint by systematically querying the search engine with the seed followed by every letter of the alphabet:
            </p>
            <pre>
modular kitchen a -> acrylic, accessories, appliances, aluminium, arch...
modular kitchen b -> basket, budget, backsplash, bar counter, brands...
modular kitchen c -> cost, catalogue, corner solutions, cabinets, carpenter...
...
modular kitchen z -> zinc hinges, zero maintenance, z-profile handles...
            </pre>
            <p>
                <strong>Suffix Mode versus Prefix Mode:</strong>
            </p>
            <ul>
                <li><strong>Suffix Mode (Seed + Letter):</strong> Discovers sub-specifications, components, brands, and variations attached to your main subject. This is ideal for product catalogs, service pages, and commercial offerings.</li>
                <li><strong>Prefix Mode (Letter + Seed):</strong> Discovers descriptors, adjectives, and qualifiers placed before the seed (e.g., <em>"acrylic modular kitchen"</em>, <em>"best modular kitchen"</em>, <em>"cheap modular kitchen"</em>).</li>
            </ul>
        </section>

        <hr>

        <section id="ch3">
            <h2>Chapter 3: Search Intent Dissection</h2>
            <p>
                Not all keywords carry equal commercial value. Ranking #1 for a term that brings visitors with no budget or willingness to buy will not generate revenue. The KWR engine automatically categorizes discovered phrases into three foundational intents:
            </p>
            <h3>1. Transactional Intent (High Commercial Value)</h3>
            <p>
                The user has their credit card or cheque book ready. They are looking to hire, buy, or obtain a quote immediately. Look for indicators such as:
            </p>
            <ul>
                <li><code>cost</code>, <code>price</code>, <code>rates per sq ft</code>, <code>charges</code></li>
                <li><code>contractor</code>, <code>service</code>, <code>carpenter near me</code>, <code>agency</code></li>
                <li><code>estimate</code>, <code>quotation</code>, <code>installation</code></li>
            </ul>
            <p>
                <em>Action:</em> Target these keywords directly on Service Pages, Pricing Calculators, and Contact Landing Pages.
            </p>

            <h3>2. Commercial Investigation Intent (Comparison Stage)</h3>
            <p>
                The user knows they want the service, but is evaluating options, materials, or providers.
            </p>
            <ul>
                <li><code>best modular kitchen brands</code>, <code>acrylic vs laminate</code>, <code>reviews</code>, <code>top contractors</code></li>
            </ul>
            <p>
                <em>Action:</em> Target these keywords on Material Guides, Comparison Charts, and Portfolio Case Studies.
            </p>

            <h3>3. Informational Intent (Top of Funnel / Educational)</h3>
            <p>
                The user has a question or needs maintenance/DIY information.
            </p>
            <ul>
                <li><code>how to clean modular kitchen trolleys</code>, <code>what is standard counter height</code>, <code>why hinges rust</code></li>
            </ul>
            <p>
                <em>Action:</em> Target these keywords on Blog Articles and FAQ sections to build site authority and capture email subscribers.
            </p>
        </section>

        <hr>

        <section id="ch4">
            <h2>Chapter 4: Local Geo-Targeting for Trades & Execution</h2>
            <p>
                For local contractors, trade professionals, and regional service businesses, generic nationwide searches are wasteful. A user in Delhi searching for "carpenter" will never hire a workshop in another state or distant district.
            </p>
            <p>
                To generate high-yield local client leads:
            </p>
            <ol>
                <li>Input your micro-locations into the <strong>Location Modifiers</strong> field: <code>Navi Mumbai, Vashi, Thane, Kharghar, Panvel, Nerul, Seawoods, Ghansoli</code>.</li>
                <li>Select the <strong>Commercial & Buyer Intent</strong> expansion mode.</li>
                <li>The engine combines your trade seed with each specific node to extract actual localized search stems (e.g. <em>"modular kitchen trolley repair Vashi"</em>, <em>"wardrobe contractor near Kharghar"</em>).</li>
            </ol>
        </section>

        <hr>

        <section id="ch5">
            <h2>Chapter 5: Long-Tail Keyword Strategy (3+ and 4+ Words)</h2>
            <p>
                Single-word or two-word queries like "kitchen" or "interior designer" are fiercely competitive, dominated by directory giants (Justdial, Houzz, Livspace).
            </p>
            <p>
                Long-tail phrases composed of four, five, or six words carry three distinct advantages:
            </p>
            <ul>
                <li><strong>Near-Zero Competition:</strong> Major corporations rarely optimize dedicated landing pages for specific 5-word queries.</li>
                <li><strong>Clear, Unambiguous Intent:</strong> A user typing <em>"acrylic l shaped modular kitchen cost per square foot in Navi Mumbai"</em> knows precisely what they want.</li>
                <li><strong>Exponential Conversion Rate:</strong> Conversion rates on 4+ word targeted phrases are typically 3x to 5x higher than 1-2 word head terms.</li>
            </ul>
            <p>
                Use the <strong>"4+ Words"</strong> filter on the dashboard to immediately isolate high-leverage long-tail targets.
            </p>
        </section>

        <hr>

        <section id="ch6">
            <h2>Chapter 6: Workflow: Extracting Search Volume with Google Keyword Planner</h2>
            <p>
                Google Autocomplete reveals <em>what</em> people search, but does not provide historical monthly search volume numbers. To get exact monthly search volume figures without paying hundreds of dollars for SEO subscriptions:
            </p>
            <ol>
                <li>In the KWR Dashboard, apply your desired filters (e.g., select <em>Transactional</em> intent and <em>High</em> priority).</li>
                <li>Click the button <strong>"Copy List"</strong>. The dashboard immediately copies the exact keyword list to your operating system clipboard.</li>
                <li>Open <a href="https://ads.google.com/home/tools/keyword-planner/" target="_blank">Google Keyword Planner</a> (free with any Google Ads account).</li>
                <li>Select <strong>"Get search volume and forecasts"</strong>.</li>
                <li>Paste your copied clipboard list directly into the box and press <strong>"Get Started"</strong>.</li>
                <li>Google will return exact historical monthly searches, 3-month trends, YoY changes, and top-of-page bid estimates for every single harvested phrase.</li>
            </ol>
        </section>

        <hr>

        <section id="ch7">
            <h2>Chapter 7: Negative Keyword Pruning and Clean Database Maintenance</h2>
            <p>
                A database with 10,000 garbage keywords is useless. A database with 300 actionable, highly qualified buyer queries is a gold mine.
            </p>
            <p>
                The KWR engine includes an active negative filter. Any suggestion containing forbidden terms is blocked before it touches your CSV storage. Recommended negative tokens for contractors and services:
            </p>
            <pre>
job, jobs, salary, vacancy, vacancies, pdf, download, course, training, exam, syllabus, login, portal, app download, free, second hand, used
            </pre>
            <p>
                Regularly review the dashboard table, mark irrelevant queries with the <strong>"Discard"</strong> status or check their boxes and execute <strong>"Delete"</strong>. Keep your keyword pool lean, verified, and ready for deployment.
            </p>
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

    return render_template_string(
        DASHBOARD_HTML,
        rows=rows,
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

    return render_template_string(
        DASHBOARD_HTML,
        rows=saved_rows,
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

@app.route("/export")
def export_csv():
    active_sheet = get_active_sheet()
    rows = load_all_keywords(active_sheet)
    if not rows:
        return "No keywords found to export.", 404

    output = io.StringIO()
    headers = list(rows[0].keys())
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)

    clean_base = active_sheet.replace(".csv", "")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={clean_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
