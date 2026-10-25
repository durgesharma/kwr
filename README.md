# kwr - SmartWood Keyword Research & Discovery Tool

Automated keyword expansion and curation tool built for SmartWood carpentry, modular kitchen, and interior execution services.

## Overview

- **`app.py`**: Flask web dashboard to view, filter, sort, edit, and expand keywords.
- **`bot.py`**: Automated keyword discovery bot querying Google Autocomplete for seed queries.
- **`test_local_sheet.py`**: Utility script to initialize and test the local CSV storage.
- **`smartwood_keywords.csv`**: Local dataset tracking keywords, search intent, topic cluster, volume, and priority.

## Quick Start

1. Install requirements:
   ```bash
   pip install flask requests
   ```

2. Run the keyword expansion bot:
   ```bash
   python bot.py
   ```

3. Run the web UI:
   ```bash
   python app.py
   ```
   Open `http://127.0.0.1:5000` in your browser.
