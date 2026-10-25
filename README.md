# kwr - Keyword Research & Discovery Intelligence Engine

Automated Google Autocomplete keyword expansion, search intent classification, and curation engine.

## Overview

- **`app.py`**: Functional web dashboard to run deep keyword harvests, filter by intent/clusters/word count, copy directly for Google Keyword Planner, and inspect live Google SERPs.
- **`engine.py`**: Core scraping and intelligence engine featuring Alphabet Soup (A–Z), Question mining, Preposition & Comparison queries, Buyer intent detection, and regional targeting.
- **`bot.py`**: Automated keyword discovery CLI runner.
- **`smartwood_keywords.csv`**: Local CSV storage tracking keywords, intent, topic cluster, and priority.
- **`/guide`**: Built-in, high-contrast, book-style Field Manual detailing autocomplete mechanisms, intent mapping, and search volume extraction workflows.

## Quick Start

1. Install requirements:
   ```bash
   pip install flask requests
   ```

2. Run the keyword expansion bot (CLI):
   ```bash
   python bot.py
   ```

3. Run the web UI:
   ```bash
   python app.py
   ```
   Open `http://127.0.0.1:5000` in your browser.
