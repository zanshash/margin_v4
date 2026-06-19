"""GET /api/catalog — instrument metadata (underlyings + per-product expiries).

Calls build_catalog() from the backend scraper, which auto-refreshes from the
Angel One public API whenever the local cache is older than 24 hours.
Falls back to the pre-built catalog_cache.json if the live fetch fails.
"""
import sys
import os
import json
from http.server import BaseHTTPRequestHandler
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

_MONTHS_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_SEGMENT_MAP = {
    "FUTIDX": "index",  "OPTIDX": "index",
    "FUTSTK": "stock",  "OPTSTK": "stock",
    "FUTCOM": "commodity", "OPTCOM": "commodity", "OPTFUT": "commodity",
    "FUTCUR": "currency",  "OPTCUR": "currency",
}


def _angel_to_iso(exp: str) -> str:
    """'30JUN26' -> '2026-06-30'"""
    day = int(exp[:2])
    mon = _MONTHS_NUM[exp[2:5].upper()]
    yr  = 2000 + int(exp[5:])
    return f"{yr}-{mon:02d}-{day:02d}"


def _make_expiry(exp_angel: str, today: date) -> dict:
    iso = _angel_to_iso(exp_angel)
    d   = date.fromisoformat(iso)
    days = max(0, (d - today).days)
    label = d.strftime("%d %b %Y").lstrip("0")
    short = d.strftime("%d %b").lstrip("0")
    return {
        "date":  iso,
        "angel": exp_angel,
        "label": label,
        "short": short,
        "type":  "monthly",
        "days":  days,
    }


_catalog_cache = None   # module-level cache (warm across requests on same instance)


def _build(raw: dict) -> dict:
    """Convert raw catalog from build_catalog() into frontend-friendly format."""
    if not raw:
        return {"exchanges": [], "instruments": []}

    today = date.today()
    by_key: dict = {}  # (symbol, exchange) -> info dict

    for ex_name, products in raw.get("contracts", {}).items():
        for prod_name, contracts in products.items():
            if prod_name not in ("OPTION", "FUTURE"):
                continue
            for c in contracts:
                parts = c["symbol"].split("-", 1)
                if len(parts) != 2:
                    continue
                underlying, exp_raw = parts
                key = (underlying, ex_name)

                if key not in by_key:
                    seg = _SEGMENT_MAP.get(c.get("instrumentType", ""), "stock")
                    by_key[key] = {
                        "symbol":     underlying,
                        "exchange":   ex_name,
                        "segment":    seg,
                        "lotSize":    c["lotSize"],
                        "expiries":   {"OPTION": {}, "FUTURE": {}},
                    }

                r = by_key[key]
                try:
                    iso = _angel_to_iso(exp_raw)
                    exp_date = date.fromisoformat(iso)
                    if exp_date >= today and iso not in r["expiries"][prod_name]:
                        r["expiries"][prod_name][iso] = _make_expiry(exp_raw, today)
                except Exception:
                    pass

    instruments = []
    for r in by_key.values():
        opt_exps  = sorted(r["expiries"]["OPTION"].values(),  key=lambda e: e["date"])
        fut_exps  = sorted(r["expiries"]["FUTURE"].values(),  key=lambda e: e["date"])
        if not opt_exps and not fut_exps:
            continue
        instruments.append({
            "symbol":      r["symbol"],
            "exchange":    r["exchange"],
            "segment":     r["segment"],
            "lotSize":     r["lotSize"],
            "hasOptions":  bool(opt_exps),
            "hasFutures":  bool(fut_exps),
            "expiries": {
                "OPTION": opt_exps,
                "FUTURE": fut_exps,
            },
        })

    instruments.sort(key=lambda i: (i["exchange"], i["symbol"]))
    exchanges = sorted({i["exchange"] for i in instruments})
    return {"exchanges": exchanges, "instruments": instruments}


def get_catalog() -> dict:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    # Primary: use build_catalog() which auto-refreshes from Angel One when >24h stale
    try:
        from catalog import build_catalog
        raw = build_catalog()
        _catalog_cache = _build(raw)
        return _catalog_cache
    except Exception:
        pass

    # Fallback: read pre-built cache file directly
    try:
        from catalog import _load_cache
        raw = _load_cache()
        _catalog_cache = _build(raw)
        return _catalog_cache
    except Exception:
        return {"exchanges": [], "instruments": []}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            data = get_catalog()
            self._send(200, data)
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass
