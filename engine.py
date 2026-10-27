import csv
import os
import sys
import re
import time
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    try:
        import subprocess
        print("[*] Required dependency 'requests' is missing. Auto-installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        import requests
        from requests.adapters import HTTPAdapter
        print("[OK] Requests installed successfully!")
    except Exception as e:
        print(f"[!] Warning: Could not import or auto-install 'requests': {e}")
        print("    Please run: pip install requests")
        requests = None
        HTTPAdapter = None

DEFAULT_CSV = "keywords.csv"
ACTIVE_SHEET_FILE = os.path.join(BASE_DIR, "active_sheet.txt")
csv_lock = Lock()

def _resolve_sheet_path(filename=None):
    """Resolves sheet filename relative to BASE_DIR if relative."""
    if not filename:
        filename = get_active_sheet()
    if os.path.isabs(filename):
        return filename
    return os.path.join(BASE_DIR, filename)

COLUMNS = [
    "Keyword", "Collection Date", "Location", 
    "Word Count", "Validation Status", "Priority", "Target Page", "Bookmarked"
]

DEFAULT_NEGATIVES = {"job", "jobs", "salary", "vacancy", "pdf", "course", "free download", "app download", "recruitment", "login"}

QUESTION_MODIFIERS = [
    "how to", "what is", "why", "where to", "when to", 
    "which is better", "can we", "is it good", "does", "how much does"
]

DEEP_QUESTION_PREFIXES = [
    "how to", "how much", "how long", "how does", "what is", "what are",
    "which", "why is", "why do", "where to", "where can i", "when to",
    "who makes", "who does", "can i", "can you", "should i", "is it better to"
]

DEEP_QUESTION_SUFFIXES = [
    "problems", "issues", "mistakes", "tips", "ideas", "guide",
    "checklist", "meaning", "examples", "benefits", "alternatives", "faq"
]

PREPOSITION_MODIFIERS = [
    "for", "with", "without", "vs", "versus", "or", "near", "under", "in", "like"
]

COMMERCIAL_MODIFIERS = [
    "cost", "price", "rates per sq ft", "price list", "contractor", 
    "service", "near me", "best", "top", "quote", "estimate", "charges", "showroom", "maker", "installation"
]

SEMANTIC_PREFIXES = [
    "best", "top", "top 10", "cheap", "affordable", "modern", "custom",
    "small", "luxury", "professional", "local", "buy", "hire"
]

SEMANTIC_SUFFIXES = [
    "vs", "versus", "or", "alternative", "compared to", "review", "reviews",
    "pros and cons", "worth it", "price", "cost", "rate", "budget", "charges",
    "quote", "near me", "shop", "company", "service", "contractor", "dealer",
    "online", "quality", "brands", "types", "design", "ideas"
]

WILDCARD_GAP_TEMPLATES = [
    "_ {seed}",
    "best _ {seed}",
    "top _ {seed}",
    "how to _ {seed}",
    "{seed} for _",
    "{seed} with _",
    "{seed} without _",
    "{seed} in _",
    "{seed} near _",
    "{seed} under _",
    "{seed} vs _",
    "{seed} like _"
]

NUMBER_MODIFIERS = [str(n) for n in range(0, 10)]
ALPHABET = list(string.ascii_lowercase)
HIGH_YIELD_LETTERS = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "l", "m", "n", "o", "p", "r", "s", "t", "w"]

# Persistent connection-pooled HTTP session for fast, low-latency autocomplete fetches
if requests is not None:
    _http_session = requests.Session()
    if HTTPAdapter:
        _adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=1)
        _http_session.mount("https://", _adapter)
        _http_session.mount("http://", _adapter)
    _http_session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })
else:
    _http_session = None

_autocomplete_cache = {}
_cache_lock = Lock()


def parse_seed_list(seed_input):
    """
    Splits comma-separated seed input (e.g. 'word1 , word2 , word3')
    into clean, independent, deduplicated seed phrases.
    """
    if not seed_input:
        return []
    if isinstance(seed_input, (list, tuple)):
        raw_parts = seed_input
    else:
        raw_parts = re.split(r',+', str(seed_input))
    seeds = []
    seen = set()
    for part in raw_parts:
        clean = " ".join(str(part).strip().split())
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            seeds.append(clean)
    return seeds


def suggestion_matches_seed(suggestion, parent_seed):
    """
    Verifies that a real Google Autocomplete suggestion genuinely contains
    or matches the target seed word(s), filtering out unrelated autocomplete drift.
    """
    if not parent_seed:
        return True
    sug_low = suggestion.strip().lower()
    seed_low = parent_seed.strip().lower()
    if seed_low in sug_low:
        return True

    # Token-level stem check for multi-word or inflected matches (e.g. kitchen/kitchens, carpenter/carpentry)
    stop_tokens = {"in", "on", "at", "to", "for", "of", "the", "a", "an", "and", "or", "with", "near", "me", "by", "vs", "versus"}
    seed_tokens = [t for t in re.findall(r'[a-z0-9]+', seed_low) if t not in stop_tokens]
    if not seed_tokens:
        seed_tokens = re.findall(r'[a-z0-9]+', seed_low)

    if not seed_tokens:
        return True

    matched_tokens = 0
    for tok in seed_tokens:
        stem = tok[:max(3, len(tok) - 2)] if len(tok) >= 5 else tok
        if stem in sug_low:
            matched_tokens += 1

    # For 1-2 word seeds: require all meaningful tokens to match
    # For 3+ word seeds: matching at least 60% of tokens (min 2) is a genuine match
    if len(seed_tokens) <= 2:
        return matched_tokens == len(seed_tokens)
    else:
        threshold = max(2, int(len(seed_tokens) * 0.6))
        return matched_tokens >= threshold


def get_active_sheet():
    """Gets the filename of the active local sheet."""
    if os.path.exists(ACTIVE_SHEET_FILE):
        try:
            with open(ACTIVE_SHEET_FILE, "r", encoding="utf-8") as f:
                name = f.read().strip()
                if name and (os.path.exists(name) or os.path.exists(_resolve_sheet_path(name))):
                    return os.path.basename(name)
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
        search_dir = BASE_DIR if os.path.exists(BASE_DIR) else "."
        for f in os.listdir(search_dir):
            if f.endswith(".csv") and not f.startswith("."):
                sheets.append(f)
    except:
        pass
    if DEFAULT_CSV not in sheets and os.path.exists(_resolve_sheet_path(DEFAULT_CSV)):
        sheets.append(DEFAULT_CSV)
    return sorted(list(set(sheets))) or [DEFAULT_CSV]


def create_new_sheet(name):
    """Creates a new CSV sheet with standard headers and sets it as active."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip()).strip('_')
    if not clean:
        clean = f"keywords_{int(time.time())}"
    filename = f"{clean}.csv"
    init_csv(filename)
    set_active_sheet(filename)
    return filename


_verified_sheets = set()


def init_csv(filename=None):
    """Initializes the CSV database with standard columns if not present."""
    sheet_name = filename or get_active_sheet()
    target_file = _resolve_sheet_path(sheet_name)
    if sheet_name in _verified_sheets and os.path.exists(target_file):
        return
    with csv_lock:
        if not os.path.exists(target_file):
            with open(target_file, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(COLUMNS)
            _verified_sheets.add(sheet_name)
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
                _verified_sheets.add(sheet_name)
            except Exception as e:
                print(f"[Engine] Header check error on {target_file}: {e}")


def fetch_google_autocomplete(query, gl="in", hl="en", cursor_pos=None):
    """
    Queries Google Autocomplete for real keyword suggestions.
    Uses persistent connection pooling and in-memory caching for high speed.
    """
    cache_key = (query.strip().lower(), gl, hl, cursor_pos)
    with _cache_lock:
        if cache_key in _autocomplete_cache:
            return list(_autocomplete_cache[cache_key])

    url = f"https://suggestqueries.google.com/complete/search?client=firefox&gl={gl}&hl={hl}&q={requests.utils.quote(query)}"
    if cursor_pos is not None:
        url += f"&cp={int(cursor_pos)}"

    try:
        response = _http_session.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if len(data) > 1 and isinstance(data[1], list):
                results = [
                    sug.strip() for sug in data[1]
                    if sug and isinstance(sug, str) and not sug.strip().startswith("http")
                ]
                with _cache_lock:
                    if len(_autocomplete_cache) > 5000:
                        _autocomplete_cache.clear()
                    _autocomplete_cache[cache_key] = results
                return results
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
    """Assigns a topic cluster based on universal query patterns."""
    kw = keyword.lower()
    if any(w in kw for w in ["price", "cost", "rate", "rates", "budget", "pricing", "charges", "cheap", "expensive", "fee"]):
        return "Pricing & Cost"
    if any(w in kw for w in ["best", "top", "review", "reviews", "vs", "versus", "compare", "comparison", "alternative"]):
        return "Reviews & Comparison"
    if any(w in kw for w in ["how to", "guide", "tutorial", "tips", "diy", "process", "step by step", "ideas", "meaning"]):
        return "Guides & How-To"
    if any(w in kw for w in ["near me", "service", "company", "contractor", "agency", "provider", "shop", "store"]):
        return "Services & Local"
    if any(w in kw for w in ["tools", "software", "app", "online", "platform", "free"]):
        return "Tools & Platforms"
    
    return seed.title() if seed else "General"


def load_all_keywords(sheet_file=None):
    """Reads all rows from the selected sheet."""
    target_file = _resolve_sheet_path(sheet_file or get_active_sheet())
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
    target_file = _resolve_sheet_path(sheet_file or get_active_sheet())
    init_csv(target_file)
    with csv_lock:
        with open(target_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for r in new_rows:
                writer.writerow(r)
    return len(new_rows)


def toggle_bookmark_in_csv(keyword_text, sheet_file=None):
    """Toggles bookmark status (1 or 0) for a given keyword."""
    target_file = _resolve_sheet_path(sheet_file or get_active_sheet())
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
    target_file = _resolve_sheet_path(sheet_file or get_active_sheet())
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
    target_file = _resolve_sheet_path(sheet_file or get_active_sheet())
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


def _build_queries_for_single_seed(base_seed, mode):
    """Generates query strings for a single seed phrase under the specified mode/algorithm."""
    q_list = []

    if mode == "standard":
        q_list.append(base_seed)
        q_list.append(f"{base_seed} ")

    elif mode == "az_suffix":
        q_list.append(base_seed)
        for char in ALPHABET:
            q_list.append(f"{base_seed} {char}")

    elif mode == "az_prefix":
        q_list.append(base_seed)
        for char in ALPHABET:
            q_list.append(f"{char} {base_seed}")

    elif mode == "numbers":
        q_list.append(base_seed)
        for num in NUMBER_MODIFIERS:
            q_list.append(f"{base_seed} {num}")

    elif mode == "questions":
        q_list.append(base_seed)
        for q in QUESTION_MODIFIERS:
            q_list.append(f"{q} {base_seed}")

    elif mode == "prepositions":
        q_list.append(base_seed)
        for p in PREPOSITION_MODIFIERS:
            q_list.append(f"{base_seed} {p}")

    elif mode == "commercial":
        q_list.append(base_seed)
        for comm in COMMERCIAL_MODIFIERS:
            q_list.append(f"{base_seed} {comm}")

    elif mode == "deep_harvest":
        q_list.append(base_seed)
        for char in ALPHABET:
            q_list.append(f"{base_seed} {char}")
        for num in NUMBER_MODIFIERS:
            q_list.append(f"{base_seed} {num}")
        for q in QUESTION_MODIFIERS:
            q_list.append(f"{q} {base_seed}")
        for p in PREPOSITION_MODIFIERS:
            q_list.append(f"{base_seed} {p}")
        for comm in COMMERCIAL_MODIFIERS:
            q_list.append(f"{base_seed} {comm}")

    # ==================== ADVANCED DISCOVERY ALGORITHMS (algos) ====================
    elif mode == "algo_multiseed":
        # High-efficiency multi-word smart scan: suffix stems + prefix qualifiers + commercial/question stems
        q_list.append(base_seed)
        for char in ALPHABET:
            q_list.append(f"{base_seed} {char}")
        for pref in SEMANTIC_PREFIXES[:8]:
            q_list.append(f"{pref} {base_seed}")
        for suf in ["price", "cost", "near me", "best", "ideas", "design", "for", "with", "vs"]:
            q_list.append(f"{base_seed} {suf}")
        for q in ["how to", "what is", "which", "best"]:
            q_list.append(f"{q} {base_seed}")

    elif mode == "algo_recursive":
        # Pass-1 stems for Recursive Snowball Graph (Pass-2 runs dynamically on discovered real roots)
        q_list.append(base_seed)
        for char in ALPHABET:
            q_list.append(f"{base_seed} {char}")
        for p in ["for", "with", "in", "near", "vs", "price", "cost", "best"]:
            q_list.append(f"{base_seed} {p}")

    elif mode == "algo_wildcard":
        # Wildcard & Gap Fill algorithm: prefix, mid-phrase infix, and suffix gap completions
        q_list.append(base_seed)
        for tmpl in WILDCARD_GAP_TEMPLATES:
            q_list.append(tmpl.format(seed=base_seed))
        words = base_seed.split()
        if len(words) >= 2:
            for i in range(1, len(words)):
                left = " ".join(words[:i])
                right = " ".join(words[i:])
                q_list.append(f"{left} _ {right}")
                for ch in ["a", "b", "c", "f", "i", "l", "m", "p", "s", "w"]:
                    q_list.append(f"{left} {ch} {right}")
        for ch in HIGH_YIELD_LETTERS:
            q_list.append(f"_ {base_seed} {ch}")
            q_list.append(f"{base_seed} {ch}")

    elif mode == "algo_semantic":
        # Semantic & Buyer Matrix algorithm
        q_list.append(base_seed)
        for pref in SEMANTIC_PREFIXES:
            q_list.append(f"{pref} {base_seed}")
        for suf in SEMANTIC_SUFFIXES:
            q_list.append(f"{base_seed} {suf}")
        for ch in HIGH_YIELD_LETTERS:
            q_list.append(f"{base_seed} {ch}")

    elif mode == "algo_questions_deep":
        # AnswerThePublic-style Deep Question & Forum Miner
        q_list.append(base_seed)
        for qp in DEEP_QUESTION_PREFIXES:
            q_list.append(f"{qp} {base_seed}")
        for qs in DEEP_QUESTION_SUFFIXES:
            q_list.append(f"{base_seed} {qs}")
        for p in PREPOSITION_MODIFIERS:
            q_list.append(f"{base_seed} {p}")

    elif mode == "algo_ultra":
        # Ultra Deep All-In-One (A-Z Suffix + A-Z Prefix + Numbers + Wildcards + Semantic + Questions + Recursive)
        q_list.append(base_seed)
        for char in ALPHABET:
            q_list.append(f"{base_seed} {char}")
        for char in HIGH_YIELD_LETTERS:
            q_list.append(f"{char} {base_seed}")
        for num in NUMBER_MODIFIERS:
            q_list.append(f"{base_seed} {num}")
        for tmpl in WILDCARD_GAP_TEMPLATES:
            q_list.append(tmpl.format(seed=base_seed))
        words = base_seed.split()
        if len(words) >= 2:
            q_list.append(f"{words[0]} _ {' '.join(words[1:])}")
        for pref in SEMANTIC_PREFIXES:
            q_list.append(f"{pref} {base_seed}")
        for suf in SEMANTIC_SUFFIXES:
            q_list.append(f"{base_seed} {suf}")
        for qp in DEEP_QUESTION_PREFIXES:
            q_list.append(f"{qp} {base_seed}")
        for qs in DEEP_QUESTION_SUFFIXES:
            q_list.append(f"{base_seed} {qs}")

    else:
        # Fallback to az_suffix
        q_list.append(base_seed)
        for char in ALPHABET:
            q_list.append(f"{base_seed} {char}")

    return q_list


def generate_query_tasks(seed_input, mode="az_suffix", locations=None):
    """
    Splits comma-separated seeds (e.g. 'word1 , word2 , word3') and builds
    a deduplicated list of (query_string, parent_seed) tasks so each seed word
    is researched independently.
    """
    seeds = parse_seed_list(seed_input)
    if not seeds and str(seed_input).strip():
        seeds = [str(seed_input).strip()]

    loc_list = [l.strip() for l in locations if l.strip()] if locations else [""]
    tasks = []
    seen = set()

    for single_seed in seeds:
        for loc in loc_list:
            base_seed = f"{single_seed} {loc}".strip() if loc else single_seed
            raw_queries = _build_queries_for_single_seed(base_seed, mode)
            for q in raw_queries:
                key = (q.lower(), single_seed.lower())
                if key not in seen:
                    seen.add(key)
                    tasks.append((q, single_seed))

    # Cross-seed pairwise combinations for multi-seed runs
    if len(seeds) >= 2 and mode in ("algo_multiseed", "algo_ultra", "algo_semantic", "deep_harvest"):
        import itertools
        for s1, s2 in itertools.combinations(seeds, 2):
            cross_queries = [
                f"{s1} vs {s2}",
                f"{s1} and {s2}",
                f"{s1} or {s2}",
                f"{s1} with {s2}",
                f"{s1} {s2}"
            ]
            for cq in cross_queries:
                for target_seed in (s1, s2):
                    key = (cq.lower(), target_seed.lower())
                    if key not in seen:
                        seen.add(key)
                        tasks.append((cq, target_seed))

    return tasks


def generate_queries_for_mode(seed, mode="az_suffix", locations=None):
    """Backwards-compatible helper returning flat list of query strings."""
    return [q for q, _ in generate_query_tasks(seed, mode, locations)]


def execute_harvest(seed, mode="az_suffix", locations=None, negative_words=None, 
                    gl="in", hl="en", progress_callback=None, stop_check=None, sheet_file=None):
    """
    Executes a high-speed, concurrent keyword discovery run across one or multiple
    comma-separated seed words, verifying real Google Autocomplete suggestions
    and supporting recursive snowball expansion.
    """
    target_file = sheet_file or get_active_sheet()
    init_csv(target_file)
    
    existing_kws = set()
    for row in load_all_keywords(target_file):
        if row.get("Keyword"):
            existing_kws.add(row["Keyword"].strip().lower())

    tasks = generate_query_tasks(seed, mode, locations)
    is_recursive_mode = mode in ("algo_recursive", "algo_ultra")
    total_queries = len(tasks)
    if total_queries == 0:
        return 0
    
    negatives = set(DEFAULT_NEGATIVES)
    if negative_words:
        for w in negative_words:
            if w.strip():
                negatives.add(w.strip().lower())

    batch_buffer = []
    added_count = 0
    completed_count = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    loc_str = ", ".join(locations) if locations else "General"
    discovered_by_seed = {}
    state_lock = Lock()

    def process_suggestions(suggestions, parent_seed):
        nonlocal added_count
        new_for_this_query = []
        for sug in suggestions:
            clean_sug = " ".join(sug.strip().split())
            if not clean_sug:
                continue
            sug_lower = clean_sug.lower()

            if sug_lower in existing_kws:
                continue

            if not suggestion_matches_seed(clean_sug, parent_seed):
                continue

            if any(neg in sug_lower for neg in negatives):
                continue

            word_count = len(clean_sug.split())
            new_row = [
                clean_sug,
                now_str,
                loc_str,
                word_count,
                "Unverified",
                "Medium",
                "",
                "0"
            ]

            batch_buffer.append(new_row)
            existing_kws.add(sug_lower)
            added_count += 1
            new_for_this_query.append(clean_sug)

        if parent_seed not in discovered_by_seed:
            discovered_by_seed[parent_seed] = []
        discovered_by_seed[parent_seed].extend(new_for_this_query)

        if len(batch_buffer) >= 35:
            save_keywords_batch(list(batch_buffer), target_file)
            batch_buffer.clear()

    def run_task_batch(task_list, stage_offset=0, grand_total=None):
        nonlocal completed_count
        effective_total = grand_total or len(task_list)
        chunk_size = 18

        with ThreadPoolExecutor(max_workers=6) as executor:
            for start_idx in range(0, len(task_list), chunk_size):
                if stop_check and stop_check():
                    break
                chunk = task_list[start_idx:start_idx + chunk_size]
                future_to_task = {}
                for q_str, p_seed in chunk:
                    cp = q_str.index("_") if "_" in q_str else None
                    clean_q = q_str.replace("_", " ").strip() if "_" in q_str else q_str
                    fut = executor.submit(fetch_google_autocomplete, clean_q, gl, hl, cp)
                    future_to_task[fut] = (q_str, p_seed)

                for fut in as_completed(future_to_task):
                    if stop_check and stop_check():
                        break
                    q_str, p_seed = future_to_task[fut]
                    sugs = fut.result() or []
                    with state_lock:
                        completed_count += 1
                        process_suggestions(sugs, p_seed)
                        if progress_callback:
                            pct = min(99, int((completed_count / max(1, effective_total)) * 100))
                            progress_callback({
                                "current_index": completed_count,
                                "total_queries": effective_total,
                                "current_query": f"[{p_seed}] {q_str}",
                                "added_count": added_count,
                                "percent": pct
                            })
                time.sleep(0.04)

    # Pass 1: Execute primary query tasks
    estimated_total = int(total_queries * 1.25) if is_recursive_mode else total_queries
    run_task_batch(tasks, stage_offset=0, grand_total=estimated_total)

    # Pass 2: Recursive Snowball Expansion on top real discovered Google stems
    if is_recursive_mode and not (stop_check and stop_check()):
        recursive_tasks = []
        seen_rec = {q.lower() for q, _ in tasks}
        for p_seed, disc_list in discovered_by_seed.items():
            # Pick shortest high-signal discovered phrases (2 to 4 words) as snowball roots
            candidates = sorted(
                [d for d in disc_list if 2 <= len(d.split()) <= 4],
                key=lambda x: len(x)
            )[:6]
            for root_kw in candidates:
                for suffix in ["", "a", "c", "f", "m", "p", "s", "for", "in", "price", "near me"]:
                    rq = f"{root_kw} {suffix}".strip()
                    if rq.lower() not in seen_rec:
                        seen_rec.add(rq.lower())
                        recursive_tasks.append((rq, p_seed))

        if recursive_tasks:
            final_total = completed_count + len(recursive_tasks)
            run_task_batch(recursive_tasks, stage_offset=completed_count, grand_total=final_total)

    with state_lock:
        if batch_buffer:
            save_keywords_batch(list(batch_buffer), target_file)
            batch_buffer.clear()

    if progress_callback:
        progress_callback({
            "current_index": completed_count,
            "total_queries": max(1, completed_count),
            "current_query": "Completed",
            "added_count": added_count,
            "percent": 100
        })

    return added_count
