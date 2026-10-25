import csv
import os
import requests
import time
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)
CSV_FILE = "smartwood_keywords.csv"

# Ensure CSV exists with headers
COLUMNS = [
    "Keyword", "Source", "Discovered From", "Collection Date", 
    "Search Intent", "Topic Cluster", "Location", 
    "Monthly Search Volume", "Volume Source", "SEO Difficulty", 
    "Target Page", "Validation Status", "Priority"
]

def init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)

init_csv()

def fetch_google_autocomplete(query):
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={requests.utils.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 1 and isinstance(data[1], list):
                return data[1]
    except Exception as e:
        print(f"Error fetching suggestions for '{query}': {e}")
    return []

def run_bot_logic(seed, max_depth_seeds=3):
    """Runs keyword expansion for a given seed and saves unique entries."""
    added_count = 0
    suggestions = fetch_google_autocomplete(seed)
    
    existing_keywords = set()
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            for row in reader:
                if row:
                    existing_keywords.add(row[0].lower())

    def save_row(kw, discovered):
        nonlocal added_count
        if kw.lower() not in existing_keywords:
            row = [
                kw, "Google Autocomplete", discovered,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Commercial", "Custom Research", "Navi Mumbai",
                "", "", "", "", "Unverified", "Medium"
            ]
            with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
            existing_keywords.add(kw.lower())
            added_count += 1
            return True
        return False

    # Save primary suggestions
    for sug in suggestions:
        save_row(sug, seed)
        time.sleep(0.1)

    # Recursive expansion for deeper results
    for sug in suggestions[:max_depth_seeds]:
        sub_suggestions = fetch_google_autocomplete(sug)
        for sub in sub_suggestions:
            save_row(sub, sug)
            time.sleep(0.1)

    return added_count

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartWood Keyword Command Center</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 15px; }
        h1 { color: #ffffff; font-size: 1.3rem; margin-bottom: 5px; }
        p { color: #a0a0a0; font-size: 0.85rem; margin-bottom: 15px; }
        .card { background: #1e1e1e; border: 1px solid #333; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
        .stats { display: flex; gap: 10px; margin-bottom: 15px; }
        .stat-card { background: #222; border: 1px solid #333; padding: 10px; border-radius: 6px; font-size: 0.75rem; flex: 1; text-align: center; }
        .stat-card span { display: block; font-size: 1.1rem; font-weight: bold; color: #90caf9; margin-top: 3px; }
        input[type="text"], select { width: 100%; padding: 10px; box-sizing: border-box; background: #121212; border: 1px solid #444; color: #fff; border-radius: 6px; font-size: 0.9rem; margin-bottom: 10px; outline: none; }
        input[type="text"]:focus, select:focus { border-color: #90caf9; }
        button { background: #1976d2; color: #fff; border: none; padding: 10px 15px; font-size: 0.9rem; font-weight: bold; border-radius: 6px; cursor: pointer; width: 100%; }
        button:hover { background: #115293; }
        .table-container { overflow-x: auto; background: #1e1e1e; border-radius: 8px; border: 1px solid #333; max-height: 55vh; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.75rem; }
        th, td { padding: 8px 10px; border-bottom: 1px solid #2a2a2a; white-space: nowrap; }
        th { background: #252525; color: #fff; font-weight: 600; position: sticky; top: 0; z-index: 10; }
        tr:hover { background: #252525; }
        .alert { background: #1b5e20; color: #c8e6c9; padding: 10px; border-radius: 6px; margin-bottom: 15px; font-size: 0.85rem; }
    </style>
</head>
<body>
    <h1>SmartWood Command Center</h1>
    <p>Termux Local Bot Engine & Database</p>

    {% if message %}
    <div class="alert">{{ message }}</div>
    {% endif %}

    <div class="stats">
        <div class="stat-card">Total Keywords <span>{{ total_count }}</span></div>
        <div class="stat-card">Engine Status <span>Online</span></div>
    </div>

    <div class="card">
        <form action="/run" method="POST">
            <label style="font-size: 0.8rem; font-weight: bold; color: #ccc;">Custom Seed Keyword:</label>
            <input type="text" name="seed" placeholder="e.g. luxury modular kitchen Thane" required>
            
            <label style="font-size: 0.8rem; font-weight: bold; color: #ccc;">Recursion Depth (Search Breadth):</label>
            <select name="depth">
                <option value="2">Fast (Top 2 branches)</option>
                <option value="4" selected>Standard (Top 4 branches)</option>
                <option value="8">Deep Exploration (Top 8 branches)</option>
            </select>

            <button type="submit">Run Bot & Harvest Keywords</button>
        </form>
    </div>

    <input type="text" id="searchBox" placeholder="Filter existing keywords..." onkeyup="filterTable()" style="margin-bottom: 10px;">

    <div class="table-container">
        <table id="keywordTable">
            <thead>
                <tr>
                    {% for header in headers %}
                    <th>{{ header }}</th>
                    {% endfor %}
                </tr>
            </thead>
            <tbody>
                {% for row in rows %}
                <tr>
                    {% for cell in row %}
                    <td>{{ cell }}</td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <script>
        function filterTable() {
            let input = document.getElementById('searchBox');
            let filter = input.value.toLowerCase();
            let table = document.getElementById('keywordTable');
            let tr = table.getElementsByTagName('tr');
            for (let i = 1; i < tr.length; i++) {
                let td = tr[i].getElementsByTagName('td')[0];
                if (td) {
                    let txtValue = td.textContent || td.innerText;
                    tr[i].style.display = txtValue.toLowerCase().indexOf(filter) > -1 ? "" : "none";
                }
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    message = request.args.get('msg', '')
    headers, rows = [], []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            rows = list(reader)
    # Reverse rows so newest appear at top
    rows.reverse()
    return render_template_string(HTML_TEMPLATE, headers=headers, rows=rows, total_count=len(rows), message=message)

@app.route('/run', methods=['POST'])
def run():
    seed = request.form.get('seed')
    depth = int(request.form.get('depth', 4))
    if seed:
        added = run_bot_logic(seed, max_depth_seeds=depth)
        return redirect(url_for('index', msg=f"Successfully harvested {added} new keywords using seed: '{seed}'"))
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
