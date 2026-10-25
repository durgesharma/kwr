import csv
import os
import re
import time
import string
import requests
from datetime import datetime
from threading import Lock

CSV_FILE = "smartwood_keywords.csv"
csv_lock = Lock()

COLUMNS = [
    "Keyword", "Source", "Discovered From", "Collection Date", 
    "Search Intent", "Topic Cluster", "Location", 
    "Word Count", "Validation Status", "Priority", "Target Page"
]

DEFAULT_NEGATIVES = {"job", "jobs", "salary", "vacancy", "pdf", "course", "free download", "app download", "recruitment", "login"}

QUESTION_MODIFIERS = [
    "how to", "what is", "why", "where to", "when to", 
    "which is better", "can we", "is it good", "does", "how much does"
]

PREPOSITION_MODIFIERS = [
    "for", "with", "without", "vs", "versus", "or", "near", "under", "in", "like"
]

COMMERCIAL_MODIFIERS = [
    "cost", "price", "rates per sq ft", "price list", "contractor", 
    "service", "near me", "best", "top", "quote", "estimate", "charges", "showroom", "maker", "installation"
]

NUMBER_MODIFIERS = [str(n) for n in range(0, 10)]
ALPHABET = list(string.ascii_lowercase)


def init_csv():
    """Initializes the CSV database with the required headers if it does not exist."""
    with csv_lock:
        if not os.path.exists(CSV_FILE):
            with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(COLUMNS)


def fetch_google_autocomplete(query, gl="in", hl="en"):
    """
    Queries Google Autocomplete for keyword suggestions.
    Uses public suggestqueries endpoint with regional parameters.
    """
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&gl={gl}&hl={hl}&q={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=6)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 1 and isinstance(data[1], list):
                return [sug.strip() for sug in data[1] if sug and isinstance(sug, str)]
    except Exception as e:
        print(f"[Engine] Autocomplete query error for '{query}': {e}")
    return []


def classify_intent(keyword):
    """
    Classifies search intent using pattern and token rules:
    - Transactional: high buying/booking intent (cost, price, hire, contractor, buy, near me)
    - Commercial Investigation: evaluation/comparison (best, top, vs, review, compare, material)
    - Informational: educational/question (how, what, why, guide, tips, ideas, dimensions)
    - Navigational: brand or login specific
    """
    kw = keyword.lower()
    
    # Check Transactional
    transactional_triggers = [
        "cost", "price", "rate", "rates", "charges", "contractor", "service", 
        "services", "near me", "maker", "agency", "firm", "hire", "buy", 
        "shop", "dealers", "supplier", "estimate", "quote", "order"
    ]
    if any(re.search(r'\b' + re.escape(t) + r'\b', kw) for t in transactional_triggers):
        return "Transactional"

    # Check Commercial Investigation
    commercial_triggers = [
        "best", "top", "review", "reviews", "vs", "versus", "compare", 
        "comparison", "difference", "which is", "pros and cons", "catalogue", "types of"
    ]
    if any(re.search(r'\b' + re.escape(c) + r'\b', kw) for c in commercial_triggers):
        return "Commercial"

    # Check Informational
    informational_triggers = [
        "how", "what", "why", "where", "when", "can", "is", "guide", 
        "tips", "ideas", "meaning", "diy", "height", "standard size", "dimensions", "colour combination"
    ]
    if any(re.search(r'\b' + re.escape(i) + r'\b', kw) for i in informational_triggers):
        return "Informational"

    # Fallback to Commercial intent for trade keywords
    return "Commercial"


def detect_cluster(keyword, seed):
    """
    Assigns a topic cluster based on common interior and trade entities.
    """
    kw = keyword.lower()
    if any(w in kw for w in ["price", "cost", "rate", "budget", "sq ft", "charges"]):
        return "Pricing & Estimates"
    if any(w in kw for w in ["material", "acrylic", "laminate", "plywood", "veneer", "mdf", "hdf", "glass"]):
        return "Materials & Finishes"
    if any(w in kw for w in ["l shaped", "u shaped", "straight", "parallel", "island", "layout", "design"]):
        return "Layouts & Designs"
    if any(w in kw for w in ["wardrobe", "cupboard", "closet", "sliding", "hinged"]):
        return "Wardrobes & Storage"
    if any(w in kw for w in ["kitchen", "modular kitchen", "trolley", "chimney", "countertop"]):
        return "Modular Kitchens"
    if any(w in kw for w in ["contractor", "carpenter", "interior designer", "agency", "execution", "renovation"]):
        return "Contractors & Execution"
    if any(w in kw for w in ["how to", "maintenance", "cleaning", "care", "problem", "waterproof"]):
        return "Maintenance & Troubleshooting"
    
    return seed.title() if seed else "General"


def load_all_keywords():
    """Reads all rows from the local CSV storage."""
    init_csv()
    rows = []
    with csv_lock:
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, mode='r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    rows.append(r)
    return rows


def save_keywords_batch(new_rows):
    """Appends multiple keyword rows safely to the CSV."""
    if not new_rows:
        return 0
    init_csv()
    with csv_lock:
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for r in new_rows:
                writer.writerow(r)
    return len(new_rows)


def update_row_in_csv(keyword_text, updates):
    """Updates fields like Priority, Validation Status, or Target Page for a keyword."""
    init_csv()
    updated = False
    with csv_lock:
        if not os.path.exists(CSV_FILE):
            return False
        with open(CSV_FILE, mode='r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                return False
            rows = []
            for row in reader:
                if len(row) > 0 and row[0].strip().lower() == keyword_text.strip().lower():
                    # Apply updates
                    for field, val in updates.items():
                        if field in headers:
                            idx = headers.index(field)
                            # expand row if needed
                            while len(row) <= idx:
                                row.append("")
                            row[idx] = val
                    updated = True
                rows.append(row)
        
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
            
    return updated


def delete_keywords_from_csv(keywords_to_delete):
    """Removes a list of keywords from CSV."""
    init_csv()
    del_set = {k.strip().lower() for k in keywords_to_delete}
    deleted_count = 0
    with csv_lock:
        if not os.path.exists(CSV_FILE):
            return 0
        with open(CSV_FILE, mode='r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                return 0
            remaining = []
            for row in reader:
                if row and row[0].strip().lower() in del_set:
                    deleted_count += 1
                else:
                    remaining.append(row)
                    
        with open(CSV_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(remaining)
            
    return deleted_count


def generate_queries_for_mode(seed, mode="az_suffix", locations=None):
    """
    Builds the complete queue of Google Autocomplete queries based on the chosen mode.
    """
    clean_seed = seed.strip()
    queries = []

    # If locations are provided, append location to seed queries
    loc_list = [l.strip() for l in locations if l.strip()] if locations else [""]

    for loc in loc_list:
        base_seed = f"{clean_seed} {loc}".strip() if loc else clean_seed

        if mode == "standard":
            queries.append(base_seed)

        elif mode == "az_suffix":
            queries.append(base_seed)
            for char in ALPHABET:
                queries.append(f"{base_seed} {char}")

        elif mode == "az_prefix":
            queries.append(base_seed)
            for char in ALPHABET:
                queries.append(f"{char} {base_seed}")

        elif mode == "numbers":
            queries.append(base_seed)
            for num in NUMBER_MODIFIERS:
                queries.append(f"{base_seed} {num}")

        elif mode == "questions":
            queries.append(base_seed)
            for q in QUESTION_MODIFIERS:
                queries.append(f"{q} {base_seed}")

        elif mode == "prepositions":
            queries.append(base_seed)
            for p in PREPOSITION_MODIFIERS:
                queries.append(f"{base_seed} {p}")

        elif mode == "commercial":
            queries.append(base_seed)
            for comm in COMMERCIAL_MODIFIERS:
                queries.append(f"{base_seed} {comm}")

        elif mode == "deep_harvest":
            # Complete suite: seed + A-Z + numbers + questions + prepositions + commercial
            queries.append(base_seed)
            for char in ALPHABET:
                queries.append(f"{base_seed} {char}")
            for num in NUMBER_MODIFIERS:
                queries.append(f"{base_seed} {num}")
            for q in QUESTION_MODIFIERS:
                queries.append(f"{q} {base_seed}")
            for p in PREPOSITION_MODIFIERS:
                queries.append(f"{base_seed} {p}")
            for comm in COMMERCIAL_MODIFIERS:
                queries.append(f"{base_seed} {comm}")

    # Deduplicate queries while preserving order
    seen = set()
    deduped_queries = []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            deduped_queries.append(q)

    return deduped_queries


def execute_harvest(seed, mode="az_suffix", locations=None, negative_words=None, 
                    gl="in", hl="en", progress_callback=None, stop_check=None):
    """
    Executes an expansion run across queries with rate-limiting, intent detection, 
    clustering, deduplication against existing database, and batch writing.
    """
    init_csv()
    
    # Load existing keywords to guarantee no duplicates
    existing_kws = set()
    for row in load_all_keywords():
        if row.get("Keyword"):
            existing_kws.add(row["Keyword"].strip().lower())

    queries = generate_queries_for_mode(seed, mode, locations)
    total_queries = len(queries)
    
    negatives = set(DEFAULT_NEGATIVES)
    if negative_words:
        for w in negative_words:
            if w.strip():
                negatives.add(w.strip().lower())

    batch_buffer = []
    added_count = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, query in enumerate(queries, 1):
        if stop_check and stop_check():
            break

        if progress_callback:
            progress_callback({
                "current_index": idx,
                "total_queries": total_queries,
                "current_query": query,
                "added_count": added_count,
                "percent": int((idx / total_queries) * 100)
            })

        suggestions = fetch_google_autocomplete(query, gl=gl, hl=hl)

        for sug in suggestions:
            clean_sug = sug.strip()
            sug_lower = clean_sug.lower()

            # Check if already seen or in database
            if sug_lower in existing_kws:
                continue

            # Check negative keywords filter
            has_negative = any(neg in sug_lower for neg in negatives)
            if has_negative:
                continue

            # Determine properties
            intent = classify_intent(clean_sug)
            cluster = detect_cluster(clean_sug, seed)
            word_count = len(clean_sug.split())
            loc_str = ", ".join(locations) if locations else "General"

            new_row = [
                clean_sug,
                "Google Autocomplete",
                query,
                now_str,
                intent,
                cluster,
                loc_str,
                word_count,
                "Unverified",
                "Medium",
                ""
            ]

            batch_buffer.append(new_row)
            existing_kws.add(sug_lower)
            added_count += 1

        # Periodic flush to CSV every 15 queries to keep disk in sync
        if len(batch_buffer) >= 20:
            save_keywords_batch(batch_buffer)
            batch_buffer.clear()

        # Friendly pacing to avoid IP throttle
        time.sleep(0.12)

    # Final flush
    if batch_buffer:
        save_keywords_batch(batch_buffer)
        batch_buffer.clear()

    return added_count
