import os
import json
import time
import urllib.request
import urllib.parse
import re
import html
import traceback

NAMES_FILE = "names_example.txt"
DB_FILE = "dota_sets_db.json"
USER_AGENT = 'DotaSetMatcher/1.0'

def fetch_set_parts_robust(name):
    urls = [
        f"https://liquipedia.net/dota2/{urllib.parse.quote(name.strip().replace(' ', '_'))}",
        f"https://liquipedia.net/dota2/{urllib.parse.quote(name.strip().replace(' ', '_'))}_Bundle"
    ]
    
    headers = {'User-Agent': USER_AGENT}
    content = None
    
    for url in urls:
        try:
            time.sleep(0.5)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode('utf-8')
                break # Found it
        except urllib.error.HTTPError as e:
            if e.code == 404: continue # Try next URL
            return [], None
        except Exception as e:
            print(f"Error scraping {name} at {url}: {e}", flush=True)
            return [], None
            
    if not content:
        return [], False # Both URLs failed 404

    try:
        parts = set()

        # Strategy 1: Section Header Parsing (Look for Set Items / Equipment / Contains)
        sections = re.split(r'<h[23].*?>(.*?)</h[23]>', content, flags=re.IGNORECASE)
        for i in range(1, len(sections), 2):
            header_text = re.sub(r'<[^>]+>', '', sections[i]).strip().lower()
            body = sections[i+1]
            
            if any(h in header_text for h in ['set items', 'equipment', 'contains']):
                # Extract link titles
                links = re.findall(r'title="([^"]+)"', body)
                for l in links:
                    l = html.unescape(l)
                    # Filter out boilerplate, hero names (usually 1 word), or redirects
                    if 'edit' not in l.lower() and 'Liquipedia' not in l and l.lower() != name.lower() and len(l) < 80:
                         # Heuristic: Items usually have 2+ words or specific keywords
                         if len(l.split()) > 1 or any(x in l.lower() for x in ['of', 'the', 'mask', 'armor', 'weapon', 'head', 'belt', 'sword']):
                            parts.add(l.strip())

        # Strategy 2: Bundle Item Block (Fallback)
        bundle_matches = re.findall(r'<div class="bundle-item-name">.*?<a[^>]*>([^<]+)</a>', content, re.DOTALL)
        for m in bundle_matches:
            parts.add(html.unescape(m).strip())

        # Strategy 3: Significant Word Pattern Fallback
        if not parts:
            words = name.split()
            # Find the most unique word (usually the longest that isn't 'Set', etc.)
            clean_words = [w for w in words if w.lower() not in ['of', 'the', 'set', 'bundle', 'mask', 'armor', 'garb']]
            if clean_words:
                sig_word = max(clean_words, key=len)
                if len(sig_word) > 3:
                    all_links = re.findall(r'title="([^"]+)"', content)
                    for l in all_links:
                        l = html.unescape(l)
                        if sig_word.lower() in l.lower() and l.lower() != name.lower() and "Liquipedia" not in l and len(l) < 80:
                            parts.add(l.strip())

        return sorted(list(parts)), True
    except urllib.error.HTTPError as e:
        if e.code == 404: return [], False
        return [], None
    except Exception as e:
        print(f"Error scraping {name}: {e}")
        return [], None

def main():
    if not os.path.exists(NAMES_FILE):
        print(f"Error: {NAMES_FILE} not found.")
        return

    with open(NAMES_FILE, 'r', encoding='utf-8') as f:
        names = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    db = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            try:
                db = json.load(f)
            except: pass

    to_scrape = [n for n in names if n not in db or not db[n]]
    
    print(f"Total sets: {len(names)}")
    print(f"Already in DB: {len(names) - len(to_scrape)}")
    print(f"To scrape: {len(to_scrape)}")

    try:
        for i, name in enumerate(to_scrape):
            print(f"[{i+1}/{len(to_scrape)}] {name}...", end=" ", flush=True)
            parts, success = fetch_set_parts_robust(name)
            
            if success is not None:
                db[name] = parts
                print(f"Found {len(parts)} parts.", flush=True)
                if (i + 1) % 5 == 0:
                    with open(DB_FILE, 'w', encoding='utf-8') as f:
                        json.dump(db, f, ensure_ascii=False, indent=2)
            else:
                print(f"Failed.", flush=True)
            
    except KeyboardInterrupt:
        print("\nStopping...")

    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
