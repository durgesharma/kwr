# kwr - Keyword Research & Discovery Intelligence Engine

Automated Google Autocomplete keyword expansion, real-time discovery intelligence, and streamlined keyword management for desktop, mobile, and Termux.

---

## Key Features & Highlights

- **Multi-Seed Comma-Separated Input (`word , word , word`)**:
  - Enter multiple seed words separated by commas (e.g., `seo audit , technical seo , local seo`) in a single run.
  - Each comma-separated word is expanded independently using real live Google Autocomplete suggestions, with automatic seed-stem verification so only genuine user searches containing each target word are collected.
- **Persistent Seed & Form State**:
  - Your entered Seed Keyword, Expansion Mode, Country/Region, Location Modifiers, and Negative Keywords automatically persist across sheet switches, new sheet creation, and Harvest page reloads—your entered seed is never lost.
- **Streamlined Discovery Modes & Advanced `(algos)`**:
  - `All variations (A to Z scan)`: Complete alphabet soup expansion (`seed + a..z`).
  - `Questions (How, What, Why, Where)`: High-intent interrogative queries.
  - `Buying & Pricing (Cost, Best, Near Me)`: Commercial & transactional buyer queries.
  - `Deep Scan (Combines all methods)`: Multi-angle expansion.
  - `Quick Search (Direct suggestions)`: Fast top suggestions.
  - `Multi-Word Smart Scan (algos)`: High-yield prefix, suffix, and commercial/question stems across multiple comma-separated words.
  - `Recursive Snowball Graph (algos)`: Two-pass Breadth-First Search (BFS) autocomplete graph crawler that feeds real Pass-1 Google suggestions back into Pass-2 to uncover deep long-tail keywords.
  - `Wildcard & Gap Fill (algos)`: Uses Google Autocomplete `_` infix/wildcard templates and cursor-position (`cp`) mechanics to discover mid-phrase and prepositional completions.
  - `Semantic & Buyer Matrix (algos)`: Probes comparison (`vs`, `or`, `alternative`), evaluation (`review`, `worth it`), and buyer-intent modifiers.
  - `Answer & Question Miner (algos)`: AnswerThePublic-style 5W1H, modal, and problem/issue suffix mining.
  - `Ultra Deep All-In-One (algos)`: Flagship algorithm combining A–Z suffix/prefix, numbers, wildcard gap fill, semantic matrix, deep questions, and recursive snowball expansion.
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
  - Starts with a clean universal `keywords.csv` workspace out of the box.
  - Organize keyword campaigns into isolated local CSV sheets (e.g. `keywords.csv`, `saas_campaign.csv`, `ecommerce_seo.csv`).
  - Create and switch sheets seamlessly right from the web dashboard without losing your current seed input.
- **Google Sheets Cloud Sync (Optional)**:
  - 1-click or CLI synchronization to push local keyword sheets directly to Google Sheets using a Google Service Account.

---

## Zero-Friction Quick Start

### 1. Android Phone (Termux) Setup
Run KWR entirely standalone directly on your Android phone without needing a computer:
```bash
# 1. Update Termux packages & install Python + Git
pkg update -y && pkg install python git -y

# 2. Clone the repository
git clone https://github.com/durgesharma/seo-keyword-finder.git
cd seo-keyword-finder

# 3. Launch with one tap
chmod +x start.sh
./start.sh
```
Open **`http://localhost:5000`** in Chrome on your phone.
*(Tip: In Chrome, tap the 3 dots menu and select **"Add to Home screen"** to launch KWR like a native mobile app!)*

---

### 2. iPhone / iPad (iOS) Setup
You can use KWR on an iPhone using either method:

- **Method A — Wi-Fi Network Access (Easiest)**:
  1. Start KWR on your computer, laptop, or Android device on the same local Wi-Fi: `python kwr.py start`.
  2. The terminal will display your network address: `http://<YOUR-IP>:5000`.
  3. Open Safari on your iPhone, enter `http://<YOUR-IP>:5000`, tap **Share (square with arrow)**, and tap **"Add to Home Screen"**.

- **Method B — Standalone on iPhone (via a-Shell app)**:
  1. Install free [a-Shell](https://apps.apple.com/app/a-shell/id1473805438) from the App Store.
  2. In a-Shell, run:
     ```bash
     git clone https://github.com/durgesharma/seo-keyword-finder.git
     cd seo-keyword-finder
     python3 kwr.py start
     ```
  3. Open Safari and go to **`http://localhost:5000`**.

---

### 3. Windows & Mac / Linux Desktop

- **Windows**: Double-click **`start.bat`** (or run `python kwr.py start`).
- **Mac / Linux**: Run **`chmod +x start.sh && ./start.sh`**.

*Dependencies (`flask`, `requests`) are automatically verified and installed on first run.*

---

### 4. Manual Setup
```bash
# 1. Clone repository
git clone https://github.com/durgesharma/seo-keyword-finder.git
cd seo-keyword-finder

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
   - Tap the **`[?] Guide`** button in the top right to view the updated Field Manual at `/guide` covering multi-word comma-separated seeds, all 6 `(algos)` engines, persistent form state, and selection-aware batch workflows.
2. **Sheet Management**:
   - Use the Sheet dropdown to switch between projects or tap **`New`** to create a new campaign sheet instantly on your device. Your typed seed and settings stay intact when switching sheets.
3. **Interactive Metric Cards**:
   - Tap **Keywords** to view all discovered terms.
   - Tap **Saved** to focus only on bookmarked high-priority keywords.
   - Tap **Export CSV** to download the active view or whatever keywords you currently have checked.
4. **Keyword Harvester**:
   - Enter a single seed or multiple comma-separated seeds (e.g., `cloud hosting , vps server , dedicated hosting`), choose a discovery mode or `(algos)` engine, optionally enter target cities or negative keywords, and click **Harvest**.
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
# Multi-seed Smart Scan (algos)
python kwr.py harvest "seo audit, technical seo, backlink checker" --mode algo_multiseed

# Recursive Snowball Graph (algos)
python kwr.py harvest "cloud hosting" --mode algo_recursive

# Commercial & Buyer Intent scan with geo-targeting
python kwr.py harvest "web design agency" --mode commercial --loc "New York, Austin"

# Ultra Deep All-In-One (algos)
python kwr.py harvest "crm software" --mode algo_ultra
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

## Built-in Field Manual (`/guide`)
Click the **`[?] Guide`** button in the web dashboard or navigate directly to **`/guide`** to read the complete 7-chapter Field Manual covering:
1. **What's New & Core Architecture**: Live concurrent Google Autocomplete harvesting & platform updates.
2. **Multi-Word Comma-Separated Seeds (`word , word , word`)**: How independent seed expansion, pairwise probes, and token verification work.
3. **Standard Discovery Modes & Advanced `(algos)`**: When to use each of the 6 `(algos)` modes (`Multi-Word Smart Scan`, `Recursive Snowball Graph`, `Wildcard & Gap Fill`, `Semantic & Buyer Matrix`, `Answer & Question Miner`, `Ultra Deep All-In-One`).
4. **Sheet Workspaces, Persistent Form State & Selection Actions**: Managing CSV sheets without losing your seed input and using selection-aware Copy, Delete, and Export CSV.
5. **Search Intent Dissection & Long-Tail Filtering**: Filtering by word length and sorting by date.
6. **Local Geo-Targeting & Negative Keyword Pruning**: Isolating local markets and blocking noise terms.
7. **Extracting Search Volume with Google Keyword Planner**: Zero-cost search volume and CPC workflow.
