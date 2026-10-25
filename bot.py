#!/usr/bin/env python3
"""
CLI Bot interface for automated keyword discovery.
Can run standalone or be scheduled.
"""
import sys
from engine import execute_harvest, load_all_keywords

SEED_KEYWORDS = [
    "modular kitchen Navi Mumbai",
    "wardrobe contractor Navi Mumbai",
    "full home renovation Navi Mumbai",
    "carpenter Ghansoli",
    "interior execution Thane"
]

def main():
    seeds = sys.argv[1:] if len(sys.argv) > 1 else SEED_KEYWORDS
    print(f"[*] Starting Keyword Harvester on {len(seeds)} seed queries...")
    total_new = 0

    def on_progress(p):
        sys.stdout.write(f"\r[{p['percent']}%] Query: {p['current_query'][:45]:<45} | Harvested: {p['added_count']}")
        sys.stdout.flush()

    for seed in seeds:
        print(f"\n[+] Processing Seed: '{seed}' (Alphabet Soup Mode)")
        count = execute_harvest(
            seed=seed,
            mode="az_suffix",
            locations=["Navi Mumbai"],
            progress_callback=on_progress
        )
        total_new += count

    print(f"\n\n[✓] Done. Added {total_new} new unique keywords.")
    print(f"[✓] Total database records: {len(load_all_keywords())}")

if __name__ == "__main__":
    main()
