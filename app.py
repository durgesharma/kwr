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
            --bg: #0c0e12;
            --surface: #15181f;
            --surface-hover: #1c202a;
            --border: #262b36;
            --text: #d8dee8;
            --text-dim: #7d8595;
            --blue: #3b82f6;
            --green: #22c55e;
            --yellow: #eab308;
            --red: #ef4444;
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
            font-size: 16px;
            font-weight: 800;
            color: #fff;
            letter-spacing: -0.5px;
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
            color: var(--blue);
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
        .btn-text:hover { color: #fff; }

        .topbar-right {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }
        .nav-tab {
            text-decoration: none;
            color: var(--text-dim);
            padding: 6px 11px;
            border-radius: 4px;
            border: 1px solid var(--border);
            background: var(--surface);
            font-size: 12px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }
        .nav-tab:hover { background: var(--surface-hover); color: #fff; }
        .nav-tab.active { border-color: var(--blue); color: var(--blue); }
        .nav-tab.saved-active { border-color: var(--yellow); color: var(--yellow); }

        /* Stats Strip */
        .stats-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
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
        .stat-num { font-size: 17px; font-weight: 700; color: #fff; margin-top: 2px; }

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
            background: #090a0d;
            border: 1px solid var(--border);
            color: #fff;
            padding: 9px 11px;
            font-size: 13px;
            border-radius: 4px;
            outline: none;
            width: 100%;
        }
        input[type="text"]:focus, select:focus {
            border-color: var(--blue);
        }

        button.btn {
            background: var(--blue);
            color: #fff;
            border: none;
            padding: 9px 16px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 4px;
            cursor: pointer;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            height: 37px;
        }
        button.btn:hover { filter: brightness(1.12); }
        button.btn-green { background: #15803d; }
        button.btn-green:hover { background: #16a34a; }
        button.btn-danger { background: #b91c1c; }
        button.btn-danger:hover { background: #dc2626; }
        button.btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
        button.btn-outline:hover { background: var(--surface-hover); color: #fff; }

        .options-toggle {
            font-size: 11px;
            color: var(--text-dim);
            cursor: pointer;
            margin-top: 8px;
            display: inline-block;
            user-select: none;
        }
        .options-toggle:hover { color: var(--blue); }
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
            background: #111827;
            border: 1px solid #1e3a8a;
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
            background: #1f2937;
            height: 6px;
            border-radius: 3px;
            overflow: hidden;
            margin: 8px 0;
        }
        .progress-bar-fill {
            background: var(--green);
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
        .filter-group {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
            flex: 1;
        }
        .actions-group {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
        }
        .search-wrap {
            position: relative;
            min-width: 200px;
            max-width: 280px;
            flex: 1;
        }
        .search-wrap input { padding-right: 60px; }
        .search-indicator {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 11px;
            color: var(--blue);
            display: none;
        }

        /* Table Design */
        .table-wrap {
            overflow-x: auto;
            max-height: 62vh;
            border: 1px solid var(--border);
            border-radius: 4px;
            background: #090a0d;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            text-align: left;
        }
        th, td {
            padding: 8px 10px;
            border-bottom: 1px solid #1a1e27;
            white-space: nowrap;
        }
        th {
            background: #12151c;
            color: var(--text-dim);
            font-size: 11px;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 5;
            user-select: none;
        }
        tr:hover td { background: #131720; }

        .kw-cell {
            color: #fff;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .quick-link {
            color: var(--text-dim);
            text-decoration: none;
            font-size: 10px;
            border: 1px solid #2d3340;
            padding: 1px 4px;
            border-radius: 3px;
        }
        .quick-link:hover { color: var(--blue); border-color: var(--blue); }

        /* Star Button */
        .star-btn {
            background: transparent;
            border: none;
            color: #4b5563;
            font-size: 16px;
            cursor: pointer;
            padding: 0 4px;
            line-height: 1;
        }
        .star-btn:hover { color: var(--yellow); }
        .star-btn.active { color: var(--yellow); }

        /* Subtle Badges */
        .pill {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 600;
        }
        .pill-tx { background: rgba(234, 179, 8, 0.15); color: #facc15; }
        .pill-comm { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
        .pill-info { background: rgba(34, 197, 94, 0.15); color: #4ade80; }

        select.table-select {
            background: #11141a;
            border: 1px solid #232833;
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
            background: #15803d;
            color: #fff;
            padding: 9px 15px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            display: none;
            z-index: 100;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }

        /* Responsive Mobile Tweak */
        @media (max-width: 768px) {
            body { padding: 8px; font-size: 12px; }
            .harvest-main { flex-direction: column; align-items: stretch; }
            .harvest-main input, .harvest-main select, .harvest-main button { width: 100%; }
            .filter-row { flex-direction: column; align-items: stretch; }
            .search-wrap { max-width: 100%; }
            .filter-group, .actions-group { width: 100%; justify-content: space-between; }
            .stats-strip { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>

    <!-- TOP BAR -->
    <div class="topbar">
        <div class="topbar-left">
            <span class="logo">KWR</span>
            
            <!-- Quick inline sheet switcher -->
            <div class="sheet-control">
                <span>📄</span>
                <select id="sheetSelect" onchange="switchSheet(this.value)">
                    {% for s in available_sheets %}
                    <option value="{{ s }}" {% if s == active_sheet %}selected{% endif %}>{{ s }}</option>
                    {% endfor %}
                </select>
                <button class="btn-text" onclick="promptNewSheet()" title="Create new sheet on device">+</button>
            </div>
        </div>

        <div class="topbar-right">
            {% if is_saved_view %}
                <a href="/" class="nav-tab">← All Keywords ({{ all_total_count }})</a>
                <span class="nav-tab saved-active">★ Saved ({{ saved_count }})</span>
            {% else %}
                <span class="nav-tab active">All ({{ total_count }})</span>
                <a href="/saved" class="nav-tab">★ Saved ({{ saved_count }})</a>
            {% endif %}
            
            <a href="/export" class="nav-tab" title="Download CSV">⬇ CSV</a>
            <a href="/guide" target="_blank" class="nav-tab" title="How to use manual">?</a>
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
            <div class="stat-num" style="color: var(--yellow);">{{ saved_count }}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">Transactional</div>
            <div class="stat-num" style="color: var(--yellow);">{{ tx_count }}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">Commercial</div>
            <div class="stat-num" style="color: var(--blue);">{{ comm_count }}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">Informational</div>
            <div class="stat-num" style="color: var(--green);">{{ info_count }}</div>
        </div>
    </div>

    {% if not is_saved_view %}
    <!-- HARVESTER PANEL -->
    <div class="card">
        <form id="harvestForm" onsubmit="startHarvest(event)">
            <div class="harvest-main">
                <input type="text" id="seedInput" placeholder="Enter seed keyword (e.g. modular kitchen, wardrobe)..." required>
                <select id="modeSelect">
                    <option value="az_suffix">Alphabet Soup: [Seed + A-Z] (Broad)</option>
                    <option value="az_prefix">Prefix Soup: [A-Z + Seed]</option>
                    <option value="commercial">Commercial: Cost, Price, Contractor, Near Me</option>
                    <option value="questions">Questions: How, What, Why, Which</option>
                    <option value="prepositions">Prepositions: For, With, Vs, Near</option>
                    <option value="numbers">Numbers: [Seed + 0-9] (Sizes, BHK)</option>
                    <option value="deep_harvest">🔥 Full Deep Harvest (All Modules)</option>
                    <option value="standard">Standard (Direct Suggestions)</option>
                </select>
                <button type="submit" class="btn btn-green" id="runBtn">⚡ Harvest</button>
            </div>

            <div class="options-toggle" onclick="toggleOptions()">⚙ Target Options (Region, Locations, Exclude) ▼</div>

            <div class="harvest-options" id="harvestOptions">
                <div>
                    <label class="field-lbl">Region</label>
                    <select id="regionSelect">
                        <option value="in:en" selected>India (en)</option>
                        <option value="in:hi">India (hi)</option>
                        <option value="us:en">United States (en)</option>
                        <option value="uk:en">United Kingdom (en)</option>
                        <option value="ae:en">UAE (en)</option>
                    </select>
                </div>
                <div>
                    <label class="field-lbl">Locations (comma-separated)</label>
                    <input type="text" id="locationsInput" value="Navi Mumbai, Thane" placeholder="Navi Mumbai, Thane">
                </div>
                <div>
                    <label class="field-lbl">Negative Exclusions</label>
                    <input type="text" id="negativesInput" value="job, salary, vacancy, pdf, download" placeholder="jobs, salary, pdf">
                </div>
            </div>
        </form>
    </div>
    {% endif %}

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
            <div class="filter-group">
                <div class="search-wrap">
                    <input type="text" id="tableFilter" placeholder="Filter keywords..." oninput="triggerFilterLoading()">
                    <span class="search-indicator" id="searchLoading">filtering...</span>
                </div>
                
                <select id="filterIntent" onchange="applyFilter()" style="width: 120px;">
                    <option value="">All Intents</option>
                    <option value="Transactional">Transactional</option>
                    <option value="Commercial">Commercial</option>
                    <option value="Informational">Informational</option>
                </select>

                <select id="filterCluster" onchange="applyFilter()" style="width: 140px;">
                    <option value="">All Clusters</option>
                    {% for c in clusters %}
                    <option value="{{ c }}">{{ c }}</option>
                    {% endfor %}
                </select>

                <select id="filterWords" onchange="applyFilter()" style="width: 110px;">
                    <option value="0">All Lengths</option>
                    <option value="3">3+ Words</option>
                    <option value="4">4+ Words</option>
                    <option value="5">5+ Words</option>
                </select>
            </div>

            <div class="actions-group">
                <button class="btn btn-outline" style="height: 33px; font-size: 11px;" onclick="copyVisibleKeywords()" title="Copy clean list for Google Keyword Planner">📋 Copy List</button>
                <button class="btn btn-danger" style="height: 33px; font-size: 11px;" onclick="deleteSelected()">🗑 Delete</button>
                <span id="rowCountLabel" style="font-size: 11px; color: var(--text-dim); margin-left: 4px;">{{ total_count }} rows</span>
            </div>
        </div>

        <div class="table-wrap">
            <table id="keywordsTable">
                <thead>
                    <tr>
                        <th style="width: 24px;"><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this)"></th>
                        <th style="width: 32px;" title="Bookmark">★</th>
                        <th>KEYWORD</th>
                        <th>INTENT</th>
                        <th>CLUSTER</th>
                        <th>SOURCE</th>
                        <th>WORDS</th>
                        <th>PRIORITY</th>
                        <th>STATUS</th>
                        <th style="width: 24px;"></th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in rows %}
                    <tr data-keyword="{{ r['Keyword'] | lower }}" 
                        data-intent="{{ r.get('Search Intent', 'Commercial') }}" 
                        data-cluster="{{ r.get('Topic Cluster', '') }}" 
                        data-words="{{ r.get('Word Count', '1') }}">
                        <td><input type="checkbox" class="row-select" value="{{ r['Keyword'] }}"></td>
                        <td>
                            {% set is_bm = (r.get('Bookmarked') == '1' or r.get('Bookmarked') == 1) %}
                            <button class="star-btn {% if is_bm %}active{% endif %}" 
                                    onclick="toggleBookmark('{{ r['Keyword'] }}', this)" 
                                    title="Toggle save">
                                {% if is_bm %}★{% else %}☆{% endif %}
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
                        <td>
                            {% set it = r.get('Search Intent', 'Commercial') %}
                            {% if it == 'Transactional' %}
                                <span class="pill pill-tx">Transactional</span>
                            {% elif it == 'Informational' %}
                                <span class="pill pill-info">Informational</span>
                            {% else %}
                                <span class="pill pill-comm">Commercial</span>
                            {% endif %}
                        </td>
                        <td style="color: var(--text-dim);">{{ r.get('Topic Cluster', '-') }}</td>
                        <td style="color: #64748b; font-size: 11px;">{{ r.get('Discovered From', '-') }}</td>
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
            const name = prompt("Enter new sheet name (e.g. modular_pune):");
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
            const res = await fetch("/api/toggle_bookmark", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword })
            });
            const data = await res.json();
            if (data.success) {
                if (data.is_bookmarked) {
                    btn.classList.add("active");
                    btn.innerText = "★";
                    showToast("Saved to bookmarks");
                } else {
                    btn.classList.remove("active");
                    btn.innerText = "☆";
                    showToast("Removed bookmark");
                    if (window.location.pathname === "/saved") {
                        btn.closest("tr").remove();
                    }
                }
            }
        }

        function triggerFilterLoading() {
            const loader = document.getElementById("searchLoading");
            loader.style.display = "inline";
            if (filterDebounce) clearTimeout(filterDebounce);
            filterDebounce = setTimeout(() => {
                applyFilter();
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

        function applyFilter() {
            const query = document.getElementById("tableFilter").value.toLowerCase();
            const intent = document.getElementById("filterIntent").value;
            const cluster = document.getElementById("filterCluster").value;
            const minWords = parseInt(document.getElementById("filterWords").value, 10);

            const rows = document.querySelectorAll("#keywordsTable tbody tr");
            let visibleCount = 0;

            rows.forEach(tr => {
                const kw = tr.getAttribute("data-keyword") || "";
                const rowIntent = tr.getAttribute("data-intent") || "";
                const rowCluster = tr.getAttribute("data-cluster") || "";
                const words = parseInt(tr.getAttribute("data-words") || "0", 10);

                const matchQ = !query || kw.includes(query);
                const matchIntent = !intent || rowIntent === intent;
                const matchCluster = !cluster || rowCluster === cluster;
                const matchWords = isNaN(minWords) || minWords === 0 || words >= minWords;

                if (matchQ && matchIntent && matchCluster && matchWords) {
                    tr.style.display = "";
                    visibleCount++;
                } else {
                    tr.style.display = "none";
                }
            });

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
                <li>Click the button <strong>"📋 Copy List"</strong>. The dashboard immediately copies the exact keyword list to your operating system clipboard.</li>
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

@app.route("/")
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

@app.route("/saved")
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

@app.route("/guide")
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
