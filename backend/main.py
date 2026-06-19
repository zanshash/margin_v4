"""
Angel One FnO Margin Calculator — complete demo.

First run: builds catalog_cache.json (takes ~30-60 seconds).
Subsequent runs: loads from cache (instant).

Usage:
    pip install requests
    python main.py
"""

from catalog import build_catalog, find_contract, get_expiries, get_strike_prices_cached, nearest_strike, get_all_contracts
from enums import Exchange, OptionType, Product, TradeType
from margin_calculator import calculate_margin
from models import Position


def sep(title: str = ""):
    if title:
        print(f"\n{'='*55}")
        print(f"  {title}")
        print(f"{'='*55}")
    else:
        print(f"{'='*55}")


def show_result(result, label: str = ""):
    if label:
        print(f"\n  >> {label}")
    print(f"  Total Margin Required : Rs.{result.totalPositionMargin:>14,.2f}")
    print(f"  SPAN Margin           : Rs.{result.margin.SPANMargin:>14,.2f}")
    print(f"  Exposure Margin       : Rs.{result.margin.exposureMargin:>14,.2f}")
    print(f"  Margin Benefit        : Rs.{result.margin.marginBenefit:>14,.2f}")
    print(f"  Net Premium           : Rs.{result.margin.netPremium:>14,.2f}")
    if result.positionMargin:
        print("  Per-position:")
        for p in result.positionMargin:
            sp = f" @{p.strikePrice}" if p.strikePrice and p.strikePrice != "0" else ""
            print(f"    [{p.contract}{sp}] SPAN=Rs.{p.SPANMargin:,.2f}  Exp=Rs.{p.exposureMargin:,.2f}  Total=Rs.{p.totalMargin:,.2f}")


def main():
    # ------------------------------------------------------------------ #
    # 1. Load (or build) the full contract catalog
    # ------------------------------------------------------------------ #
    sep("CATALOG")
    cat = build_catalog()   # loads from cache if fresh, fetches otherwise
    print("\nContracts available per exchange × product:")
    for ex_name, products in cat["contracts"].items():
        for prod_name, contracts in products.items():
            print(f"  {ex_name:8s}  {prod_name:8s}  {len(contracts):4d} contracts")

    # ------------------------------------------------------------------ #
    # 2. List NIFTY expiries
    # ------------------------------------------------------------------ #
    sep("NIFTY EXPIRIES — NFO FUTURE")
    expiries = get_expiries("NIFTY", "NFO", "FUTURE")
    print(f"\n  {expiries}")

    # ------------------------------------------------------------------ #
    # 3. Futures — NIFTY (nearest expiry, 1 lot)
    # ------------------------------------------------------------------ #
    sep("NIFTY FUTURES MARGIN (1 lot, BUY)")
    nifty_fut = find_contract("NIFTY", exchange=Exchange.NFO, product=Product.FUTURE)
    if nifty_fut:
        print(f"\n  Contract  : {nifty_fut['symbol']}")
        print(f"  Lot size  : {nifty_fut['lotSize']}")
        pos = Position(
            contract=nifty_fut["symbol"],
            exchange=Exchange.NFO,
            product=Product.FUTURE,
            qty=nifty_fut["lotSize"],
            tradeType=TradeType.BUY,
        )
        result = calculate_margin([pos])
        show_result(result)

    # ------------------------------------------------------------------ #
    # 4. BANKNIFTY futures (nearest expiry, 1 lot)
    # ------------------------------------------------------------------ #
    sep("BANKNIFTY FUTURES MARGIN (1 lot, SELL)")
    bnf = find_contract("BANKNIFTY", exchange=Exchange.NFO, product=Product.FUTURE)
    if bnf:
        print(f"\n  Contract  : {bnf['symbol']}")
        print(f"  Lot size  : {bnf['lotSize']}")
        pos = Position(
            contract=bnf["symbol"],
            exchange=Exchange.NFO,
            product=Product.FUTURE,
            qty=bnf["lotSize"],
            tradeType=TradeType.SELL,
        )
        result = calculate_margin([pos])
        show_result(result)

    # ------------------------------------------------------------------ #
    # 5. Options — NIFTY ATM CE (nearest expiry)
    # ------------------------------------------------------------------ #
    sep("NIFTY OPTIONS MARGIN — ATM CALL (BUY)")
    nifty_opt = find_contract("NIFTY", exchange=Exchange.NFO, product=Product.OPTION)
    if nifty_opt:
        strikes = get_strike_prices_cached(Exchange.NFO, Product.OPTION, nifty_opt["symbol"], option_type=OptionType.CALL)
        if strikes:
            # Pick ATM using median strike
            atm = strikes[len(strikes) // 2]
            print(f"\n  Contract  : {nifty_opt['symbol']}")
            print(f"  Strike    : {atm}  (ATM approx, median of {len(strikes)} strikes)")
            print(f"  Lot size  : {nifty_opt['lotSize']}")
            pos = Position(
                contract=nifty_opt["symbol"],
                exchange=Exchange.NFO,
                product=Product.OPTION,
                qty=nifty_opt["lotSize"],
                tradeType=TradeType.BUY,
                strikePrice=atm,
                optionType=OptionType.CALL,
            )
            result = calculate_margin([pos])
            show_result(result)

    # ------------------------------------------------------------------ #
    # 6. Multi-leg — Bull call spread (BUY CE + SELL CE → margin benefit)
    # ------------------------------------------------------------------ #
    sep("BULL CALL SPREAD — BUY CE + SELL CE (margin benefit demo)")
    nifty_opt2 = find_contract("NIFTY", exchange=Exchange.NFO, product=Product.OPTION)
    if nifty_opt2:
        strikes = get_strike_prices_cached(Exchange.NFO, Product.OPTION, nifty_opt2["symbol"], option_type=OptionType.CALL)
        if len(strikes) >= 2:
            mid = (strikes[0] + strikes[-1]) / 2
            lower = nearest_strike(strikes, mid)
            # pick next available strike above lower for the short leg
            above = [s for s in strikes if s > lower]
            upper = above[0] if above else lower

            print(f"\n  Contract  : {nifty_opt2['symbol']}")
            print(f"  BUY  CE   : strike {lower}")
            print(f"  SELL CE   : strike {upper}")

            positions = [
                Position(
                    contract=nifty_opt2["symbol"],
                    exchange=Exchange.NFO,
                    product=Product.OPTION,
                    qty=nifty_opt2["lotSize"],
                    tradeType=TradeType.BUY,
                    strikePrice=lower,
                    optionType=OptionType.CALL,
                ),
                Position(
                    contract=nifty_opt2["symbol"],
                    exchange=Exchange.NFO,
                    product=Product.OPTION,
                    qty=nifty_opt2["lotSize"],
                    tradeType=TradeType.SELL,
                    strikePrice=upper,
                    optionType=OptionType.CALL,
                ),
            ]
            result = calculate_margin(positions)
            show_result(result, "Combined margin (benefit applied)")

    # ------------------------------------------------------------------ #
    # 7. Commodity futures — MCX GOLD (if available)
    # ------------------------------------------------------------------ #
    sep("MCX GOLD FUTURES (1 lot, BUY)")
    gold = find_contract("GOLD", exchange=Exchange.MCX, product=Product.FUTURE)
    if gold:
        print(f"\n  Contract  : {gold['symbol']}")
        print(f"  Lot size  : {gold['lotSize']}")
        pos = Position(
            contract=gold["symbol"],
            exchange=Exchange.MCX,
            product=Product.FUTURE,
            qty=gold["lotSize"],
            tradeType=TradeType.BUY,
        )
        result = calculate_margin([pos])
        show_result(result)
    else:
        print("\n  MCX GOLD not found in catalog.")

    sep()


if __name__ == "__main__":
    main()
