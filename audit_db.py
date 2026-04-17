import json
import re

db_path = 'dota_sets_db.json'
with open(db_path, 'r', encoding='utf-8') as f:
    db = json.load(f)

print(f"--- Database Audit (Total: {len(db)} sets) ---")

# 1. Check for empty sets (excluding known 1-item items)
# Known couriers/singles that should be empty:
singles = ['Faceless Rex', 'Atrophic Skitterwing', 'Hakobi and Tenneko']
empty_sets = [k for k, v in db.items() if not v and k not in singles]
if empty_sets:
    print(f"WARNING: Found {len(empty_sets)} unexpectedly empty sets:")
    for s in empty_sets[:10]: print(f"  - {s}")
else:
    print("SUCCESS: No unexpectedly empty sets found.")

# 2. Check for boilerplate in part names
boilerplate = ['liquipedia', 'wiki', 'edit', 'русский', '–']
found_bad = []
for set_name, parts in db.items():
    for p in parts:
        if any(b in p.lower() for b in boilerplate):
            # Exception for hyphen which is part of some names
            if '–' in p and 'русский' not in p: continue 
            found_bad.append(f"{set_name} -> {p}")

if found_bad:
    print(f"WARNING: Found {len(found_bad)} parts with potential boilerplate:")
    for b in found_bad[:10]: print(f"  - {b}")
else:
    print("SUCCESS: No boilerplate found in part names.")

# 3. Check for very short part lists (1-2 items) - might be incomplete
short_sets = [k for k, v in db.items() if len(v) > 0 and len(v) < 3 and k not in singles]
if short_sets:
    print(f"INFO: Found {len(short_sets)} sets with only 1-2 parts (check if correct):")
    for s in short_sets[:10]: print(f"  - {s} ({len(db[s])} parts)")

print("--- Audit Complete ---")
