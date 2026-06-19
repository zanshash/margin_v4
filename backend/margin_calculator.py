"""
Public Angel One margin calculator API — no authentication required.

Base: https://margin-calc-arom-prod.angelbroking.com
"""

import requests
from typing import List

from enums import Exchange, Product
from models import Position, MarginResponse

BASE = "https://margin-calc-arom-prod.angelbroking.com"

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "Origin": "https://www.angelone.in",
    "Referer": "https://www.angelone.in/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
}


def get_exchanges() -> list:
    """Return list of available exchanges: [{exchangeName, exchangeId}, ...]"""
    resp = requests.get(f"{BASE}/exchange", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["exchange"]


def get_products(exchange: Exchange) -> list:
    """Return products for an exchange: [{productName, productId, productType?}, ...]"""
    resp = requests.get(f"{BASE}/exchange/{exchange}/product", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["product"]


def get_contracts(exchange: Exchange, product: Product) -> list:
    """Return all contracts: [{symbol, lotSize, instrumentType}, ...]"""
    resp = requests.get(
        f"{BASE}/exchange/{exchange}/product/{product}/contract",
        headers=HEADERS, timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["contract"]


def get_strike_prices(exchange: Exchange, product: Product, contract: str, option_type: str = "CALL") -> list:
    """Return available strike prices for an options contract. option_type: CALL or PUT."""
    resp = requests.get(
        f"{BASE}/exchange/{exchange}/product/{product}/contract/{contract}/strike-price",
        params={"optionType": str(option_type).upper()},
        headers=HEADERS, timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("strikePrice", [])


def calculate_margin(positions: List[Position]) -> MarginResponse:
    """
    POST positions to the public Angel One SPAN margin calculator.

    No authentication required. Supports up to 50 positions.

    Example:
        from catalog import find_contract
        from enums import Exchange, Product, TradeType

        c = find_contract("NIFTY", exchange=Exchange.NFO, product=Product.FUTURE)
        pos = Position(
            contract=c["symbol"],
            exchange=Exchange.NFO,
            product=Product.FUTURE,
            qty=c["lotSize"],
            tradeType=TradeType.BUY,
        )
        result = calculate_margin([pos])
        print(result.totalPositionMargin)
    """
    payload = {"position": [p.to_dict() for p in positions]}
    resp = requests.post(
        f"{BASE}/margin-calculator/SPAN",
        json=payload,
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return MarginResponse.from_dict(resp.json())
