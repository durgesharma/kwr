import csv
import io
import json
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
                                    onclick="toggleBookmark(this)" 
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
                            <select class="table-select" onchange="updateRowField(this, 'Priority', this.value)">
                                <option value="High" {% if r.get('Priority') == 'High' %}selected{% endif %}>High</option>
                                <option value="Medium" {% if r.get('Priority') == 'Medium' or not r.get('Priority') %}selected{% endif %}>Medium</option>
                                <option value="Low" {% if r.get('Priority') == 'Low' %}selected{% endif %}>Low</option>
                            </select>
                        </td>
                        <td>
                            <select class="table-select" onchange="updateRowField(this, 'Validation Status', this.value)">
                                <option value="Unverified" {% if r.get('Validation Status') == 'Unverified' or not r.get('Validation Status') %}selected{% endif %}>Unverified</option>
                                <option value="Target" {% if r.get('Validation Status') == 'Target' %}selected{% endif %}>Target</option>
                                <option value="Discard" {% if r.get('Validation Status') == 'Discard' %}selected{% endif %}>Discard</option>
                            </select>
                        </td>
                        <td>
                            <button type="button" class="row-del-btn" onclick="deleteSingle(this)" title="Delete keyword">×</button>
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
        let rowItems = [];
        let rowMapByTr = new Map();
        let lastSortedOrder = 'all';

        function initRowCache() {
            const tbody = document.querySelector("#keywordsTable tbody");
            if (!tbody) return;
            const trs = tbody.querySelectorAll("tr");
            rowItems = [];
            rowMapByTr.clear();
            for (let i = 0; i < trs.length; i++) {
                const tr = trs[i];
                const cb = tr.querySelector(".row-select");
                const rawKw = cb ? cb.value : (tr.querySelector(".kw-cell span") ? tr.querySelector(".kw-cell span").textContent.trim() : "");
                const item = {
                    tr: tr,
                    cb: cb,
                    index: parseInt(tr.getAttribute("data-index") || String(i + 1), 10),
                    keyword: (tr.getAttribute("data-keyword") || rawKw.toLowerCase()),
                    rawKeyword: rawKw,
                    date: tr.getAttribute("data-date") || "",
                    words: parseInt(tr.getAttribute("data-words") || "0", 10),
                    bookmarked: tr.getAttribute("data-bookmarked") === "1",
                    visible: true
                };
                rowItems.push(item);
                rowMapByTr.set(tr, item);
            }

            tbody.addEventListener("change", (e) => {
                if (e.target && e.target.classList.contains("row-select")) {
                    const tr = e.target.closest("tr");
                    if (tr) {
                        tr.classList.toggle("row-selected", e.target.checked);
                    }
                    updateSelectionUI();
                }
            });
        }

        function updateStatsCounters() {
            const total = rowItems.length;
            let saved = 0;
            for (let i = 0; i < rowItems.length; i++) {
                if (rowItems[i].bookmarked) saved++;
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

        function updateSelectionUI() {
            let visibleCount = 0;
            let selectedCount = 0;
            for (let i = 0; i < rowItems.length; i++) {
                const item = rowItems[i];
                if (item.visible) {
                    visibleCount++;
                    if (item.cb && item.cb.checked) {
                        selectedCount++;
                    }
                }
            }
            const label = document.getElementById("rowCountLabel");
            if (label) {
                if (selectedCount > 0) {
                    label.innerHTML = `<span style="color: #93c5fd; font-weight: 600;">${selectedCount} selected</span> · ${visibleCount} rows`;
                } else {
                    label.textContent = `${visibleCount} rows`;
                }
            }
            const selectAll = document.getElementById("selectAll");
            if (selectAll) {
                selectAll.checked = (visibleCount > 0 && selectedCount === visibleCount);
                selectAll.indeterminate = (selectedCount > 0 && selectedCount < visibleCount);
            }
        }

        function getSelectedVisibleItems() {
            const selected = [];
            for (let i = 0; i < rowItems.length; i++) {
                const item = rowItems[i];
                if (item.visible && item.cb && item.cb.checked) {
                    selected.push(item);
                }
            }
            return selected;
        }

        function getVisibleItems() {
            const visible = [];
            for (let i = 0; i < rowItems.length; i++) {
                if (rowItems[i].visible) {
                    visible.push(rowItems[i]);
                }
            }
            return visible;
        }

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

        async function toggleBookmark(btnOrKw, maybeBtn) {
            const btn = maybeBtn || btnOrKw;
            const tr = btn ? btn.closest("tr") : null;
            const item = tr ? rowMapByTr.get(tr) : null;
            const keyword = (typeof btnOrKw === "string") ? btnOrKw : (item ? item.rawKeyword : "");
            if (!keyword) return;

            const res = await fetch("/api/toggle_bookmark", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword })
            });
            const data = await res.json();
            if (data.success) {
                const svg = btn ? btn.querySelector("svg") : null;
                if (data.is_bookmarked) {
                    if (btn) btn.classList.add("active");
                    if (svg) svg.setAttribute("fill", "currentColor");
                    if (tr) tr.setAttribute("data-bookmarked", "1");
                    if (item) item.bookmarked = true;
                    showToast("Saved to bookmarks");
                } else {
                    if (btn) btn.classList.remove("active");
                    if (svg) svg.setAttribute("fill", "none");
                    if (tr) tr.setAttribute("data-bookmarked", "0");
                    if (item) item.bookmarked = false;
                    showToast("Removed bookmark");
                    if (currentTab === 'saved' && item) {
                        item.visible = false;
                        item.tr.style.display = "none";
                        if (item.cb && item.cb.checked) {
                            item.cb.checked = false;
                            item.tr.classList.remove("row-selected");
                        }
                    }
                }
                updateStatsCounters();
                updateSelectionUI();
            }
        }

        function triggerFilterLoading() {
            const loader = document.getElementById("searchLoading");
            loader.style.display = "inline";
            if (filterDebounce) clearTimeout(filterDebounce);
            filterDebounce = setTimeout(() => {
                applyFilterAndSort();
                loader.style.display = "none";
            }, 40);
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

        async function updateRowField(elOrKw, field, value) {
            let keyword = elOrKw;
            if (typeof elOrKw !== "string" && elOrKw && elOrKw.closest) {
                const tr = elOrKw.closest("tr");
                const item = rowMapByTr.get(tr);
                keyword = item ? item.rawKeyword : "";
            }
            if (!keyword) return;
            await fetch("/api/update_row", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword, field, value })
            });
            showToast(`Updated ${field}`);
        }

        async function deleteSingle(btnOrKeyword) {
            let item = null;
            if (typeof btnOrKeyword === "string") {
                item = rowItems.find(r => r.rawKeyword === btnOrKeyword);
            } else if (btnOrKeyword && btnOrKeyword.closest) {
                const tr = btnOrKeyword.closest("tr");
                item = rowMapByTr.get(tr);
            }
            if (!item) return;

            if (!confirm(`Delete '${item.rawKeyword}'?`)) return;
            const res = await fetch("/api/delete_keywords", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keywords: [item.rawKeyword] })
            });
            const data = await res.json();
            if (data.success) {
                item.tr.remove();
                rowMapByTr.delete(item.tr);
                rowItems = rowItems.filter(r => r !== item);
                updateStatsCounters();
                updateSelectionUI();
                showToast("Deleted keyword");
            }
        }

        async function deleteSelected() {
            const selected = getSelectedVisibleItems();
            if (!selected.length) {
                showToast("Select keywords using checkboxes first");
                return;
            }
            if (!confirm(`Delete ${selected.length} selected keyword${selected.length > 1 ? 's' : ''}?`)) return;
            const kwsToDelete = selected.map(item => item.rawKeyword);
            const res = await fetch("/api/delete_keywords", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keywords: kwsToDelete })
            });
            const data = await res.json();
            if (data.success) {
                const selectedSet = new Set(selected);
                for (let i = 0; i < selected.length; i++) {
                    selected[i].tr.remove();
                    rowMapByTr.delete(selected[i].tr);
                }
                rowItems = rowItems.filter(r => !selectedSet.has(r));
                updateStatsCounters();
                updateSelectionUI();
                showToast(`Deleted ${selected.length} selected keyword${selected.length > 1 ? 's' : ''}`);
            }
        }

        function toggleSelectAll(master) {
            for (let i = 0; i < rowItems.length; i++) {
                const item = rowItems[i];
                if (item.visible && item.cb) {
                    item.cb.checked = master.checked;
                    item.tr.classList.toggle("row-selected", master.checked);
                }
            }
            updateSelectionUI();
        }

        function applyFilterAndSort(forceSort = false) {
            const query = (document.getElementById("tableFilter").value || "").trim().toLowerCase();
            const dateOrder = document.getElementById("filterDateOrder") ? document.getElementById("filterDateOrder").value : "all";
            const minWords = parseInt(document.getElementById("filterWords").value, 10) || 0;
            const onlySaved = (currentTab === 'saved');
            const tbody = document.querySelector("#keywordsTable tbody");
            if (!tbody) return;

            if (forceSort || dateOrder !== lastSortedOrder) {
                if (dateOrder === "asc") {
                    rowItems.sort((a, b) => a.date.localeCompare(b.date) || (a.index - b.index));
                } else if (dateOrder === "desc") {
                    rowItems.sort((a, b) => b.date.localeCompare(a.date) || (a.index - b.index));
                } else {
                    rowItems.sort((a, b) => a.index - b.index);
                }
                const frag = document.createDocumentFragment();
                for (let i = 0; i < rowItems.length; i++) {
                    frag.appendChild(rowItems[i].tr);
                }
                tbody.appendChild(frag);
                lastSortedOrder = dateOrder;
            }

            for (let i = 0; i < rowItems.length; i++) {
                const item = rowItems[i];
                const matchQ = !query || item.keyword.includes(query);
                const matchWords = minWords === 0 || item.words >= minWords;
                const matchSaved = !onlySaved || item.bookmarked;
                const shouldShow = matchQ && matchWords && matchSaved;

                if (item.visible !== shouldShow) {
                    item.visible = shouldShow;
                    item.tr.style.display = shouldShow ? "" : "none";
                }
                if (!shouldShow && item.cb && item.cb.checked) {
                    item.cb.checked = false;
                    item.tr.classList.remove("row-selected");
                }
            }

            const arrow = document.getElementById("dateSortArrow");
            if (arrow) {
                if (dateOrder === "asc") arrow.textContent = "↑";
                else if (dateOrder === "desc") arrow.textContent = "↓";
                else arrow.textContent = "↕";
            }

            updateSelectionUI();
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
            const selected = getSelectedVisibleItems();
            const targetItems = selected.length > 0 ? selected : getVisibleItems();
            const kws = targetItems.map(item => item.rawKeyword).filter(Boolean);

            if (!kws.length) {
                showToast("No keywords to copy");
                return;
            }

            const label = selected.length > 0
                ? `Copied ${kws.length} selected keyword${kws.length > 1 ? 's' : ''}`
                : (currentTab === 'saved' ? `Copied ${kws.length} saved keyword${kws.length > 1 ? 's' : ''}` : `Copied ${kws.length} keyword${kws.length > 1 ? 's' : ''}`);

            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(kws.join("\\n")).then(() => {
                    showToast(label);
                }).catch(() => {
                    fallbackCopyText(kws.join("\\n"), label);
                });
            } else {
                fallbackCopyText(kws.join("\\n"), label);
            }
        }

        function exportKeywordsCSV(event) {
            if (event) event.preventDefault();
            const selected = getSelectedVisibleItems();
            const targetItems = selected.length > 0 ? selected : getVisibleItems();

            if (!targetItems.length) {
                showToast("No keywords to export");
                return;
            }

            const kws = targetItems.map(item => item.rawKeyword);
            const mode = selected.length > 0 ? "selected" : (currentTab === "saved" ? "saved" : "all");

            const kwInput = document.getElementById("exportKeywordsInput");
            const modeInput = document.getElementById("exportModeInput");
            const form = document.getElementById("exportForm");
            if (kwInput && modeInput && form) {
                kwInput.value = JSON.stringify(kws);
                modeInput.value = mode;
                form.submit();
                if (selected.length > 0) {
                    showToast(`Exporting ${kws.length} selected keyword${kws.length > 1 ? 's' : ''}...`);
                } else if (currentTab === "saved") {
                    showToast(`Exporting ${kws.length} saved keyword${kws.length > 1 ? 's' : ''}...`);
                } else {
                    showToast(`Exporting ${kws.length} keyword${kws.length > 1 ? 's' : ''}...`);
                }
            } else {
                window.location.href = "/export?view=" + encodeURIComponent(currentTab);
            }
        }

        // Initialize row cache and view state
        document.addEventListener("DOMContentLoaded", () => {
            restoreFormState();
            initRowCache();
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
            <h2>Chapter 4: Sheet Workspaces, Persistent Form State & Selection Actions</h2>
            <p>
                Manage multiple campaigns cleanly using the top navigation bar and selection toolbar:
            </p>
            <ul>
                <li><strong>Sheet Selector &amp; New Sheet (<code>+</code>):</strong> Switch between CSV sheets at the top-left or click <code>+</code> to create a dedicated workspace for a new client or niche.</li>
                <li><strong>Persistent Seed &amp; Settings:</strong> Switching sheets or clicking <strong>Harvest</strong> automatically preserves your entered Seed Keyword, Mode, Country, Locations, and Negative filters so you never have to retype them.</li>
                <li><strong>Keywords vs. Saved Tabs:</strong> Click the <strong>Bookmark ribbon</strong> on any row to save top keywords. Switch between the <strong>Keywords</strong> tab and the <strong>Saved</strong> tab at any time.</li>
                <li><strong>Selection-Aware Copy, Delete &amp; Export CSV:</strong>
                    <ul>
                        <li><strong>When checkboxes are selected:</strong> Clicking <strong>Copy</strong>, <strong>Delete</strong>, or <strong>Export CSV</strong> operates <em>strictly</em> on the checked rows.</li>
                        <li><strong>When no checkboxes are selected:</strong> Clicking <strong>Copy</strong> or <strong>Export CSV</strong> exports all currently visible rows in your active tab (e.g., only your bookmarked rows when viewing the <strong>Saved</strong> tab, or filtered rows in the <strong>Keywords</strong> tab).</li>
                    </ul>
                </li>
            </ul>
        </section>

        <hr>

        <section id="ch5">
            <h2>Chapter 5: Search Intent Dissection & Long-Tail Filtering</h2>
            <p>
                Every harvested keyword is automatically scored for <strong>Priority</strong> (High, Medium, Low), <strong>Word Count</strong>, and <strong>Search Intent</strong>:
            </p>
            <ul>
                <li><strong>Transactional Intent (High Commercial Value):</strong> Queries containing direct purchase or hiring signals such as <code>cost</code>, <code>price</code>, <code>quote</code>, <code>buy</code>, <code>service</code>, <code>agency</code>, or <code>near me</code>. Target these on service and landing pages.</li>
                <li><strong>Commercial Investigation (Comparison Stage):</strong> Queries evaluating options such as <code>best</code>, <code>top</code>, <code>reviews</code>, <code>vs</code>, or <code>alternatives</code>. Target these on comparison pages and case studies.</li>
                <li><strong>Informational Intent (Educational / Top of Funnel):</strong> Queries asking <code>how</code>, <code>what</code>, <code>why</code>, <code>guide</code>, or <code>tutorial</code>. Target these with blog posts and documentation.</li>
            </ul>
            <p>
                Use the filter bar to isolate <strong>High Priority</strong> phrases, filter by <strong>3+ or 4+ Words</strong> for low-competition long-tail gems, or sort by <strong>Date: Newest / Oldest</strong> to inspect your latest harvest batch.
            </p>
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
    app.run(host="127.0.0.1", port=5000, debug=False)
