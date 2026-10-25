#!/usr/bin/env python3
"""
CLI Bot interface for automated keyword discovery.
Can run standalone or be scheduled.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine import execute_harvest, load_all_keywords

DEFAULT_SEEDS = [
    "seo tools",
    "cloud storage",
    "digital marketing"
]

def main():
    if len(sys.argv) > 1:
        seeds = sys.argv[1:]
    else:
        print("[*] No seed keywords specified. Usage: python bot.py \"your keyword\"")
        print("[*] Using default example seeds...")
        seeds = DEFAULT_SEEDS

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
            locations=None,
            progress_callback=on_progress
        )
        total_new += count

    print(f"\n\n[✓] Done. Added {total_new} new unique keywords.")
    print(f"[✓] Total database records: {len(load_all_keywords())}")

if __name__ == "__main__":
    main()
