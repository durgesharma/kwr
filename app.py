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

# ==================== TEMPLATES ====================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KWR - Keyword Research Intelligence Engine</title>
    <style>
        :root {
            --bg: #0f1115;
            --surface: #181b21;
            --border: #2c323f;
            --text: #e6edf3;
            --muted: #8b949e;
            --accent: #238636;
            --accent-blue: #1f6feb;
            --danger: #da3633;
            --tag-tx: #9e6a03;
            --tag-comm: #1f6feb;
            --tag-info: #238636;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; background-color: var(--bg); color: var(--text); padding: 16px; font-size: 13px; line-height: 1.4; }
        
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
        .header h1 { font-size: 1.25rem; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
        .header .nav-links { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .header .nav-links a { color: #58a6ff; text-decoration: none; font-size: 12px; border: 1px solid var(--border); padding: 6px 12px; border-radius: 4px; background: var(--surface); display: inline-flex; align-items: center; justify-content: center; }
        .header .nav-links a:hover { background: #22272e; color: #79c0ff; }
        .header .nav-links a.help-btn { width: 28px; height: 28px; padding: 0; border-radius: 50%; font-size: 14px; font-weight: 700; color: #e6edf3; background: #21262d; border: 1px solid #30363d; }
        .header .nav-links a.help-btn:hover { background: #30363d; color: #58a6ff; border-color: #58a6ff; }
        
        .stats-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }
        .stat-card { background: var(--surface); border: 1px solid var(--border); padding: 10px; border-radius: 4px; }
        .stat-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; }
        .stat-card .val { font-size: 1.2rem; font-weight: bold; margin-top: 4px; color: #58a6ff; }
        
        .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 14px; margin-bottom: 16px; }
        .panel-title { font-weight: bold; font-size: 12px; text-transform: uppercase; margin-bottom: 10px; color: #8b949e; letter-spacing: 0.5px; }
        
        .grid-form { display: grid; grid-template-columns: 2fr 1.2fr 1fr 1fr; gap: 10px; align-items: end; }
        .form-group { display: flex; flex-direction: column; gap: 4px; }
        label { font-size: 11px; color: var(--muted); }
        input[type="text"], select, textarea {
            background: #0d1117; border: 1px solid var(--border); color: #c9d1d9; padding: 8px 10px; font-family: inherit; font-size: 12px; border-radius: 4px; outline: none; width: 100%;
        }
        input[type="text"]:focus, select:focus, textarea:focus { border-color: #58a6ff; }
        
        .adv-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
        
        button.btn {
            background: var(--accent-blue); color: #fff; border: 1px solid rgba(255,255,255,0.1); padding: 8px 14px; font-family: inherit; font-size: 12px; font-weight: 600; border-radius: 4px; cursor: pointer; height: 35px;
        }
        button.btn:hover { filter: brightness(1.15); }
        button.btn-green { background: var(--accent); }
        button.btn-danger { background: var(--danger); }
        button.btn-sm { height: auto; padding: 4px 8px; font-size: 11px; }

        /* Progress banner */
        #progressContainer { display: none; background: #161b22; border: 1px solid #388bfd; border-radius: 4px; padding: 12px; margin-bottom: 16px; }
        .progress-bar-bg { background: #21262d; height: 8px; border-radius: 4px; overflow: hidden; margin: 8px 0; }
        .progress-bar-fill { background: #238636; height: 100%; width: 0%; transition: width 0.2s; }
        
        /* Table and filters */
        .controls-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; margin-bottom: 10px; }
        .left-controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .right-controls { display: flex; gap: 8px; align-items: center; }

        .table-wrap { overflow-x: auto; max-height: 60vh; border: 1px solid var(--border); border-radius: 4px; background: #0d1117; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
        th, td { padding: 7px 10px; border-bottom: 1px solid #21262d; white-space: nowrap; }
        th { background: #161b22; color: #8b949e; font-weight: 600; position: sticky; top: 0; z-index: 5; font-size: 11px; }
        tr:hover td { background: #161b22; }
        
        .badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; text-transform: uppercase; }
        .badge-tx { background: rgba(210, 153, 34, 0.2); color: #d29922; border: 1px solid rgba(210, 153, 34, 0.4); }
        .badge-comm { background: rgba(56, 139, 253, 0.2); color: #58a6ff; border: 1px solid rgba(56, 139, 253, 0.4); }
        .badge-info { background: rgba(63, 185, 80, 0.2); color: #3fb950; border: 1px solid rgba(63, 185, 80, 0.4); }
        
        a.serp-link { color: #8b949e; text-decoration: none; margin-left: 6px; font-size: 11px; }
        a.serp-link:hover { color: #58a6ff; text-decoration: underline; }

        select.inline-select { background: #161b22; border: 1px solid #30363d; color: #c9d1d9; font-size: 11px; padding: 2px 4px; border-radius: 3px; }
        
        /* Bookmark button */
        .bm-btn { background: #21262d; border: 1px solid #30363d; color: #8b949e; cursor: pointer; }
        .bm-btn:hover { color: #fff; border-color: #58a6ff; }
        .bm-btn.bm-active { background: rgba(210, 153, 34, 0.15); border-color: #d29922; color: #d29922; font-weight: bold; }

        #toast {
            position: fixed; bottom: 20px; right: 20px; background: #238636; color: #fff; padding: 10px 16px; border-radius: 4px; display: none; z-index: 99; font-weight: bold; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }

        /* Modal Overlay */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: none; align-items: center; justify-content: center; z-index: 100;
        }
        .modal-card {
            background: #181b21; border: 1px solid var(--border); border-radius: 6px; padding: 20px; width: 520px; max-width: 90vw; color: var(--text);
        }
        .modal-card h3 { font-size: 14px; margin-bottom: 12px; color: #58a6ff; display: flex; justify-content: space-between; align-items: center; }
        .modal-card .close-btn { background: none; border: none; color: var(--muted); font-size: 18px; cursor: pointer; }
        .setup-steps { background: #0d1117; border: 1px solid #30363d; padding: 12px; border-radius: 4px; font-size: 11px; margin-bottom: 14px; color: #8b949e; line-height: 1.5; }
        .setup-steps ol { padding-left: 18px; }
        .setup-steps li { margin-bottom: 4px; }
        .setup-steps code { color: #58a6ff; }

        .sheet-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; background: #0d1117; border: 1px solid #21262d; border-radius: 4px; margin-bottom: 6px; font-size: 12px; }
        .sheet-item.active { border-color: #238636; }
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>KWR ENGINE // Google Autocomplete Intelligence</h1>
            <div style="font-size: 11px; color: var(--muted); margin-top: 2px;">
                Active Sheet: <strong style="color: #58a6ff;">{{ active_sheet }}</strong>
                {% if is_saved_view %} &bull; <span style="color: #d29922; font-weight: bold;">★ SAVED / BOOKMARKS VIEW</span>{% endif %}
            </div>
        </div>
        <div class="nav-links">
            {% if is_saved_view %}
                <a href="/" style="color: #79c0ff; font-weight: bold;">← ALL KEYWORDS</a>
            {% else %}
                <a href="/saved" style="color: #d29922; font-weight: bold;">★ SAVED ({{ saved_count }})</a>
            {% endif %}
            <button class="btn btn-sm" onclick="openSheetSelectorModal()" style="background: #21262d; border: 1px solid #30363d; color: #79c0ff;">📁 SHEETS</button>
            <button class="btn btn-sm" onclick="openSheetsModal()" style="background: #21262d; border: 1px solid #30363d; color: #58a6ff;">📊 GOOGLE SHEET</button>
            <a href="/export">⬇ EXPORT CSV</a>
            <a href="/guide" target="_blank" class="help-btn" title="How to Use / Field Manual">?</a>
        </div>
    </div>

    <!-- STATS BAR -->
    <div class="stats-bar">
        <div class="stat-card">
            <div class="label">Total Keywords</div>
            <div class="val" id="statTotal">{{ total_count }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Saved (Bookmarked)</div>
            <div class="val" style="color: #d29922;">{{ saved_count }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Transactional (Buyer)</div>
            <div class="val" style="color: #d29922;">{{ tx_count }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Commercial (Reviews/Vs)</div>
            <div class="val" style="color: #58a6ff;">{{ comm_count }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Informational (Guides/Q)</div>
            <div class="val" style="color: #3fb950;">{{ info_count }}</div>
        </div>
    </div>

    {% if not is_saved_view %}
    <!-- HARVESTER CONTROL PANEL -->
    <div class="panel">
        <div class="panel-title">Keyword Discovery Runner (Target Sheet: {{ active_sheet }})</div>
        <form id="harvestForm" onsubmit="startHarvest(event)">
            <div class="grid-form">
                <div class="form-group">
                    <label>Seed Keyword</label>
                    <input type="text" id="seedInput" placeholder="e.g. modular kitchen, wardrobe design, carpenter" required>
                </div>
                <div class="form-group">
                    <label>Expansion Mode</label>
                    <select id="modeSelect">
                        <option value="az_suffix">Alphabet Soup: Suffix [Seed + A-Z] (Standard)</option>
                        <option value="az_prefix">Alphabet Soup: Prefix [A-Z + Seed]</option>
                        <option value="commercial">Commercial & Buyer Intent (Price, Cost, Contractor, Near Me)</option>
                        <option value="questions">Questions & Informational (How, What, Why, Which)</option>
                        <option value="prepositions">Prepositions & Comparisons (Vs, For, With, Near)</option>
                        <option value="numbers">Numbers & Sizes [Seed + 0-9]</option>
                        <option value="deep_harvest">🔥 Full Deep Harvest (Runs All Above Modules)</option>
                        <option value="standard">Standard Fast (Direct Suggestions Only)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Region & Language</label>
                    <select id="regionSelect">
                        <option value="in:en" selected>India (en)</option>
                        <option value="in:hi">India (hi)</option>
                        <option value="us:en">United States (en)</option>
                        <option value="uk:en">United Kingdom (en)</option>
                        <option value="ae:en">UAE (en)</option>
                    </select>
                </div>
                <div class="form-group">
                    <button type="submit" class="btn btn-green" id="runBtn">⚡ RUN HARVEST</button>
                </div>
            </div>

            <div class="adv-row">
                <div class="form-group">
                    <label>Location Modifiers (comma-separated, appended to query)</label>
                    <input type="text" id="locationsInput" value="Navi Mumbai, Thane" placeholder="e.g. Navi Mumbai, Thane, Kharghar">
                </div>
                <div class="form-group">
                    <label>Negative Filter (comma-separated, auto-discards junk matches)</label>
                    <input type="text" id="negativesInput" value="job, salary, vacancy, pdf, download, course" placeholder="e.g. jobs, salary, pdf">
                </div>
            </div>
        </form>
    </div>
    {% endif %}

    <!-- LIVE PROGRESS BOX -->
    <div id="progressContainer">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong style="color: #58a6ff;" id="progressText">Harvesting keywords...</strong>
            <button class="btn btn-danger btn-sm" onclick="stopHarvest()">STOP JOB</button>
        </div>
        <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="progressFill"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--muted);">
            <span id="currentQueryText">Query: -</span>
            <span id="harvestCountText">New Harvested: 0</span>
        </div>
    </div>

    <!-- DATA TABLE & CONTROLS -->
    <div class="panel" style="padding: 10px;">
        <div class="controls-bar">
            <div class="left-controls">
                <div style="position: relative; display: flex; align-items: center;">
                    <input type="text" id="tableFilter" placeholder="Filter keywords in sheet..." style="width: 230px;" oninput="triggerFilterLoading()">
                    <span id="searchLoading" style="display: none; position: absolute; right: 8px; font-size: 10px; color: #58a6ff;">filtering...</span>
                </div>
                <select id="filterIntent" onchange="applyFilter()" style="width: 140px;">
                    <option value="">All Intents</option>
                    <option value="Transactional">Transactional</option>
                    <option value="Commercial">Commercial</option>
                    <option value="Informational">Informational</option>
                </select>
                <select id="filterCluster" onchange="applyFilter()" style="width: 170px;">
                    <option value="">All Clusters</option>
                    {% for c in clusters %}
                    <option value="{{ c }}">{{ c }}</option>
                    {% endfor %}
                </select>
                <select id="filterWords" onchange="applyFilter()" style="width: 130px;">
                    <option value="0">All Lengths</option>
                    <option value="3">3+ Words</option>
                    <option value="4">4+ Words (Long-tail)</option>
                    <option value="5">5+ Words (Ultra long-tail)</option>
                </select>
            </div>
            <div class="right-controls">
                <button class="btn btn-sm" onclick="copyVisibleKeywords()">📋 COPY VISIBLE FOR GKP</button>
                <button class="btn btn-sm btn-danger" onclick="deleteSelected()">🗑 DELETE SELECTED</button>
                <span id="rowCountLabel" style="font-size: 11px; color: var(--muted);">Showing: {{ total_count }}</span>
            </div>
        </div>

        <div class="table-wrap">
            <table id="keywordsTable">
                <thead>
                    <tr>
                        <th style="width: 28px;"><input type="checkbox" id="selectAll" onclick="toggleSelectAll(this)"></th>
                        <th style="width: 60px;">SAVE</th>
                        <th>KEYWORD</th>
                        <th>INTENT</th>
                        <th>CLUSTER</th>
                        <th>DISCOVERED FROM</th>
                        <th>WORDS</th>
                        <th>PRIORITY</th>
                        <th>STATUS</th>
                        <th>ACTION</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in rows %}
                    <tr data-keyword="{{ r['Keyword'] | lower }}" 
                        data-intent="{{ r.get('Search Intent', 'Commercial') }}" 
                        data-cluster="{{ r.get('Topic Cluster', '') }}" 
                        data-words="{{ r.get('Word Count', '1') }}"
                        data-bookmarked="{{ r.get('Bookmarked', '0') }}">
                        <td><input type="checkbox" class="row-select" value="{{ r['Keyword'] }}"></td>
                        <td>
                            {% set is_bm = (r.get('Bookmarked') == '1' or r.get('Bookmarked') == 1) %}
                            <button class="btn btn-sm bm-btn {% if is_bm %}bm-active{% endif %}" 
                                    onclick="toggleBookmark('{{ r['Keyword'] }}', this)" 
                                    title="Save to Bookmarks">
                                {% if is_bm %}★ Saved{% else %}☆ Save{% endif %}
                            </button>
                        </td>
                        <td>
                            <strong>{{ r['Keyword'] }}</strong>
                            <a class="serp-link" href="https://www.google.com/search?q={{ r['Keyword'] | urlencode }}" target="_blank" title="Check Live Google SERP">↗ SERP</a>
                            <a class="serp-link" href="https://trends.google.com/trends/explore?q={{ r['Keyword'] | urlencode }}&geo=IN" target="_blank" title="Check Google Trends">↗ Trends</a>
                        </td>
                        <td>
                            {% set it = r.get('Search Intent', 'Commercial') %}
                            {% if it == 'Transactional' %}
                                <span class="badge badge-tx">Transactional</span>
                            {% elif it == 'Informational' %}
                                <span class="badge badge-info">Informational</span>
                            {% else %}
                                <span class="badge badge-comm">Commercial</span>
                            {% endif %}
                        </td>
                        <td style="color: #8b949e;">{{ r.get('Topic Cluster', '-') }}</td>
                        <td style="color: #6e7681; font-size: 11px;">{{ r.get('Discovered From', '-') }}</td>
                        <td>{{ r.get('Word Count', '-') }}</td>
                        <td>
                            <select class="inline-select" onchange="updateRowField('{{ r['Keyword'] }}', 'Priority', this.value)">
                                <option value="High" {% if r.get('Priority') == 'High' %}selected{% endif %}>High</option>
                                <option value="Medium" {% if r.get('Priority') == 'Medium' or not r.get('Priority') %}selected{% endif %}>Medium</option>
                                <option value="Low" {% if r.get('Priority') == 'Low' %}selected{% endif %}>Low</option>
                            </select>
                        </td>
                        <td>
                            <select class="inline-select" onchange="updateRowField('{{ r['Keyword'] }}', 'Validation Status', this.value)">
                                <option value="Unverified" {% if r.get('Validation Status') == 'Unverified' or not r.get('Validation Status') %}selected{% endif %}>Unverified</option>
                                <option value="Target" {% if r.get('Validation Status') == 'Target' %}selected{% endif %}>Target</option>
                                <option value="Discard" {% if r.get('Validation Status') == 'Discard' %}selected{% endif %}>Discard</option>
                            </select>
                        </td>
                        <td>
                            <button class="btn btn-danger btn-sm" onclick="deleteSingle('{{ r['Keyword'] }}')">×</button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <!-- SHEET SELECTOR & CREATOR MODAL -->
    <div id="sheetSelectorModal" class="modal-overlay">
        <div class="modal-card">
            <h3>
                <span>📁 Manage Local Sheets on Device</span>
                <button class="close-btn" onclick="closeSheetSelectorModal()">×</button>
            </h3>
            
            <p style="font-size: 11px; color: var(--muted); margin-bottom: 12px;">
                Sheets stay stored locally as <code>.csv</code> files inside this app on your phone. You can create separate sheets for different niches, clients, or projects.
            </p>

            <div style="font-size: 11px; font-weight: bold; color: #8b949e; text-transform: uppercase; margin-bottom: 6px;">Available Sheets on Device:</div>
            <div id="sheetsListContainer" style="max-height: 180px; overflow-y: auto; margin-bottom: 15px;">
                {% for s in available_sheets %}
                <div class="sheet-item {% if s == active_sheet %}active{% endif %}">
                    <div>
                        <strong>{{ s }}</strong>
                        {% if s == active_sheet %} <span style="color: #238636; font-size: 10px;">(ACTIVE)</span>{% endif %}
                    </div>
                    {% if s != active_sheet %}
                    <button class="btn btn-sm" onclick="switchSheet('{{ s }}')">Select</button>
                    {% endif %}
                </div>
                {% endfor %}
            </div>

            <div style="border-top: 1px solid var(--border); padding-top: 12px;">
                <label style="font-size: 11px; font-weight: bold; color: #58a6ff;">Create New Sheet on Phone:</label>
                <div style="display: flex; gap: 8px; margin-top: 6px;">
                    <input type="text" id="newSheetNameInput" placeholder="e.g. interior_thane or wardrobe_keywords">
                    <button class="btn btn-sm btn-green" onclick="createNewSheet()">+ CREATE</button>
                </div>
            </div>
        </div>
    </div>

    <!-- GOOGLE SHEETS LIVE SYNC MODAL -->
    <div id="sheetsModal" class="modal-overlay">
        <div class="modal-card">
            <h3>
                <span>📊 Google Sheets Live Synchronization</span>
                <button class="close-btn" onclick="closeSheetsModal()">×</button>
            </h3>
            
            <div class="setup-steps">
                <strong>Quick 3-Step Setup:</strong>
                <ol>
                    <li>Download your Google Cloud Service Account JSON key and place it as <code>credentials.json</code> in this project folder.</li>
                    <li>Create your Google Spreadsheet and click <strong>Share</strong> &rarr; grant <strong>Editor</strong> permission to your Service Account email.</li>
                    <li>Paste your Google Spreadsheet URL below and click <strong>Save & Sync</strong>.</li>
                </ol>
            </div>

            <div id="sheetsStatusBanner" style="font-size: 11px; margin-bottom: 12px; padding: 8px; border-radius: 4px; background: #21262d; border: 1px solid #30363d;">
                Status: Checking...
            </div>

            <div class="form-group" style="margin-bottom: 10px;">
                <label>Google Spreadsheet URL or Sheet ID</label>
                <input type="text" id="sheetUrlInput" placeholder="https://docs.google.com/spreadsheets/d/your-sheet-id/edit">
            </div>

            <div class="adv-row" style="margin-bottom: 15px;">
                <div class="form-group">
                    <label>Credentials File</label>
                    <input type="text" id="sheetCredsInput" value="credentials.json">
                </div>
                <div class="form-group">
                    <label>Worksheet Tab Name</label>
                    <input type="text" id="sheetTabInput" value="Keywords">
                </div>
            </div>

            <div style="display: flex; gap: 10px; justify-content: flex-end;">
                <button class="btn btn-sm" onclick="closeSheetsModal()" style="background: #21262d;">CANCEL</button>
                <button class="btn btn-sm btn-green" id="syncBtn" onclick="saveAndSyncSheets()">SYNC TO GOOGLE SHEET</button>
            </div>
        </div>
    </div>

    <div id="toast">Copied to clipboard!</div>

    <script>
        let pollTimer = null;
        let filterDebounce = null;

        function showToast(msg) {
            const t = document.getElementById("toast");
            t.innerText = msg;
            t.style.display = "block";
            setTimeout(() => { t.style.display = "none"; }, 2500);
        }

        // Bookmark toggle
        async function toggleBookmark(keyword, btn) {
            const res = await fetch("/api/toggle_bookmark", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword })
            });
            const data = await res.json();
            if (data.success) {
                if (data.is_bookmarked) {
                    btn.classList.add("bm-active");
                    btn.innerText = "★ Saved";
                    showToast(`Saved '${keyword}' to bookmarks!`);
                } else {
                    btn.classList.remove("bm-active");
                    btn.innerText = "☆ Save";
                    showToast(`Removed '${keyword}' from bookmarks.`);
                    // If on /saved view, hide row immediately
                    if (window.location.pathname === "/saved") {
                        btn.closest("tr").remove();
                    }
                }
            }
        }

        // Sheet Selector Modal
        function openSheetSelectorModal() {
            document.getElementById("sheetSelectorModal").style.display = "flex";
        }

        function closeSheetSelectorModal() {
            document.getElementById("sheetSelectorModal").style.display = "none";
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

        async function createNewSheet() {
            const input = document.getElementById("newSheetNameInput");
            const name = input.value.trim();
            if (!name) {
                alert("Please enter a name for the new sheet.");
                return;
            }
            const res = await fetch("/api/create_sheet", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sheet_name: name })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`Created and switched to ${data.sheet_name}`);
                location.reload();
            } else {
                alert(data.message || "Failed to create sheet.");
            }
        }

        // Filtering with loading indicator
        function triggerFilterLoading() {
            const loader = document.getElementById("searchLoading");
            loader.style.display = "inline";
            if (filterDebounce) clearTimeout(filterDebounce);
            filterDebounce = setTimeout(() => {
                applyFilter();
                loader.style.display = "none";
            }, 80);
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
            document.getElementById("progressText").innerText = "Starting engine...";

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
            document.getElementById("harvestCountText").innerText = `New Harvested: ${st.added_count}`;

            if (!st.running) {
                clearInterval(pollTimer);
                document.getElementById("runBtn").disabled = false;
                showToast(`Harvest complete! Added ${st.added_count} new keywords.`);
                setTimeout(() => { location.reload(); }, 1200);
            }
        }

        async function stopHarvest() {
            await fetch("/api/stop", { method: "POST" });
            document.getElementById("progressText").innerText = "Stopping job...";
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
            if (!confirm(`Delete keyword '${keyword}'?`)) return;
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

            document.getElementById("rowCountLabel").innerText = `Showing: ${visibleCount}`;
        }

        function copyVisibleKeywords() {
            const visibleRows = document.querySelectorAll("#keywordsTable tbody tr");
            const kws = [];
            visibleRows.forEach(tr => {
                if (tr.style.display !== "none") {
                    const kwText = tr.querySelector("strong") ? tr.querySelector("strong").innerText.trim() : "";
                    if (kwText) kws.push(kwText);
                }
            });

            if (!kws.length) {
                alert("No keywords visible to copy.");
                return;
            }

            navigator.clipboard.writeText(kws.join("\\n")).then(() => {
                showToast(`Copied ${kws.length} keywords to clipboard! Ready for Google Keyword Planner.`);
            });
        }

        async function openSheetsModal() {
            document.getElementById("sheetsModal").style.display = "flex";
            const res = await fetch("/api/sheets_status");
            const st = await res.json();
            
            document.getElementById("sheetUrlInput").value = st.sheet_id_or_url || "";
            document.getElementById("sheetCredsInput").value = st.credentials_path || "credentials.json";
            document.getElementById("sheetTabInput").value = st.worksheet_name || "Keywords";

            const banner = document.getElementById("sheetsStatusBanner");
            if (st.credentials_exist) {
                banner.innerHTML = `<span style="color: #3fb950;">✔ Credentials Found:</span> <code>${st.credentials_path}</code><br><span style="color: #8b949e;">Service Email:</span> <code>${st.client_email || 'Present'}</code>`;
            } else {
                banner.innerHTML = `<span style="color: #d29922;">⚠ Missing Credentials:</span> Place <code>${st.credentials_path}</code> in the root folder.`;
            }
        }

        function closeSheetsModal() {
            document.getElementById("sheetsModal").style.display = "none";
        }

        async function saveAndSyncSheets() {
            const sheetUrl = document.getElementById("sheetUrlInput").value.trim();
            const credsPath = document.getElementById("sheetCredsInput").value.trim();
            const tabName = document.getElementById("sheetTabInput").value.trim();

            if (!sheetUrl) {
                alert("Please enter a Google Spreadsheet URL or ID.");
                return;
            }

            const syncBtn = document.getElementById("syncBtn");
            syncBtn.disabled = true;
            syncBtn.innerText = "Syncing...";

            try {
                const res = await fetch("/api/sheets_sync", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        sheet_id_or_url: sheetUrl,
                        credentials_path: credsPath,
                        worksheet_name: tabName
                    })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message);
                    closeSheetsModal();
                } else {
                    alert(data.message);
                }
            } catch (err) {
                alert("Sync failed: " + err);
            } finally {
                syncBtn.disabled = false;
                syncBtn.innerText = "SYNC TO GOOGLE SHEET";
            }
        }
    </script>
</body>
</html>
"""

# ==================== FIELD MANUAL (HOW TO USE) ====================
# Book-style typography: High contrast, clean classic serif, readable line lengths, chapters.

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
        blockquote {
            margin: 20px 0;
            padding: 10px 20px;
            background: #f4f1ea;
            border-left: 3px solid #666;
            font-style: italic;
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
                <li>Click the button <strong>"📋 COPY VISIBLE FOR GKP"</strong>. The dashboard immediately copies the exact keyword list to your operating system clipboard.</li>
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
                Regularly review the dashboard table, mark irrelevant queries with the <strong>"Discard"</strong> status or check their boxes and execute <strong>"DELETE SELECTED"</strong>. Keep your keyword pool lean, verified, and ready for deployment.
            </p>
        </section>
    </div>
</body>
</html>
"""

# ==================== ROUTES ====================

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
        **stats
    )

@app.route("/saved")
def saved_view():
    active_sheet = get_active_sheet()
    all_rows = load_all_keywords(active_sheet)
    # Filter only bookmarked rows
    saved_rows = [r for r in all_rows if str(r.get("Bookmarked", "0")) in ("1", "true", "True", "yes")]
    stats = get_stats_and_data(all_rows)
    # override total count for saved view
    stats["total_count"] = len(saved_rows)
    available_sheets = list_available_sheets()

    return render_template_string(
        DASHBOARD_HTML,
        rows=saved_rows,
        active_sheet=active_sheet,
        available_sheets=available_sheets,
        is_saved_view=True,
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
