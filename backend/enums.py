from enum import Enum


class _StrEnum(str, Enum):
    """Base class: str() returns the value, not 'ClassName.VALUE' (Python < 3.11 compat)."""
    def __str__(self):
        return self.value

    def __repr__(self):
        return self.value


class Exchange(_StrEnum):
    NFO    = "NFO"     # NSE Futures & Options
    MCX    = "MCX"     # Multi Commodity Exchange
    CDS    = "CDS"     # Currency Derivatives
    NCDEX  = "NCDEX"   # National Commodity & Derivatives Exchange
    BFO    = "BFO"     # BSE Futures & Options
    NSECOM = "NSECOM"  # NSE Commodity


class Product(_StrEnum):
    FUTURE = "FUTURE"
    OPTION = "OPTION"


class TradeType(_StrEnum):
    BUY  = "BUY"
    SELL = "SELL"


class OptionType(_StrEnum):
    CALL = "CALL"
    PUT  = "PUT"


class InstrumentType(_StrEnum):
    FUTIDX = "FUTIDX"   # Index futures      (NIFTY, BANKNIFTY, FINNIFTY …)
    FUTSTK = "FUTSTK"   # Stock futures       (RELIANCE, TCS, INFY …)
    FUTCUR = "FUTCUR"   # Currency futures    (USDINR, EURINR …)
    FUTCOM = "FUTCOM"   # Commodity futures   (GOLD, SILVER, CRUDE …)
    OPTIDX = "OPTIDX"   # Index options
    OPTSTK = "OPTSTK"   # Stock options
    OPTCUR = "OPTCUR"   # Currency options
    OPTCOM = "OPTCOM"   # Commodity options
    OPTFUT = "OPTFUT"   # Options on futures
