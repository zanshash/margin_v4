from dataclasses import dataclass
from typing import List

from enums import Exchange, OptionType, Product, TradeType


@dataclass
class Position:
    contract: str           # e.g. "NIFTY-30JUN26", "BANKNIFTY-28JUL26"
    exchange: Exchange      # NFO, MCX, CDS, NCDEX, BFO, NSECOM
    product: Product        # FUTURE or OPTION
    qty: int                # units (= lots × lotSize)
    tradeType: TradeType    # BUY or SELL
    strikePrice: float = 0.0       # 0 for futures; actual strike for options
    optionType: OptionType = ""    # CALL or PUT (options only)

    def to_dict(self) -> dict:
        d = {
            "contract": self.contract,
            "exchange": str(self.exchange),
            "product": str(self.product),
            "qty": self.qty,
            "strikePrice": self.strikePrice,
            "tradeType": str(self.tradeType),
        }
        if self.optionType:
            d["optionType"] = str(self.optionType)
        return d


@dataclass
class MarginBreakdown:
    netPremium: float = 0.0
    SPANMargin: float = 0.0
    exposureMargin: float = 0.0
    totalMargin: float = 0.0
    marginBenefit: float = 0.0
    deliveryMargin: float = 0.0
    additionalMargin: float = 0.0
    tenderMargin: float = 0.0
    specialMargin: float = 0.0
    additionalPreExpiryMargin: float = 0.0


@dataclass
class PositionMargin:
    exchange: str
    contract: str
    product: str
    strikePrice: str
    qty: int
    instrumentType: str
    tradeType: str
    SPANMargin: float
    exposureMargin: float
    totalMargin: float


@dataclass
class MarginResponse:
    margin: MarginBreakdown
    totalPositionMargin: float
    positionMargin: List[PositionMargin]

    @classmethod
    def from_dict(cls, data: dict) -> "MarginResponse":
        m = data.get("margin", {})
        breakdown = MarginBreakdown(
            netPremium=m.get("netPremium", 0.0),
            SPANMargin=m.get("SPANMargin", 0.0),
            exposureMargin=m.get("exposureMargin", 0.0),
            totalMargin=m.get("totalMargin", 0.0),
            marginBenefit=m.get("marginBenefit", 0.0),
            deliveryMargin=m.get("deliveryMargin", 0.0),
            additionalMargin=m.get("additionalMargin", 0.0),
            tenderMargin=m.get("tenderMargin", 0.0),
            specialMargin=m.get("specialMargin", 0.0),
            additionalPreExpiryMargin=m.get("additionalPreExpiryMargin", 0.0),
        )
        positions = [
            PositionMargin(
                exchange=p["exchange"],
                contract=p["contract"],
                product=p["product"],
                strikePrice=p["strikePrice"],
                qty=p["qty"],
                instrumentType=p["instrumentType"],
                tradeType=p["tradeType"],
                SPANMargin=p["SPANMargin"],
                exposureMargin=p["exposureMargin"],
                totalMargin=p["totalMargin"],
            )
            for p in data.get("positionMargin", [])
        ]
        return cls(
            margin=breakdown,
            totalPositionMargin=data["totalPositionMargin"],
            positionMargin=positions,
        )
