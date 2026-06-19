"""Vercel serverless function: POST /api/margin

Accepts frontend leg format, proxies to Angel One SPAN API via the
backend module, and returns the result shaped for the UI.
"""
import sys
import os
import json
import dataclasses
from http.server import BaseHTTPRequestHandler

# Add backend/ to import path so margin_calculator, models, enums resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from margin_calculator import calculate_margin  # noqa: E402
from models import Position                      # noqa: E402
from enums import Exchange, Product, TradeType, OptionType  # noqa: E402

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def iso_to_angel(iso_date):
    """'2026-07-31' -> '31JUL26'"""
    y, m, d = iso_date.split("-")
    return f"{d}{MONTHS[int(m) - 1]}{y[2:]}"


def build_position(leg):
    product_map = {"Options": Product.OPTION, "Futures": Product.FUTURE}
    opt_map = {"CE": OptionType.CALL, "PE": OptionType.PUT}
    trade_map = {"BUY": TradeType.BUY, "SELL": TradeType.SELL}
    opt_raw = leg.get("optionType") or ""
    return Position(
        contract=f"{leg['symbol']}-{iso_to_angel(leg['expiry'])}",
        exchange=Exchange(leg["exchange"]),
        product=product_map[leg["product"]],
        qty=int(leg.get("qty", leg.get("lots", 1))),
        tradeType=trade_map[leg["tradeType"]],
        strikePrice=float(leg.get("strike") or 0.0),
        optionType=opt_map.get(opt_raw, ""),
    )


def response_to_dict(response, legs):
    result = {
        "margin": dataclasses.asdict(response.margin),
        "totalPositionMargin": response.totalPositionMargin,
        "positionMargin": [dataclasses.asdict(p) for p in response.positionMargin],
    }
    # Angel One: positive netPremium = received premium.
    # Frontend convention: negative = received (received = netPremium < 0). Flip sign.
    result["margin"]["netPremium"] = -(result["margin"].get("netPremium") or 0.0)
    # Angel One omits optionType in positionMargin; add it back from input legs.
    opt_map = {"CE": "C", "PE": "P"}
    for i, pm in enumerate(result["positionMargin"]):
        opt = legs[i].get("optionType") if i < len(legs) else None
        pm["optionType"] = opt_map.get(opt or "", "")
    return result


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except Exception as e:
            self._send(400, {"error": f"Bad request: {e}"})
            return

        legs = body.get("legs", [])
        if not legs:
            self._send(400, {"error": "No legs provided"})
            return

        try:
            positions = [build_position(leg) for leg in legs]
            result = response_to_dict(calculate_margin(positions), legs)
            self._send(200, result)
        except Exception as e:
            self._send(502, {"error": str(e)})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
