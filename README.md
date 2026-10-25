# kwr - Keyword Research & Discovery Intelligence Engine

Automated Google Autocomplete keyword expansion, search intent classification, and Google Sheets synchronization.

---

## ⚡ Zero-Friction Quick Start

### 1. One-Click Launch (Recommended)
- **Windows**: Double-click **`start.bat`** (or type `kwr start`).
- **Linux / macOS / Termux**: Run **`chmod +x start.sh && ./start.sh`**.

*This automatically checks and installs dependencies, then launches the local dashboard at `http://127.0.0.1:5000`.*

---

### 2. Manual Setup
```bash
# 1. Clone repository
git clone https://github.com/durgesharma/kwr.git
cd kwr

# 2. Install dependencies
pip install -r requirements.txt

# 3. Check installation health
python kwr.py check

# 4. Start Web Command Center
python kwr.py start
```
Open **`http://127.0.0.1:5000`** in your browser.

---

## 🛠️ CLI Operations & `kwr help`

Run the built-in CLI assistant anytime for instructions and diagnostics:
```bash
python kwr.py help
```

### Available CLI Commands:
| Command | Description |
|---|---|
| `python kwr.py help` | Show detailed usage manual, modes, and flags |
| `python kwr.py check` | Run system diagnostics and verify dependencies |
| `python kwr.py start` | Launch the web dashboard on port 5000 |
| `python kwr.py harvest "<seed>"` | Harvest keywords directly from terminal |
| `python kwr.py sync-sheets` | Sync local database into your Google Sheet |

### Terminal Harvest Examples:
```bash
# Alphabet Soup A-Z scan
python kwr.py harvest "modular kitchen" --mode az_suffix

# Commercial Buyer-Intent scan with geo-targeting
python kwr.py harvest "interior designer" --mode commercial --loc "Navi Mumbai, Thane"

# Full deep harvest
python kwr.py harvest "wardrobe contractor" --mode deep_harvest
```

---

## 📊 Google Sheets Live Synchronization (Optional)

You can sync discovered keywords directly to your own Google Sheet alongside the local CSV database.

### Simple 3-Step Setup:
1. **Get Credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com).
   - Create a project and enable both **Google Sheets API** and **Google Drive API**.
   - Create a **Service Account**, generate a JSON key, and save it in this project folder as **`credentials.json`**.
2. **Share Your Google Sheet**:
   - Create a new Google Spreadsheet in your Google Drive.
   - Click **Share** and add your Service Account email (e.g. `your-app@...gserviceaccount.com`) with **Editor** permissions.
3. **Connect & Sync**:
   - Open the web dashboard (`http://127.0.0.1:5000`), click **📊 GOOGLE SHEET**, paste your Spreadsheet URL, and click **Sync to Google Sheet**.
   - Or run from terminal:
     ```bash
     python kwr.py sync-sheets --url "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
     ```

---

## 📖 Built-in Field Manual
Click the **`?`** button in the top-right corner of the web dashboard or navigate to **`/guide`** to read the complete field manual covering autocomplete algorithms, search intent classification, and search volume extraction via Google Keyword Planner.
