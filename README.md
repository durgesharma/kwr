# kwr - Keyword Research & Discovery Intelligence Engine

Automated Google Autocomplete keyword expansion, real-time discovery intelligence, and streamlined keyword management for desktop, mobile, and Termux.

---

## Key Features & Highlights

- **Streamlined Discovery Modes**:
  - `Standard A-Z`: Complete alphabet soup expansion (`seed + a..z`).
  - `Questions & Needs`: High-intent queries using interrogative modifiers (`how`, `why`, `what`, `best`, `near me`).
  - `Deep Discovery`: Comprehensive recursive multi-pass crawl for finding low-competition long-tail keywords.
- **Mobile-First & Desktop Ergonomics**:
  - Re-architected 3-tier top layout designed specifically for phones and tablets.
  - Dedicated full-width Sheet Switcher with one-tap `[+] New` sheet creation (no truncated file names).
  - Clean brand header with quick-access `[?] Guide` field manual.
- **Unified Interactive Metric Strip**:
  - **Keywords Card**: Displays total count and toggles full keyword list.
  - **Saved Card**: Displays starred count and filters instantly to bookmarked keywords with zero page reloads.
  - **Export Card**: Context-aware CSV export. Downloads selected checkboxes if any, or active view (`Saved` vs `All`).
- **Selection-Aware Batch Operations**:
  - **Contextual Copy**: Copies only selected keywords when checkboxes are checked; copies all visible/active tab keywords when unselected. Supports clipboard fallback for local HTTP/Termux environments.
  - **Instant In-Place Deletion**: Single-row and bulk checkbox deletions remove elements directly from the DOM and update all counter cards in real time without slow full-page reloads.
  - **Live Selection Counter**: Dynamic status bar displays `<N> selected · <Total> rows` with automatic indeterminate/master checkbox synchronization.
- **High-Performance Architecture & Zero-Lag DOM**:
  - **In-Memory Row Cache**: Eliminates repeated DOM queries and layout thrashing during live keyword filtering.
  - **DocumentFragment Re-ordering**: Date sorting batches DOM updates into a single reflow instead of hundreds of live append mutations.
  - **CSS `content-visibility: auto`**: Off-screen rows skip layout and painting overhead for buttery smooth 60fps scrolling on mobile devices.
  - **Sheet Header Cache**: In-memory caching in the engine eliminates redundant disk reads during batch updates.
- **Clean, Distraction-Free Keyword Table**:
  - Zero clutter: Focuses on core data (`KEYWORD`, `DATE`, `BOOKMARK`, `ACTIONS`) without redundant columns.
  - **Square Row Delete Buttons**: Consistent `24x24px` theme-matched square `×` buttons (`.row-del-btn`) with subtle danger hover states.
  - **Date Ordering**: Sort instantly by `All` (natural sheet order), `Date: Newest`, or `Date: Oldest`.
  - **Word Length Filtering**: Filter by length (`2+ Words`, `3+ Words`, `4+ Words`, etc.) to isolate long-tail queries.
  - **Real-Time Search**: Instant live keyword filtering as you type.
  - **Compact Phone Action Bar**: Left-aligned date/word controls with right-aligned icon-only Copy and Delete buttons.
- **Minimalist Aesthetic & Theme Parity**:
  - Soft, eye-friendly desaturated dark matte theme (`#16171a` / `#1e2025`) to eliminate glare and eye strain.
  - Complete dark matte theme parity for the built-in Field Manual (`/guide`).
  - Clean, crisp SVG vector icons replacing all emojis across the entire UI.
- **Multi-Sheet Management**:
  - Organize keyword campaigns into isolated local CSV sheets (e.g. `smartwood_keywords.csv`, `real_estate.csv`).
  - Create and switch sheets seamlessly right from the web dashboard.
- **Google Sheets Cloud Sync (Optional)**:
  - 1-click or CLI synchronization to push local keyword sheets directly to Google Sheets using a Google Service Account.

---

## Zero-Friction Quick Start

### 1. One-Click Launch (Recommended)
- **Windows**: Double-click **`start.bat`** (or run `python kwr.py start`).
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

## Web Command Center Walkthrough

1. **Header & Field Manual**:
   - Tap the **`[?] Guide`** button in the top right to view the field manual and tactical SEO guide at `/guide` (now in matching dark mode).
2. **Sheet Management**:
   - Use the Sheet dropdown to switch between projects or tap **`New`** to create a new campaign sheet instantly on your device.
3. **Interactive Metric Cards**:
   - Tap **Keywords** to view all discovered terms.
   - Tap **Saved** to focus only on starred high-priority keywords.
   - Tap **Export CSV** to download the active view or whatever keywords you currently have checked.
4. **Keyword Harvester**:
   - Enter a seed term (e.g., `interior designer`), choose a discovery mode, optionally enter target cities or negative keywords, and click **Harvest**.
5. **Selection & Bulk Actions**:
   - Check individual rows or use the header checkbox to select all visible rows.
   - Click the **Copy** button to copy selected keywords (or all visible keywords if none are selected) to your clipboard for Google Keyword Planner.
   - Click the **Delete** button to remove selected rows immediately without page reloads.

---

## CLI Operations & kwr help

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
# Standard Alphabet Soup A-Z scan
python kwr.py harvest "modular kitchen" --mode az_suffix

# Questions & Needs scan with geo-targeting
python kwr.py harvest "interior designer" --mode commercial --loc "Navi Mumbai, Thane"

# Full deep harvest
python kwr.py harvest "wardrobe contractor" --mode deep_harvest
```

---

## Google Sheets Live Synchronization (Optional)

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
   - Open the web dashboard (`http://127.0.0.1:5000`), click **Google Sheet**, paste your Spreadsheet URL, and click **Sync to Google Sheet**.
   - Or run from terminal:
     ```bash
     python kwr.py sync-sheets --url "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit"
     ```

---

## Built-in Field Manual
Click the **`[?] Guide`** button in the web dashboard or navigate directly to **`/guide`** to read the complete field manual covering autocomplete algorithms, search intent classification, and search volume extraction via Google Keyword Planner.
