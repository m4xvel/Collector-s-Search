#!/usr/bin/env python3
"""Find Dota 2 inventory items on Steam by a predefined list of names."""

from __future__ import annotations


import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Callable, Any

STEAM_COMMUNITY_HOST = "steamcommunity.com"
DOTA_APP_ID = 570
DOTA_CONTEXT_ID = 2
COLLECTORSSHOP_ITEMS_ENDPOINT = "https://collectorsshop.ru/api/rest/catalog/items"
COLLECTORSSHOP_DOTA_ROUTE = "dota"
DEFAULT_LANG = "english"
DEFAULT_COUNT = 2000
MAX_PAGES = 100
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class SteamInventoryError(RuntimeError):
    """Raised when inventory fetching or profile resolution fails."""


@dataclass(frozen=True)
class InventoryItem:
    asset_id: str
    amount: int
    display_name: str
    match_text: str
    exact_fields: Tuple[str, ...]
    icon_url: str = ""
    name_color: str = ""
    rarity_name: str = ""
    rarity_color: str = ""
    is_giftable: bool = False
    is_tradable: bool = False
    is_marketable: bool = False
    is_bundle: bool = False
    market_hash_name: str = ""










def _http_get(url: str, params: Dict[str, str] | None = None) -> str:
    def _decode_response(data: bytes, content_encoding: str) -> str:
        if "gzip" in content_encoding.lower():
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        return data.decode("utf-8", errors="replace")

    query = urllib.parse.urlencode(params or {})
    full_url = f"{url}?{query}" if query else url
    req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})

    max_retries = 3
    base_delay = 5  # Start with 5s delay for 429

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read()
                encoding = response.headers.get("Content-Encoding", "")
                return _decode_response(raw, encoding)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    # For long waits, print to console so user knows why it hangs
                    print(f"Received 429 for {url}. Waiting {delay}s before retry {attempt + 1}/{max_retries}...", flush=True)
                    time.sleep(delay)
                    continue
                hint = " Too many requests; wait and retry."
            elif exc.code in {401, 403}:
                hint = (
                    " Inventory is likely private or hidden. "
                    "Make sure profile and inventory are Public."
                )
            else:
                hint = ""
            
            body = ""
            if exc.fp:
                try:
                    raw = exc.read()
                    encoding = exc.headers.get("Content-Encoding", "") if exc.headers else ""
                    body = _decode_response(raw, encoding)
                except Exception: pass

            msg = f"HTTP {exc.code} while requesting {url}.{hint}"
            if body:
                trimmed = re.sub(r"\s+", " ", body)[:200]
                msg += f" Response snippet: {trimmed}"
            raise SteamInventoryError(msg) from exc
        except urllib.error.URLError as exc:
            if attempt < max_retries:
                time.sleep(1) # Short retry for network blips
                continue
            raise SteamInventoryError(f"Network error while requesting {url}: {exc.reason}") from exc

    # Should not be reachable
    raise SteamInventoryError(f"Failed to fetch {url} after {max_retries} attempts.")


def _http_get_json(url: str, params: Dict[str, str] | None = None) -> Dict:
    text = _http_get(url, params=params)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        snippet = re.sub(r"\s+", " ", text)[:200]
        raise SteamInventoryError(
            f"Service returned non-JSON response for {url}. Snippet: {snippet}"
        ) from exc


def resolve_steam_id(inventory_url: str) -> str:
    candidate = inventory_url.strip()
    if candidate.isdigit() and len(candidate) >= 16:
        return candidate

    if "://" not in candidate and candidate.startswith("steamcommunity.com/"):
        candidate = f"https://{candidate}"

    parsed = urllib.parse.urlparse(candidate)
    host = parsed.netloc.lower()
    if not host:
        raise SteamInventoryError("Please pass a full Steam Community URL.")

    if host != STEAM_COMMUNITY_HOST and not host.endswith(f".{STEAM_COMMUNITY_HOST}"):
        raise SteamInventoryError(
            "URL host must be steamcommunity.com (or its subdomain)."
        )

    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise SteamInventoryError("Could not parse Steam profile from URL.")

    if parts[0] == "inventory" and len(parts) >= 2 and parts[1].isdigit():
        return parts[1]

    if parts[0] == "profiles" and len(parts) >= 2 and parts[1].isdigit():
        return parts[1]

    if parts[0] == "id" and len(parts) >= 2:
        vanity = parts[1]
        return resolve_vanity_to_steam_id(vanity)

    raise SteamInventoryError(
        "Unsupported URL format. Expected /profiles/<steamid>/... or /id/<vanity>/..."
    )


def resolve_vanity_to_steam_id(vanity: str) -> str:
    xml_text = _http_get(f"https://steamcommunity.com/id/{vanity}/", params={"xml": "1"})

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        snippet = re.sub(r"\s+", " ", xml_text)[:200]
        raise SteamInventoryError(
            f"Failed to parse XML for vanity URL '{vanity}'. Snippet: {snippet}"
        ) from exc

    steam_id_node = root.find("steamID64")
    steam_id = steam_id_node.text.strip() if steam_id_node is not None and steam_id_node.text else ""
    if not steam_id.isdigit():
        raise SteamInventoryError(
            f"Could not resolve vanity URL '{vanity}' to steamID64."
        )
    return steam_id


def fetch_dota_inventory(
    steam_id: str, 
    progress_callback: Callable[[int, str], None] | None = None
) -> Tuple[List[Dict], Dict[Tuple[str, str], Dict]]:
    endpoint = f"https://steamcommunity.com/inventory/{steam_id}/{DOTA_APP_ID}/{DOTA_CONTEXT_ID}"

    all_assets: List[Dict] = []
    seen_asset_ids = set()
    descriptions: Dict[Tuple[str, str], Dict] = {}

    start_assetid = ""
    page = 0

    while True:
        page += 1
        if progress_callback:
            progress_callback(10 + min(page * 5, 40), f"Загрузка страницы инвентаря {page}...")
            
        if page > MAX_PAGES:
            raise SteamInventoryError(
                f"Inventory pagination exceeded {MAX_PAGES} pages."
            )

        params = {
            "l": DEFAULT_LANG,
            "count": str(DEFAULT_COUNT),
        }
        if start_assetid:
            params["start_assetid"] = start_assetid

        payload = _http_get_json(endpoint, params=params)

        assets = payload.get("assets") or []
        descs = payload.get("descriptions") or []

        for asset in assets:
            aid = str(asset.get("assetid", ""))
            if aid and aid not in seen_asset_ids:
                all_assets.append(asset)
                seen_asset_ids.add(aid)

        for desc in descs:
            classid = str(desc.get("classid", ""))
            instanceid = str(desc.get("instanceid", "0"))
            if classid:
                descriptions[(classid, instanceid)] = desc

        if not payload.get("more_items"):
            break

        start_assetid = str(payload.get("last_assetid", ""))
        if not start_assetid:
            raise SteamInventoryError(
                "Steam reported more_items=true but did not provide last_assetid."
            )

    return all_assets, descriptions


# Quality prefixes added by gems/inscriptions that should be stripped for matching
_QUALITY_PREFIXES = (
    "Inscribed ",
    "Autographed ",
    "Frozen ",
    "Corrupted ",
    "Cursed ",
    "Heroic ",
    "Genuine ",
    "Elder ",
    "Exalted ",
    "Infused ",
    "Auspicious ",
    "Unusual ",
    "Bundle of ",
    "Бандл: ",
)


def _strip_quality_prefix(name: str) -> str:
    """Remove quality prefixes (e.g. 'Inscribed Genuine ') from an item name."""
    while True:
        changed = False
        for prefix in _QUALITY_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix):]
                changed = True
                break
        if not changed:
            break
    return name


def _extract_original_name(desc: Dict) -> str:
    """Extract original item name from Steam fraudwarnings field.

    Renamed items have a fraudwarnings entry like:
      'This item has been renamed.\nOriginal name: "Ardalan Arms Race - Head"'
    Returns the original name or empty string if not found.
    """
    warnings = desc.get("fraudwarnings")
    if not isinstance(warnings, list):
        return ""
    for warning in warnings:
        if not isinstance(warning, str):
            continue
        match = re.search(r'Original name:\s*"(.+?)"', warning)
        if match:
            return match.group(1).strip()
    return ""


def _join_non_empty(parts: Iterable[str]) -> str:
    return " | ".join([p for p in parts if p])


def build_items(assets: List[Dict], descriptions: Dict[Tuple[str, str], Dict]) -> List[InventoryItem]:
    items: List[InventoryItem] = []

    for asset in assets:
        classid = str(asset.get("classid", ""))
        instanceid = str(asset.get("instanceid", "0"))
        desc = descriptions.get((classid, instanceid))
        if not desc:
            continue

        name = str(desc.get("name", "")).strip()
        market_hash_name = str(desc.get("market_hash_name", "")).strip()
        item_type = str(desc.get("type", "")).strip()

        # Resolve original name for renamed items and strip quality prefixes
        original_name = _extract_original_name(desc)
        clean_market_name = _strip_quality_prefix(market_hash_name)

        tags = desc.get("tags") if isinstance(desc.get("tags"), list) else []
        tag_names = [str(tag.get("name", "")).strip() for tag in tags if isinstance(tag, dict)]

        # Use the cleanest available name for display:
        # original_name (from fraudwarnings) > clean_market_name > market_hash_name > name
        display_name = original_name or clean_market_name or market_hash_name or name or f"classid:{classid}"

        # Build matching fields with all name variants for maximum match coverage
        all_names = {f for f in [name, market_hash_name, clean_market_name, original_name, item_type, *tag_names] if f}
        exact_fields = tuple({f.lower() for f in all_names})
        match_text = _join_non_empty([name, market_hash_name, clean_market_name, original_name, item_type, *tag_names]).lower()

        amount_raw = str(asset.get("amount", "1"))
        amount = int(amount_raw) if amount_raw.isdigit() else 1

        rarity_name = ""
        rarity_color = ""
        for tag in tags:
            if isinstance(tag, dict) and tag.get("category") == "rarity":
                rarity_name = str(tag.get("name", "")).strip()
                rarity_color = str(tag.get("color", "")).strip()
                break

        icon_url = str(desc.get("icon_url", "")).strip()
        if icon_url:
            icon_url = f"https://community.cloudflare.steamstatic.com/economy/image/{icon_url}"

        name_color = str(desc.get("name_color", "")).strip()

        # Check for giftability in descriptions
        is_giftable = False
        desc_list = desc.get("descriptions")
        if isinstance(desc_list, list):
            for d_attr in desc_list:
                if isinstance(d_attr, dict):
                    val = str(d_attr.get("value", "")).lower()
                    if "may be gifted once" in val or "can be gifted once" in val or "можно подарить один раз" in val:
                        is_giftable = True
                        break

        items.append(
            InventoryItem(
                asset_id=str(asset.get("assetid", "")),
                amount=amount,
                display_name=display_name,
                match_text=match_text,
                exact_fields=exact_fields,
                icon_url=icon_url,
                name_color=name_color,
                rarity_name=rarity_name,
                rarity_color=rarity_color,
                is_giftable=is_giftable,
                is_tradable=desc.get("tradable") == 1,
                is_marketable=desc.get("marketable") == 1,
                is_bundle="bundle" in item_type.lower() or "бандл" in item_type.lower() or "full set" in item_type.lower(),
                market_hash_name=market_hash_name,
            )
        )

    return items


@dataclass(frozen=True)
class MatchResult:
    target: str
    items: List[InventoryItem]
    category: str = "Other"
    full_set_count: int = 0
    is_full: bool = True
    missing_parts: List[str] = None
    # Track which parts contribute to an incomplete set
    found_parts_count: Dict[str, int] = None
    
    @property
    def total_units(self) -> int:
        return sum(i.amount for i in self.items)


def search_items(
    items: List[InventoryItem],
    targets: List[str] | None = None,
    progress_callback: Callable[[int, str], None] | None = None
) -> List[MatchResult]:
    results: List[MatchResult] = []

    if progress_callback:
        progress_callback(60, "Сопоставление предметов с базой сетов...")

    db_path = Path(__file__).resolve().parent / "dota_sets_db.json"
    arcana_path = Path(__file__).resolve().parent / "arcanas_db.json"
    persona_path = Path(__file__).resolve().parent / "personas_db.json"
    
    sets_db = {}
    set_to_category = {}

    def load_db(path: Path):
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    nested = json.load(f)
                    for category, sets in nested.items():
                        for set_name, parts in sets.items():
                            # Priority logic: Arcanas > Personas > Cache (default)
                            # We only overwrite if the new category is higher priority
                            current_cat = set_to_category.get(set_name)
                            if current_cat in ["Arcanas", "Personas"] and category not in ["Arcanas", "Personas"]:
                                continue # Keep existing high priority
                            
                            sets_db[set_name] = parts
                            set_to_category[set_name] = category
            except Exception:
                pass

    # Load in order of priority (lowest to highest so highest overwrites)
    load_db(db_path)
    load_db(persona_path)
    load_db(arcana_path)

    search_targets = targets if targets is not None else sorted(sets_db.keys())
    
    for target in search_targets:
        needle = target.strip().lower()
        if not needle:
            continue
        required_parts = sets_db.get(target, [])
        names_to_find = {needle} | {p.lower() for p in required_parts}

        # Select only items that EXACTLY match our target or its parts
        matched_items: List[InventoryItem] = []
        for item in items:
            if any(name in item.exact_fields for name in names_to_find):
                matched_items.append(item)

        if not matched_items:
            results.append(MatchResult(target=target, items=[], is_full=False, full_set_count=0))
            continue
        
        # 1. Gather all unique items matching the target name exactly
        # An item is a "Bundle" if it matches the target name AND (it's not a part OR it's explicitly a bundle)
        bundle_items = []
        is_single_item_set = (len(required_parts) == 1 and required_parts[0].lower() == needle)
        
        for i in matched_items:
            if needle in i.exact_fields:
                if not is_single_item_set or i.is_bundle:
                    # If it's a multi-part set, a match on the target name is always a bundle.
                    # If it's a single-item set, it's only a bundle if Steam says so.
                    bundle_items.append(i)
        
        sets_from_bundles = sum(i.amount for i in bundle_items)
        
        if not required_parts:
            # If not in DB, assume any match IS a full set (e.g. Courier)
            results.append(MatchResult(
                target=target,
                items=matched_items,
                full_set_count=sum(i.amount for i in matched_items),
                is_full=True
            ))
            continue

        # 2. Count parts from individual items
        part_counts = {p.lower(): 0 for p in required_parts}
        for item in matched_items:
            # If it's already counted as a bundle, don't count it as a part
            if item in bundle_items:
                continue
            
            # Check if this item matches any of the required parts
            for rp in required_parts:
                rp_lower = rp.lower()
                if rp_lower in item.exact_fields:
                    part_counts[rp_lower] += item.amount
                    break

        # 3. Calculate full sets from parts
        if part_counts:
            sets_from_parts = min(part_counts.values())
        else:
            sets_from_parts = 0
            
        total_full_sets = sets_from_bundles + sets_from_parts
        
        # 4. Check for an incomplete set from remaining parts
        remaining_parts = {p: count - sets_from_parts for p, count in part_counts.items()}
        # A part is missing IF we have some extra parts but not all of them for the NEXT set
        has_extra_parts = any(count > 0 for count in remaining_parts.values())
        
        missing = []
        if total_full_sets == 0:
            # If we have 0 full sets, show what's missing for the 1st
            missing = [p for p in required_parts if remaining_parts[p.lower()] <= 0]

        # Safety deduplication by asset_id (just in case input had them)
        unique_matched_items = []
        seen_matched_aids = set()
        for i in matched_items:
            if i.asset_id not in seen_matched_aids:
                unique_matched_items.append(i)
                seen_matched_aids.add(i.asset_id)
        
        results.append(MatchResult(
            target=target,
            items=unique_matched_items,
            category=set_to_category.get(target, "Other"),
            full_set_count=total_full_sets,
            is_full=(total_full_sets > 0),
            missing_parts=missing if missing else None,
            found_parts_count=remaining_parts if has_extra_parts else None
        ))

    return results


def _normalize_name(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_price_value(item: Dict) -> float | None:
    for key in ("fin_price", "price"):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(" ", "")
            if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
                return float(cleaned)
    return None


def _format_price(amount: float, currency: str) -> str:
    if amount.is_integer():
        base = f"{int(amount):,}".replace(",", " ")
    else:
        base = f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{base} {currency.upper()}"


def _pick_best_catalog_item(target: str, items: List[Dict]) -> Dict | None:
    target_normalized = _normalize_name(target)
    exact_matches: List[Dict] = []
    substring_matches: List[Dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        item_name = _normalize_name(str(item.get("name", "")))
        if item_name == target_normalized:
            exact_matches.append(item)
        elif target_normalized and target_normalized in item_name:
            substring_matches.append(item)

    pool = exact_matches or substring_matches or [item for item in items if isinstance(item, dict)]
    if not pool:
        return None

    with_price = [item for item in pool if extract_price_value(item) is not None]
    if with_price:
        return min(with_price, key=lambda row: extract_price_value(row) or float("inf"))
    return pool[0]


def fetch_collectorsshop_prices(targets: List[str]) -> Dict[str, str]:
    prices: Dict[str, str] = {}
    unique_targets = list(dict.fromkeys([target.strip() for target in targets if target.strip()]))

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
        except SteamInventoryError:
            prices[target] = "n/a"
            continue

        items = payload.get("items")
        if not isinstance(items, list) or not items:
            prices[target] = "n/a"
            continue

        best_item = _pick_best_catalog_item(target, items)
        if not best_item:
            prices[target] = "n/a"
            continue

        amount = extract_price_value(best_item)
        if amount is None:
            prices[target] = "n/a"
            continue

        currency = str(payload.get("currency", "rub"))
        price_label = _format_price(amount, currency)
        if best_item.get("stock") is False:
            price_label += " (нет в наличии)"
        prices[target] = price_label

    return prices


def fetch_market_prices(
    progress_callback: Callable[[int, str], None] | None = None
) -> Dict[str, float]:
    """Fetch all Dota 2 item prices from market.dota2.net.

    Returns a dict mapping market_hash_name -> price in RUB.
    Only items with a valid price are included.
    """
    url = "https://market.dota2.net/api/v2/prices/RUB.json"
    if progress_callback:
        progress_callback(85, "Загрузка цен с маркета...")

    try:
        payload = _http_get_json(url)
    except SteamInventoryError:
        return {}

    if not payload.get("success"):
        return {}

    items = payload.get("items")
    if not isinstance(items, list):
        return {}

    prices: Dict[str, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("market_hash_name", "")
        price_str = item.get("price", "")
        if not name or not price_str:
            continue
        try:
            price = float(price_str)
            if price > 0:
                prices[name] = price
        except (ValueError, TypeError):
            continue

    return prices

