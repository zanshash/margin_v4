"""
Contract catalog — fetches and caches the complete list of all tradeable
contracts across every exchange and product from the Angel One public API.

Cache file: catalog_cache.json  (auto-refreshed if older than 24 hours)

Usage:
    from catalog import find_contract, get_expiries, get_strike_prices_cached

    # Futures
    c = find_contract("NIFTY", exchange="NFO", product="FUTURE")
    # {'symbol': 'NIFTY-30JUN26', 'lotSize': 65, 'instrumentType': 'FUTIDX', ...}

    # Options — find a specific expiry + strike
    c = find_contract("NIFTY", exchange="NFO", product="OPTION", expiry="JUN26")
    strikes = get_strike_prices_cached("NFO", "OPTION", c["symbol"])

    # All NIFTY expiries
    expiries = get_expiries("NIFTY", exchange="NFO", product="FUTURE")
    # ['30JUN26', '28JUL26', '25AUG26']
"""

import json
import os
import time
from typing import List, Optional

import requests

_MONTH = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}


def _expiry_sort_key(expiry: str) -> tuple:
    """Convert DDMMMYY → (year, month, day) for chronological sorting."""
    try:
        day = int(expiry[:2])
        month = _MONTH.get(expiry[2:5].upper(), 0)
        year = 2000 + int(expiry[5:7])
        return (year, month, day)
    except Exception:
        return (9999, 0, 0)

BASE = "https://margin-calc-arom-prod.angelbroking.com"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "catalog_cache.json")
CACHE_TTL = 86400  # 24 hours in seconds

HEADERS = {
    "Accept": "*/*",
    "Origin": "https://www.angelone.in",
    "Referer": "https://www.angelone.in/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
}

# In-memory cache to avoid repeated disk reads within the same process
_cache: Optional[dict] = None


def _load_cache() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            _cache = json.load(f)
        return _cache
    return {}


def _save_cache(data: dict):
    global _cache
    _cache = data
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass  # read-only filesystem (Vercel production) — keep in-memory only


def _cache_is_fresh() -> bool:
    if not os.path.exists(CACHE_FILE):
        return False
    age = time.time() - os.path.getmtime(CACHE_FILE)
    return age < CACHE_TTL


def build_catalog(refresh: bool = False) -> dict:
    """
    Fetch the complete contract catalog from all exchanges × all products.
    Saves result to catalog_cache.json.

    Structure:
        {
          "built_at": <unix timestamp>,
          "contracts": {
            "NFO": {
              "FUTURE": [ {symbol, lotSize, instrumentType}, ... ],
              "OPTION": [ {symbol, lotSize, instrumentType}, ... ]
            },
            "MCX": { ... },
            ...
          },
          "strikes": {
            "NFO:OPTION:NIFTY-30JUN26": [24000.0, 24050.0, ...]
          }
        }
    """
    if not refresh and _cache_is_fresh():
        return _load_cache()

    print("Building contract catalog (fetching from API)...")
    catalog: dict = {"built_at": time.time(), "contracts": {}, "strikes": {}}

    # 1. Get all exchanges
    resp = requests.get(f"{BASE}/exchange", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    exchanges = resp.json()["exchange"]

    for ex in exchanges:
        ex_name = ex["exchangeName"]
        catalog["contracts"][ex_name] = {}
        print(f"  {ex_name} ...", end=" ", flush=True)

        # 2. Get products for this exchange
        try:
            resp = requests.get(f"{BASE}/exchange/{ex_name}/product", headers=HEADERS, timeout=10)
            resp.raise_for_status()
            products = resp.json().get("product", [])
        except Exception:
            print("(skipped)")
            continue

        for prod in products:
            prod_name = prod["productName"]

            # 3. Get all contracts for this exchange + product
            try:
                resp = requests.get(
                    f"{BASE}/exchange/{ex_name}/product/{prod_name}/contract",
                    headers=HEADERS, timeout=20,
                )
                resp.raise_for_status()
                contracts = resp.json().get("contract", [])
            except Exception:
                contracts = []

            # Attach exchange + product to each record for convenience
            for c in contracts:
                c["exchange"] = ex_name
                c["product"] = prod_name

            catalog["contracts"][ex_name][prod_name] = contracts
            print(f"{prod_name}({len(contracts)})", end=" ", flush=True)

        print()

    _save_cache(catalog)
    total = sum(
        len(contracts)
        for ex in catalog["contracts"].values()
        for contracts in ex.values()
    )
    print(f"Catalog built: {total} contracts across {len(exchanges)} exchanges.")
    return catalog


def get_all_contracts(exchange: str = None, product: str = None) -> List[dict]:
    """
    Return flat list of all contracts, optionally filtered by exchange/product.
    Each item: {symbol, lotSize, instrumentType, exchange, product}
    """
    cat = _load_cache()
    if not cat:
        cat = build_catalog()

    result = []
    for ex_name, products in cat.get("contracts", {}).items():
        if exchange and ex_name != exchange.upper():
            continue
        for prod_name, contracts in products.items():
            if product and prod_name != product.upper():
                continue
            result.extend(contracts)
    return result


def find_contract(
    name: str,
    exchange: str = None,
    product: str = None,
    expiry: str = None,
) -> Optional[dict]:
    """
    Find the nearest-expiry contract matching the symbol name.

    Args:
        name:     Symbol name, e.g. "NIFTY", "BANKNIFTY", "RELIANCE"
        exchange: Optional filter, e.g. "NFO"
        product:  Optional filter, e.g. "FUTURE" or "OPTION"
        expiry:   Partial expiry string, e.g. "JUN26", "JUL26", "30JUN26"

    Returns:
        Contract dict: {symbol, lotSize, instrumentType, exchange, product}
        or None if not found.
    """
    name_upper = name.upper()
    candidates = [
        c for c in get_all_contracts(exchange, product)
        if c["symbol"].startswith(name_upper + "-")
    ]

    if expiry:
        expiry_upper = expiry.upper()
        candidates = [c for c in candidates if expiry_upper in c["symbol"].upper()]

    if not candidates:
        return None

    candidates.sort(key=lambda c: _expiry_sort_key(c["symbol"].split("-", 1)[-1]))
    return candidates[0]


def get_expiries(name: str, exchange: str, product: str) -> List[str]:
    """
    Return sorted list of expiry strings for a given symbol.
    e.g. ['30JUN26', '28JUL26', '25AUG26']
    """
    name_upper = name.upper()
    contracts = [
        c for c in get_all_contracts(exchange, product)
        if c["symbol"].startswith(name_upper + "-")
    ]
    expiries = [c["symbol"].split("-", 1)[-1] for c in contracts]
    return sorted(set(expiries), key=_expiry_sort_key)


def get_strike_prices_cached(
    exchange: str,
    product: str,
    contract: str,
    option_type: str = "CALL",
) -> List[float]:
    """
    Fetch (and cache) available strike prices for an options contract.
    Requires option_type ("CALL" or "PUT") — API mandates it.
    Returns sorted list of floats, e.g. [24000.0, 24050.0, 24100.0, ...]
    """
    cat = _load_cache()
    if not cat:
        cat = build_catalog()

    ot = str(option_type).upper()
    key = f"{str(exchange).upper()}:{str(product).upper()}:{contract}:{ot}"
    if key in cat.get("strikes", {}):
        return cat["strikes"][key]

    try:
        resp = requests.get(
            f"{BASE}/exchange/{exchange}/product/{product}/contract/{contract}/strike-price",
            params={"optionType": ot},
            headers=HEADERS, timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json().get("strikePrice", [])
        strikes = sorted(float(s) for s in raw)
    except Exception:
        strikes = []

    cat.setdefault("strikes", {})[key] = strikes
    _save_cache(cat)
    return strikes


def nearest_strike(strikes: List[float], target: float) -> float:
    """Return the strike price closest to target."""
    if not strikes:
        raise ValueError("No strikes available")
    return min(strikes, key=lambda s: abs(s - target))


if __name__ == "__main__":
    cat = build_catalog(refresh=True)

    print("\n--- Sample: NFO FUTURE contracts (first 10) ---")
    nfo_fut = get_all_contracts("NFO", "FUTURE")
    for c in nfo_fut[:10]:
        print(f"  {c['symbol']:30s}  lotSize={c['lotSize']:6d}  type={c['instrumentType']}")

    print("\n--- NIFTY expiries (NFO FUTURE) ---")
    print(" ", get_expiries("NIFTY", "NFO", "FUTURE"))

    print("\n--- find_contract('BANKNIFTY', NFO, FUTURE) ---")
    print(" ", find_contract("BANKNIFTY", "NFO", "FUTURE"))

    print("\n--- Exchanges in catalog ---")
    for ex in cat["contracts"]:
        products = cat["contracts"][ex]
        for prod, contracts in products.items():
            print(f"  {ex:8s} {prod:8s} {len(contracts):4d} contracts")
