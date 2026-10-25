import csv
import os
from datetime import datetime

CSV_FILE = "smartwood_keywords.csv"

# Define columns based on your schema
COLUMNS = [
    "Keyword",
    "Source",
    "Discovered From",
    "Collection Date",
    "Search Intent",
    "Topic Cluster",
    "Location",
    "Monthly Search Volume",
    "Volume Source",
    "SEO Difficulty",
    "Target Page",
    "Validation Status",
    "Priority"
]

def init_local_sheet():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
        print(f"Created local sheet: {CSV_FILE}")
    else:
        print(f"Local sheet already exists: {CSV_FILE}")

def add_keyword_row(keyword, source, discovered_from, intent, cluster, location):
    row = [
        keyword,
        source,
        discovered_from,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        intent,
        cluster,
        location,
        "", # Monthly Search Volume (unknown initially)
        "", # Volume Source
        "", # SEO Difficulty
        "", # Target Page
        "Unverified",
        "Medium"
    ]
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(row)
    print(f"Added keyword: '{keyword}' to local sheet.")

if __name__ == "__main__":
    init_local_sheet()
    add_keyword_row(
        keyword="modular kitchen Navi Mumbai",
        source="Google Autocomplete",
        discovered_from="seed",
        intent="Commercial",
        cluster="Modular Kitchens",
        location="Navi Mumbai"
    )
    print("Local sheet test completed successfully!")
