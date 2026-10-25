import csv
import os
import re
import time
import string
import requests
from datetime import datetime
from threading import Lock

DEFAULT_CSV = "smartwood_keywords.csv"
ACTIVE_SHEET_FILE = "active_sheet.txt"
csv_lock = Lock()

COLUMNS = [
    "Keyword", "Source", "Discovered From", "Collection Date", 
    "Search Intent", "Topic Cluster", "Location", 
    "Word Count", "Validation Status", "Priority", "Target Page", "Bookmarked"
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


def get_active_sheet():
    """Gets the filename of the active local sheet."""
    if os.path.exists(ACTIVE_SHEET_FILE):
        try:
            with open(ACTIVE_SHEET_FILE, "r", encoding="utf-8") as f:
                name = f.read().strip()
                if name and os.path.exists(name):
                    return name
        except:
            pass
    return DEFAULT_CSV


def set_active_sheet(sheet_filename):
    """Sets the active local sheet file."""
    clean_name = os.path.basename(sheet_filename.strip())
    if not clean_name.endswith(".csv"):
        clean_name += ".csv"
    with open(ACTIVE_SHEET_FILE, "w", encoding="utf-8") as f:
        f.write(clean_name)
    init_csv(clean_name)
    return clean_name


def list_available_sheets():
    """Lists all CSV keyword sheets in the project directory."""
    sheets = []
    try:
        for f in os.listdir("."):
            if f.endswith(".csv") and not f.startswith("."):
                sheets.append(f)
    except:
        pass
    if DEFAULT_CSV not in sheets and os.path.exists(DEFAULT_CSV):
        sheets.append(DEFAULT_CSV)
    return sorted(list(set(sheets)))


def create_new_sheet(name):
    """Creates a new CSV sheet with standard headers and sets it as active."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip()).strip('_')
    if not clean:
        clean = f"keywords_{int(time.time())}"
    filename = f"{clean}.csv"
    init_csv(filename)
    set_active_sheet(filename)
    return filename


def init_csv(filename=None):
    """Initializes the CSV database with standard columns if not present."""
    target_file = filename or get_active_sheet()
    with csv_lock:
        if not os.path.exists(target_file):
            with open(target_file, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(COLUMNS)
        else:
            # Ensure Bookmarked column exists in header if missing
            try:
                with open(target_file, mode='r', encoding='utf-8', errors='replace') as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                if header and "Bookmarked" not in header:
                    header.append("Bookmarked")
                    rows = []
                    with open(target_file, mode='r', encoding='utf-8', errors='replace') as f:
                        reader = csv.reader(f)
                        next(reader, None)
                        for r in reader:
                            while len(r) < len(header):
                                r.append("0")
                            rows.append(r)
                    with open(target_file, mode='w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(header)
                        writer.writerows(rows)
            except Exception as e:
                print(f"[Engine] Header check error on {target_file}: {e}")


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
    """Classifies search intent using pattern and token rules."""
    kw = keyword.lower()
    
    transactional_triggers = [
        "cost", "price", "rate", "rates", "charges", "contractor", "service", 
        "services", "near me", "maker", "agency", "firm", "hire", "buy", 
        "shop", "dealers", "supplier", "estimate", "quote", "order"
    ]
    if any(re.search(r'\b' + re.escape(t) + r'\b', kw) for t in transactional_triggers):
        return "Transactional"

    commercial_triggers = [
        "best", "top", "review", "reviews", "vs", "versus", "compare", 
        "comparison", "difference", "which is", "pros and cons", "catalogue", "types of"
    ]
    if any(re.search(r'\b' + re.escape(c) + r'\b', kw) for c in commercial_triggers):
        return "Commercial"

    informational_triggers = [
        "how", "what", "why", "where", "when", "can", "is", "guide", 
        "tips", "ideas", "meaning", "diy", "height", "standard size", "dimensions", "colour combination"
    ]
    if any(re.search(r'\b' + re.escape(i) + r'\b', kw) for i in informational_triggers):
        return "Informational"

    return "Commercial"


def detect_cluster(keyword, seed):
    """Assigns a topic cluster based on common interior and trade entities."""
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


def load_all_keywords(sheet_file=None):
    """Reads all rows from the selected sheet."""
    target_file = sheet_file or get_active_sheet()
    init_csv(target_file)
    rows = []
    with csv_lock:
        if os.path.exists(target_file):
            with open(target_file, mode='r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    # ensure Bookmarked key exists
                    if "Bookmarked" not in r:
                        r["Bookmarked"] = "0"
                    rows.append(r)
    return rows


def save_keywords_batch(new_rows, sheet_file=None):
    """Appends multiple keyword rows safely to the sheet."""
    if not new_rows:
        return 0
    target_file = sheet_file or get_active_sheet()
    init_csv(target_file)
    with csv_lock:
        with open(target_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for r in new_rows:
                writer.writerow(r)
    return len(new_rows)


def toggle_bookmark_in_csv(keyword_text, sheet_file=None):
    """Toggles bookmark status (1 or 0) for a given keyword."""
    target_file = sheet_file or get_active_sheet()
    init_csv(target_file)
    new_state = False
    with csv_lock:
        if not os.path.exists(target_file):
            return False
        with open(target_file, mode='r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                return False
            if "Bookmarked" not in headers:
                headers.append("Bookmarked")
            bm_idx = headers.index("Bookmarked")
            rows = []
            for row in reader:
                while len(row) < len(headers):
                    row.append("0")
                if row and row[0].strip().lower() == keyword_text.strip().lower():
                    cur = row[bm_idx].strip()
                    if cur in ("1", "true", "True", "yes"):
                        row[bm_idx] = "0"
                        new_state = False
                    else:
                        row[bm_idx] = "1"
                        new_state = True
                rows.append(row)
        
        with open(target_file, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
            
    return new_state


def update_row_in_csv(keyword_text, updates, sheet_file=None):
    """Updates fields like Priority, Validation Status, or Target Page for a keyword."""
    target_file = sheet_file or get_active_sheet()
    init_csv(target_file)
    updated = False
    with csv_lock:
        if not os.path.exists(target_file):
            return False
        with open(target_file, mode='r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                return False
            rows = []
            for row in reader:
                if len(row) > 0 and row[0].strip().lower() == keyword_text.strip().lower():
                    for field, val in updates.items():
                        if field in headers:
                            idx = headers.index(field)
                            while len(row) <= idx:
                                row.append("")
                            row[idx] = val
                    updated = True
                rows.append(row)
        
        with open(target_file, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
            
    return updated


def delete_keywords_from_csv(keywords_to_delete, sheet_file=None):
    """Removes a list of keywords from CSV."""
    target_file = sheet_file or get_active_sheet()
    init_csv(target_file)
    del_set = {k.strip().lower() for k in keywords_to_delete}
    deleted_count = 0
    with csv_lock:
        if not os.path.exists(target_file):
            return 0
        with open(target_file, mode='r', encoding='utf-8', errors='replace') as f:
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
                    
        with open(target_file, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(remaining)
            
    return deleted_count


def generate_queries_for_mode(seed, mode="az_suffix", locations=None):
    """Builds the queue of Google Autocomplete queries based on the chosen mode."""
    clean_seed = seed.strip()
    queries = []
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

    seen = set()
    deduped_queries = []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            deduped_queries.append(q)

    return deduped_queries


def execute_harvest(seed, mode="az_suffix", locations=None, negative_words=None, 
                    gl="in", hl="en", progress_callback=None, stop_check=None, sheet_file=None):
    """Executes an expansion run across queries with rate-limiting, deduplication, and writing."""
    target_file = sheet_file or get_active_sheet()
    init_csv(target_file)
    
    existing_kws = set()
    for row in load_all_keywords(target_file):
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

            if sug_lower in existing_kws:
                continue

            has_negative = any(neg in sug_lower for neg in negatives)
            if has_negative:
                continue

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
                "",
                "0"  # Bookmarked = 0 by default
            ]

            batch_buffer.append(new_row)
            existing_kws.add(sug_lower)
            added_count += 1

        if len(batch_buffer) >= 20:
            save_keywords_batch(batch_buffer, target_file)
            batch_buffer.clear()

        time.sleep(0.12)

    if batch_buffer:
        save_keywords_batch(batch_buffer, target_file)
        batch_buffer.clear()

    return added_count
