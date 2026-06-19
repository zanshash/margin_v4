"""GET /api/strikes?exchange=NFO&product=OPTION&contract=NIFTY-30JUN26&optionType=CALL

Returns the sorted list of available strike prices for an options contract.
Reads from catalog_cache.json first; falls back to live Angel One API fetch
(without writing back — Vercel's filesystem is read-only).
"""
import sys
import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

_BASE = "https://margin-calc-arom-prod.angelbroking.com"
_HEADERS = {
    "Accept": "*/*",
    "Origin": "https://www.angelone.in",
    "Referer": "https://www.angelone.in/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
}

_strikes_mem: dict = {}   # module-level in-memory cache


def _get_strikes(exchange: str, product: str, contract: str, opt_type: str) -> list:
    key = f"{exchange.upper()}:{product.upper()}:{contract}:{opt_type.upper()}"
    if key in _strikes_mem:
        return _strikes_mem[key]

    # Try catalog cache file first (read-only, safe on Vercel)
    try:
        from catalog import _load_cache
        cat = _load_cache()
        if cat and key in cat.get("strikes", {}):
            _strikes_mem[key] = cat["strikes"][key]
            return _strikes_mem[key]
    except Exception:
        pass

    # Fall back to live Angel One API (no cache write)
    import requests
    resp = requests.get(
        f"{_BASE}/exchange/{exchange}/product/{product}/contract/{contract}/strike-price",
        params={"optionType": opt_type.upper()},
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    raw = resp.json().get("strikePrice", [])
    strikes = sorted(float(s) for s in raw)
    _strikes_mem[key] = strikes
    return strikes


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs       = parse_qs(urlparse(self.path).query)
        exchange = (qs.get("exchange",  ["NFO"])[0]).upper()
        product  = (qs.get("product",   ["OPTION"])[0]).upper()
        contract = qs.get("contract", [""])[0]
        opt_type = (qs.get("optionType", ["CALL"])[0]).upper()

        if not contract:
            self._send(400, {"error": "contract parameter is required"})
            return

        try:
            strikes = _get_strikes(exchange, product, contract, opt_type)
            self._send(200, {"strikes": strikes})
        except Exception as e:
            self._send(502, {"error": str(e)})

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
