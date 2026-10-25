import csv
import os
import requests
import time
from datetime import datetime

CSV_FILE = "smartwood_keywords.csv"

# Initial seed keywords for SmartWood
SEED_KEYWORDS = [
    "modular kitchen Navi Mumbai",
    "wardrobe contractor Navi Mumbai",
    "full home renovation Navi Mumbai",
    "carpenter Ghansoli",
    "interior execution Thane"
]

def fetch_google_autocomplete(query):
    """Fetches keyword suggestions from Google's public autocomplete endpoint."""
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

def save_keyword(keyword, discovered_from, intent="Commercial", cluster="General Carpentry", location="Navi Mumbai"):
    """Appends a keyword to the local CSV if it doesn't already exist."""
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].lower() == keyword.lower():
                    return False # Already exists

    row = [
        keyword,
        "Google Autocomplete",
        discovered_from,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        intent,
        cluster,
        location,
        "", 
        "", 
        "", 
        "", 
        "Unverified",
        "Medium"
    ]
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(row)
    return True

def run_discovery():
    print("Starting SmartWood Keyword Discovery Bot...")
    discovered_count = 0

    for seed in SEED_KEYWORDS:
        print(f"\nExploring seed: '{seed}'")
        suggestions = fetch_google_autocomplete(seed)
        
        for suggestion in suggestions:
            if save_keyword(suggestion, discovered_from=seed):
                print(f"  [+] Discovered: {suggestion}")
                discovered_count += 1
            time.sleep(0.3)

        for suggestion in suggestions[:2]:
            sub_suggestions = fetch_google_autocomplete(suggestion)
            for sub in sub_suggestions:
                if save_keyword(sub, discovered_from=suggestion):
                    print(f"    [++] Recursive Discovered: {sub}")
                    discovered_count += 1
                time.sleep(0.3)

    print(f"\nDiscovery complete! Added {discovered_count} new unique keywords to {CSV_FILE}.")

if __name__ == "__main__":
    run_discovery()
