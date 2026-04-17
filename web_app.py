#!/usr/bin/env python3
"""Modern Web UI for Collector's Search: Dota 2 Steam inventory search.

No external dependencies required.
"""

from __future__ import annotations

import argparse
import html
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Any

from inventory_finder import (
    SteamInventoryError,
    build_items,
    fetch_collectorsshop_prices,
    fetch_dota_inventory,
    read_targets,
    resolve_steam_id,
    search_items,
    extract_price_value,
    COLLECTORSSHOP_ITEMS_ENDPOINT,
    COLLECTORSSHOP_DOTA_ROUTE,
    _http_get_json,
    _pick_best_catalog_item,
    _format_price,
)

BASE_DIR = Path(__file__).resolve().parent
NAMES_FILE = BASE_DIR / "names_example.txt"

# Design System & Styles
CSS = """
:root {
  --bg: #0f171a;
  --surface: #1a2428;
  --panel: #222d32;
  --border: #2e3c43;
  --ink: #e0e6e8;
  --ink-muted: #8fa3ad;
  --accent: #10b981;
  --accent-glow: rgba(16, 185, 129, 0.2);
  --danger: #ef4444;
  --gold: #f59e0b;
  --purple: #8b5cf6;
  --shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.5);
  --font: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  font-family: var(--font);
  color: var(--ink);
  background: var(--bg);
  background-image: 
    radial-gradient(circle at 0% 0%, rgba(16, 185, 129, 0.05) 0%, transparent 50%),
    radial-gradient(circle at 100% 100%, rgba(139, 92, 246, 0.05) 0%, transparent 50%);
  padding: 40px 20px;
  line-height: 1.5;
}

.wrap {
  max-width: 1100px;
  margin: 0 auto;
}

header {
  text-align: center;
  margin-bottom: 40px;
}

h1 {
  font-size: 2.5rem;
  font-weight: 800;
  margin: 0 0 12px;
  background: linear-gradient(135deg, #10b981, #34d399);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.02em;
}

.sub {
  color: var(--ink-muted);
  font-size: 1.1rem;
}

.search-box {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 30px;
  box-shadow: var(--shadow);
  margin-bottom: 40px;
  backdrop-filter: blur(10px);
}

form {
  display: grid;
  gap: 20px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--ink-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

input[type="text"], select {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  color: var(--ink);
  font-size: 1rem;
  transition: border-color 0.2s, box-shadow 0.2s;
}

input[type="text"]:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-glow);
}

.form-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 20px;
}

.controls {
  display: flex;
  align-items: center;
  gap: 20px;
}

.check-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 0.95rem;
  user-select: none;
}

button {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 12px;
  padding: 14px 28px;
  font-size: 1rem;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.2s, filter 0.2s;
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}

button:hover {
  filter: brightness(1.1);
  transform: translateY(-2px);
}

button:active {
  transform: translateY(0);
}

.error {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--danger);
  color: var(--danger);
  border-radius: 12px;
  padding: 16px;
  margin-top: 20px;
  font-weight: 600;
}

.item.is-bundle {
  background: var(--accent-glow);
  border: 1px solid var(--accent);
  box-shadow: 0 0 15px var(--accent-glow);
}

.bundle-tag {
  background: var(--accent);
  color: #fff;
  font-size: 0.65rem;
  font-weight: 800;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  margin-top: 4px;
}
#loading-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 26, 0.8);
  backdrop-filter: blur(8px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  visibility: hidden;
  opacity: 0;
  transition: opacity 0.3s, visibility 0.3s;
}

#loading-overlay.visible {
  visibility: visible;
  opacity: 1;
}

.spinner {
  width: 64px;
  height: 64px;
  border: 4px solid var(--accent-glow);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 1.25rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.05em;
}

.result-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 24px;
}

.stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.chip {
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: 99px;
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  transition: border-color 0.2s, background-color 0.2s;
}
a.chip:hover {
  border-color: var(--accent);
  background: var(--surface);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
}

.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  transition: transform 0.2s, border-color 0.2s;
  position: relative;
  overflow: hidden;
}

.card:hover {
  border-color: var(--ink-muted);
  transform: translateY(-4px);
}

.card-header {
  margin-bottom: 20px;
}

.target-name {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0 0 8px;
  color: var(--ink);
}

.price {
  font-size: 0.9rem;
  color: var(--gold);
  font-weight: 600;
  display: flex;
  flex-direction: column; /* Changed to column to stack prices */
  gap: 2px;
}

.price-unit {
  font-size: 0.75rem;
  color: var(--ink-muted);
  font-weight: 400;
}

.item-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--surface);
  padding: 10px;
  border-radius: 12px;
  font-size: 0.875rem;
}

.item-img {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: var(--bg);
  object-fit: cover;
}

.item-info {
  display: flex;
  flex-direction: column;
}

.set-count {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.item-name {
  font-weight: 600;
  line-height: 1.2;
}

.item-rarity {
  font-size: 0.75rem;
  color: var(--ink-muted);
  text-transform: uppercase;
  margin-top: 2px;
}

.item-amount {
  margin-left: auto;
  background: var(--border);
  color: var(--ink);
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 700;
}

.item.missing {
  opacity: 0.4;
  filter: grayscale(1);
  background: transparent;
  border: 1px dashed var(--border);
}

.card[data-full="false"] {
  border-style: dashed;
}

/* Hide partials by default if not toggled */
body:not(.show-partials) .card[data-full="false"] {
  display: none !important;
}

.toggle-partials {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: 99px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--ink-muted);
  transition: all 0.2s;
}

.toggle-partials:hover {
  border-color: var(--accent);
  color: var(--ink);
}

.toggle-partials.active {
  background: var(--accent-glow);
  border-color: var(--accent);
  color: var(--accent);
}

@media (max-width: 600px) {
  .form-footer { flex-direction: column; align-items: stretch; }
  .controls { flex-direction: column; align-items: flex-start; }
  .grid { grid-template-columns: 1fr; }
  .result-controls { flex-direction: column; align-items: stretch; }
}

/* Scrollbar */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--ink-muted); }
"""

def fetch_rich_prices(targets: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch prices and numeric values for sorting."""
    data = {}
    unique_targets = list(dict.fromkeys([t.strip() for t in targets if t.strip()]))
    
    for target in unique_targets:
        try:
            payload = _http_get_json(
                COLLECTORSSHOP_ITEMS_ENDPOINT,
                params={
                    "game": COLLECTORSSHOP_DOTA_ROUTE,
                    "name": target,
                    "page": "1",
                },
            )
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                data[target] = {"label": "n/a", "value": 0}
                continue
            
            best_item = _pick_best_catalog_item(target, items)
            if not best_item:
                data[target] = {"label": "n/a", "value": 0}
                continue
                
            amount = extract_price_value(best_item)
            if amount is None:
                data[target] = {"label": "n/a", "value": 0}
                continue
                
            currency = str(payload.get("currency", "rub"))
            label = _format_price(amount, currency)
            if best_item.get("stock") is False:
                label += " (нет в наличии)"
            
            data[target] = {"label": label, "value": amount}
        except Exception:
            data[target] = {"label": "n/a", "value": 0}
    return data

def render_page(
    *,
    names_file: str,
    inventory_url: str = "",
    error: str = "",
    result: Optional[Dict[str, Any]] = None,
) -> str:
    inventory_url_safe = html.escape(inventory_url)
    names_file_safe = html.escape(names_file)
    
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""

    result_html = ""
    if result:
        cards_html = ""
        for item_data in result["matches"]:
            # Group items by name and icon to show combined quantities (x2, x3...)
            grouped_items = {}
            for itm in item_data["items"]:
                key = (itm.display_name, itm.icon_url, itm.rarity_name, itm.rarity_color, itm.name_color)
                if key not in grouped_items:
                    grouped_items[key] = {
                        "display_name": itm.display_name,
                        "icon_url": itm.icon_url,
                        "rarity_name": itm.rarity_name,
                        "rarity_color": itm.rarity_color,
                        "name_color": itm.name_color,
                        "amount": 0
                    }
                grouped_items[key]["amount"] += itm.amount

            items_html = ""
            for itm in grouped_items.values():
                is_bundle = itm['display_name'].lower() == item_data['target'].lower()
                bundle_class = "is-bundle" if is_bundle else ""
                bundle_tag = '<div class="bundle-tag">БАНДЛ</div>' if is_bundle else ""
                
                rarity_style = f"color: #{itm['rarity_color']};" if itm['rarity_color'] else ""
                name_style = f"color: #{itm['name_color']}; font-weight: 700;" if itm['name_color'] else ""
                
                items_html += f"""
                <div class="item {bundle_class}">
                  <img class="item-img" src="{html.escape(itm['icon_url'] or '')}" alt="" loading="lazy">
                  <div class="item-info">
                    <div class="item-name" style="{name_style}">{html.escape(itm['display_name'])}</div>
                    <div class="item-rarity" style="{rarity_style}">{html.escape(itm['rarity_name'])}</div>
                    {bundle_tag}
                  </div>
                  <div class="item-amount">×{itm['amount']}</div>
                </div>
                """
            
            for part in (item_data.get("missing_parts") or []):
                items_html += f"""
                <div class="item missing">
                  <div class="item-info">
                    <div class="item-name" style="color: var(--ink-muted)">{html.escape(part)}</div>
                    <div class="item-rarity">Отсутствует</div>
                  </div>
                </div>
                """
            
            count_badge = ""
            if item_data.get("full_set_count", 0) > 0:
                count_badge = f'<div class="set-count">Полных сетов: {item_data["full_set_count"]}</div>'

            # Calculate prices for display
            item_price_val = float(item_data.get("price_value", 0))
            set_count = item_data.get("full_set_count", 0)
            
            # Label for total price (for all X sets)
            if set_count > 1 and item_price_val > 0:
                total_set_price = item_price_val * set_count
                # Reuse the format helper if possible, or simple format
                # We'll just use a simple display since _format_price is in inventory_finder context
                # but we'll try to match the label format
                price_main_label = item_data['price_label'] # This is "X RUB"
                # If it already contains "RUB", we'll try to update the number
                import re
                main_label = re.sub(r'[\d\s\.]+', f'{total_set_price:,.0f} '.replace(',', ' '), item_data['price_label'])
                unit_label = f'<div class="price-unit">за 1 шт: {item_data["price_label"]}</div>'
            else:
                main_label = item_data['price_label']
                unit_label = ""

            # Data attributes for client-side sorting/filtering
            cards_html += f"""
            <div class="card" 
                 data-target="{html.escape(item_data['target'].lower())}"
                 data-price="{item_data['price_value']}"
                 data-count="{item_data['total_units']}"
                 data-rarity="{html.escape(item_data['rarity'].lower())}"
                 data-full="{str(item_data['is_full']).lower()}">
              <div class="card-header">
                <h3 class="target-name">{html.escape(item_data['target'])}</h3>
                {count_badge}
                <div class="price">
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>
                    {html.escape(main_label)}
                  </div>
                  {unit_label}
                </div>
              </div>
              <div class="item-list">
                {items_html}
              </div>
            </div>
            """

        result_html = f"""
        <div class="result-controls">
          <div class="stats">
            <a href="https://steamcommunity.com/profiles/{html.escape(str(result['steam_id']))}" target="_blank" class="chip" title="Открыть профиль Steam">SteamID: {html.escape(str(result['steam_id']))}</a>
            <span class="chip" style="color: var(--accent)">Найдено полных: {result['matched_count']}</span>
            <span class="chip" style="color: var(--gold)">Общая стоимость: {result['total_price_label']}</span>
            <button id="toggle-partials" class="toggle-partials" title="Показать неполные сеты">
              <span>Неполные ({result['partial_count']})</span>
            </button>
          </div>
          
          <div class="controls" style="gap: 12px; flex-grow: 1; justify-content: flex-end;">
            <input id="js-filter" type="text" placeholder="Фильтр по названию..." style="max-width: 250px; padding: 10px 14px; font-size: 0.9rem;">
            <select id="js-sort" style="padding: 10px 14px; font-size: 0.9rem; border-radius: 12px;">
              <option value="name">По названию</option>
              <option value="price_desc">Дороже</option>
              <option value="price_asc">Дешевле</option>
              <option value="count">По количеству</option>
              <option value="rarity">По редкости</option>
            </select>
          </div>
        </div>
        
        <div id="results-grid" class="grid">
          {cards_html}
        </div>
        """

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dota 2 Inventory Finder</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>
  <div id="loading-overlay">
    <div class="spinner"></div>
    <div class="loading-text">ПОИСК ПРЕДМЕТОВ...</div>
  </div>

  <div class="wrap">
    <header>
      <h1>Collector's Search</h1>
    </header>

    <main>
      <section class="search-box">
        <form method="post" action="/">
          <div class="input-group">
            <label for="inventory_url">Steam Profile / Inventory URL</label>
            <input id="inventory_url" name="inventory_url" type="text" required
                   placeholder="https://steamcommunity.com/id/m4xvel/inventory"
                   value="{inventory_url_safe}">
          </div>

          <div class="form-footer">
            <div class="controls">
            </div>
            <button type="submit">Найти предметы</button>
          </div>
        </form>
      </section>

      {error_html}
      {result_html}
    </main>
  </div>

  <script>
  document.addEventListener('DOMContentLoaded', () => {{
    const grid = document.getElementById('results-grid');
    if (!grid) return;

    const filterInput = document.getElementById('js-filter');
    const sortSelect = document.getElementById('js-sort');
    const togglePartialsBtn = document.getElementById('toggle-partials');
    let cards = Array.from(grid.getElementsByClassName('card'));

    const update = () => {{
      const query = filterInput.value.toLowerCase();
      const sortBy = sortSelect.value;

      // Filter
      cards.forEach(card => {{
        const target = card.dataset.target || '';
        card.style.display = target.includes(query) ? '' : 'none';
      }});

      // Sort
      const sorted = [...cards].sort((a, b) => {{
        // Special logic: if partials are shown, sort them to the top
        if (document.body.classList.contains('show-partials')) {{
          const isFullA = a.dataset.full === 'true';
          const isFullB = b.dataset.full === 'true';
          if (isFullA !== isFullB) {{
            return isFullA ? 1 : -1; // Full sets (true) go down, partials (false) go up
          }}
        }}

        if (sortBy === 'name') {{
          return a.dataset.target.localeCompare(b.dataset.target);
        }}
        if (sortBy.startsWith('price')) {{
          const pA = parseFloat(a.dataset.price) || 0;
          const pB = parseFloat(b.dataset.price) || 0;
          
          if (pA === 0 && pB !== 0) return 1;
          if (pB === 0 && pA !== 0) return -1;
          
          return sortBy === 'price_desc' ? pB - pA : pA - pB;
        }}
        if (sortBy === 'count') {{
          return parseInt(b.dataset.count) - parseInt(a.dataset.count);
        }}
        if (sortBy === 'rarity') {{
          return a.dataset.rarity.localeCompare(b.dataset.rarity);
        }}
        return 0;
      }});

      sorted.forEach(node => grid.appendChild(node));
    }};

    filterInput.addEventListener('input', update);
    sortSelect.addEventListener('change', update);

    if (togglePartialsBtn) {{
      togglePartialsBtn.addEventListener('click', () => {{
        document.body.classList.toggle('show-partials');
        togglePartialsBtn.classList.toggle('active');
        update();
      }});
    }}
  }});

  // Loading indicator for form
  const searchForm = document.querySelector('form');
  const overlay = document.getElementById('loading-overlay');
  if (searchForm && overlay) {{
    searchForm.addEventListener('submit', () => {{
      overlay.classList.add('visible');
    }});
  }}
  </script>
</body>
</html>
"""

class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404, "Not Found")
            return
        page = render_page(names_file=NAMES_FILE.name)
        self._send_html(page)

    def do_POST(self) -> None:
        if self.path != "/":
            self.send_error(404, "Not Found")
            return

        form = self._read_form_data()
        inventory_url = (form.get("inventory_url", [""])[0] or "").strip()

        error = ""
        result = None

        if not inventory_url:
            error = "Укажите ссылку на инвентарь или профиль."
        else:
            try:
                targets = read_targets(str(NAMES_FILE))
                steam_id = resolve_steam_id(inventory_url)
                assets, descriptions = fetch_dota_inventory(steam_id)
                items = build_items(assets, descriptions)
                raw_results = search_items(items, targets)
                
                matched_rows = [r for r in raw_results if r.items]
                target_names_for_price = [r.target for r in matched_rows if r.is_full]
                rich_prices = fetch_rich_prices(target_names_for_price)

                matches = []
                total_value = 0.0
                currency = "RUB"
                
                for row in matched_rows:
                    price_info = rich_prices.get(row.target, {"label": "n/a", "value": 0})
                    price_val = float(price_info.get("value", 0))
                    
                    # Calculate contribution to total value based on quantity of full sets
                    if row.full_set_count > 0:
                        total_value += (price_val * row.full_set_count)
                    
                    if "RUB" in price_info["label"].upper(): currency = "RUB"
                    elif "USD" in price_info["label"].upper(): currency = "USD"
                    
                    first_item_rarity = row.items[0].rarity_name if row.items else ""
                    
                    matches.append({
                        "target": row.target,
                        "items": row.items,
                        "price_label": price_info["label"] if row.is_full else "Неполный сет",
                        "price_value": price_info["value"] if row.is_full else 0,
                        "total_units": row.total_units,
                        "full_set_count": row.full_set_count,
                        "rarity": first_item_rarity,
                        "is_full": row.is_full,
                        "missing_parts": row.missing_parts
                    })

                # Initial sort: partials first, then by name
                matches.sort(key=lambda x: (x["is_full"], x["target"].lower()))

                result = {
                    "steam_id": steam_id,
                    "targets_count": len(targets),
                    "items_count": len(items),
                    "matched_count": len([m for m in matches if m["is_full"]]),
                    "partial_count": len([m for m in matches if not m["is_full"]]),
                    "matches": matches,
                    "total_price_label": _format_price(total_value, currency),
                }
            except SteamInventoryError as exc:
                error = str(exc)
            except Exception as e:
                error = f"Ошибка: {str(e)}"

        page = render_page(
            names_file=NAMES_FILE.name,
            inventory_url=inventory_url,
            error=error,
            result=result,
        )
        self._send_html(page)

    def _read_form_data(self) -> Dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return urllib.parse.parse_qs(raw, keep_blank_values=True)

    def _send_html(self, content: str, status: int = 200) -> None:
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not NAMES_FILE.exists():
        print(f"Error: {NAMES_FILE} not found")
        return 1

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    exit(main())
