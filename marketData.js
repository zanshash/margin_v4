/* ============================================================
   Nubra Margin Calculator — Mock Market Data + Data Service
   ------------------------------------------------------------
   This is the ONLY place market/margin data lives. The UI reads
   exclusively through the accessor functions exposed on
   window.MarketData. To connect a real backend later, replace the
   bodies of the accessor functions with API calls — the returned
   data SHAPES and the UI stay unchanged.

   Shapes
     instrument  = { symbol, name, exchange, segment, lotSize, spot, change, changePct, strikeStep }
     expiry      = { date:"2026-07-31", label:"31 Jul 2026", short:"31 Jul", type:"weekly|monthly", days }
     strikeQuote = { strike, ce:{ ltp, price }, pe:{ ltp, price } }
     marginResp  = { margin:{ netPremium, SPANMargin, exposureMargin, totalMargin,
                              marginBenefit, deliveryMargin, additionalMargin,
                              tenderMargin, specialMargin, additionalPreExpiryMargin },
                     totalPositionMargin, positionMargin:[ leg... ] }
   ============================================================ */
(function (global) {
  "use strict";

  /* ---- Seed: instruments -------------------------------------------------- */
  var INSTRUMENTS = {
    NIFTY:     { symbol: "NIFTY",     name: "Nifty 50",        exchange: "NFO", segment: "index",     lotSize: 75,   spot: 24800, change: 93.70,  strikeStep: 50 },
    BANKNIFTY: { symbol: "BANKNIFTY", name: "Nifty Bank",      exchange: "NFO", segment: "index",     lotSize: 35,   spot: 52000, change: 210.40, strikeStep: 100 },
    FINNIFTY:  { symbol: "FINNIFTY",  name: "Nifty Financial", exchange: "NFO", segment: "index",     lotSize: 65,   spot: 23500, change: 64.20,  strikeStep: 50 },
    HDFCBANK:  { symbol: "HDFCBANK",  name: "HDFC Bank",       exchange: "NFO", segment: "stock",     lotSize: 550,  spot: 1680,  change: -8.60,  strikeStep: 20 },
    RELIANCE:  { symbol: "RELIANCE",  name: "Reliance Inds",   exchange: "NFO", segment: "stock",     lotSize: 500,  spot: 1450,  change: 12.35,  strikeStep: 10 },
    SENSEX:    { symbol: "SENSEX",    name: "BSE Sensex",      exchange: "BFO", segment: "index",     lotSize: 20,   spot: 81000, change: 312.50, strikeStep: 100 },
    CRUDEOIL:  { symbol: "CRUDEOIL",  name: "Crude Oil",       exchange: "MCX", segment: "commodity", lotSize: 100,  spot: 6200,  change: -34.00, strikeStep: 50 },
    GOLD:      { symbol: "GOLD",      name: "Gold",            exchange: "MCX", segment: "commodity", lotSize: 100,  spot: 71000, change: 220.00, strikeStep: 100 },
  };
  Object.keys(INSTRUMENTS).forEach(function (k) {
    var i = INSTRUMENTS[k];
    i.changePct = Math.round((i.change / i.spot) * 10000) / 100;
  });

  /* ---- Seed: expiries (weekly + monthly) ---------------------------------- */
  var EXPIRIES = [
    { date: "2026-06-25", label: "25 Jun 2026", short: "25 Jun", type: "weekly",  days: 7 },
    { date: "2026-07-31", label: "31 Jul 2026", short: "31 Jul", type: "monthly", days: 43 },
    { date: "2026-08-28", label: "28 Aug 2026", short: "28 Aug", type: "monthly", days: 71 },
  ];
  function expiriesFor(symbol) {
    var inst = INSTRUMENTS[symbol];
    var seg = inst ? inst.segment : "index";
    // indices trade weekly + monthly; stocks & commodities monthly only
    return seg === "index" ? EXPIRIES.slice() : EXPIRIES.filter(function (e) { return e.type === "monthly"; });
  }
  function expiryByDate(date) {
    for (var i = 0; i < EXPIRIES.length; i++) if (EXPIRIES[i].date === date) return EXPIRIES[i];
    return EXPIRIES[1];
  }

  /* ---- Risk rates by segment (SPAN % + exposure %) ------------------------ */
  var RATES = {
    index:     { span: 0.060, expo: 0.035 },
    stock:     { span: 0.105, expo: 0.050 },
    commodity: { span: 0.085, expo: 0.045 },
  };

  /* ---- Pricing model (illustrative LTP) ----------------------------------- */
  function round2(n) { return Math.round(n * 100) / 100; }
  function atmOf(symbol) { var i = INSTRUMENTS[symbol]; return Math.round(i.spot / i.strikeStep) * i.strikeStep; }
  function priceOption(symbol, strike, opt, days) {
    var i = INSTRUMENTS[symbol], spot = i.spot;
    var intrinsic = opt === "CE" ? Math.max(spot - strike, 0) : Math.max(strike - spot, 0);
    var atmTV = spot * 0.012 * Math.sqrt(days / 30);
    var dist = Math.abs(strike - spot) / spot;
    var tv = atmTV * Math.exp(-Math.pow(dist / 0.05, 2));
    return round2(intrinsic + tv);
  }

  /* ======================  ACCESSORS  ====================== */

  function getExchanges() { return ["NFO", "BFO", "MCX"]; }

  function getProducts(/* exchange */) { return ["Options", "Futures"]; }

  function getInstruments(exchange) {
    return Object.keys(INSTRUMENTS)
      .map(function (k) { return INSTRUMENTS[k]; })
      .filter(function (i) { return !exchange || i.exchange === exchange; });
  }

  function getInstrument(symbol) { return INSTRUMENTS[symbol]; }

  function getExpiries(symbol) { return expiriesFor(symbol); }

  function getStrikes(symbol, expiryDate) {
    var inst = INSTRUMENTS[symbol];
    if (!inst) return [];
    var atm = atmOf(symbol), days = expiryByDate(expiryDate).days, out = [];
    for (var k = -12; k <= 12; k++) {
      var s = atm + k * inst.strikeStep;
      if (s <= 0) continue;
      var ce = priceOption(symbol, s, "CE", days);
      var pe = priceOption(symbol, s, "PE", days);
      out.push({ strike: s, ce: { ltp: ce, price: ce }, pe: { ltp: pe, price: pe } });
    }
    return out;
  }

  function getQuote(symbol, expiryDate, strike, opt) {
    var days = expiryByDate(expiryDate).days;
    var p = priceOption(symbol, strike, opt, days);
    return { ltp: p, price: p };
  }

  function exchangeCode(exchange) {
    return exchange === "NFO" ? "nse_fo" : exchange === "BFO" ? "bse_fo" : "mcx_fo";
  }
  function productCode(segment, isOpt) {
    if (segment === "index") return isOpt ? "OPTIDX" : "FUTIDX";
    if (segment === "commodity") return isOpt ? "OPTFUT" : "FUTCOM";
    return isOpt ? "OPTSTK" : "FUTSTK";
  }

  /* calcMargin(legs) -> full backend-shaped response.
     leg input = { exchange, product:"Options"|"Futures", symbol, expiry,
                   optionType:"CE"|"PE"|null, strike:number|null,
                   tradeType:"BUY"|"SELL", lots, price?:number }            */
  function calcMargin(legs) {
    var positionMargin = legs.map(function (l) {
      var inst = INSTRUMENTS[l.symbol];
      var lot = inst.lotSize, spot = inst.spot, qty = l.lots * lot;
      var r = RATES[inst.segment] || RATES.stock;
      var isOpt = l.product === "Options";
      var px = (l.price != null) ? l.price
             : (isOpt ? getQuote(l.symbol, l.expiry, l.strike, l.optionType).price : spot);
      var shortRisk = (l.product === "Futures") || (isOpt && l.tradeType === "SELL");
      var span = 0, expo = 0, total = 0;
      if (shortRisk) { span = spot * qty * r.span; expo = spot * qty * r.expo; total = span + expo; }
      else { total = px * qty; }
      // brief sign convention: sold legs negative
      var prem = (l.tradeType === "SELL" ? -1 : 1) * px * qty;
      return {
        premium: round2(prem),
        exchange: exchangeCode(inst.exchange),
        contract: l.symbol + "-" + l.expiry + (isOpt ? ("-" + l.strike + l.optionType) : "-FUT"),
        product: productCode(inst.segment, isOpt),
        strikePrice: isOpt ? Number(l.strike).toFixed(2) : "0.00",
        qty: qty,
        instrumentType: productCode(inst.segment, isOpt),
        tradeType: l.tradeType,
        optionType: isOpt ? (l.optionType === "CE" ? "C" : "P") : "",
        SPANMargin: round2(span),
        exposureMargin: round2(expo),
        totalMargin: round2(total),
        shortRisk: shortRisk,
      };
    });

    var totalPositionMargin = positionMargin.reduce(function (a, p) { return a + p.totalMargin; }, 0);
    var soldSpan = positionMargin.filter(function (p) { return p.shortRisk; }).reduce(function (a, p) { return a + p.SPANMargin; }, 0);
    var soldExpo = positionMargin.filter(function (p) { return p.shortRisk; }).reduce(function (a, p) { return a + p.exposureMargin; }, 0);
    var boughtPrem = positionMargin.filter(function (p) { return !p.shortRisk; }).reduce(function (a, p) { return a + p.totalMargin; }, 0);
    var numLong = legs.filter(function (l) { return l.product === "Options" && l.tradeType === "BUY"; }).length;
    var numShort = positionMargin.filter(function (p) { return p.shortRisk; }).length;

    var hedge = 0;
    if (numShort > 0 && numLong > 0 && legs.length >= 2) hedge = Math.min(0.82, 0.34 * numLong);
    var nettedSpan = soldSpan * (1 - hedge);
    var nettedExpo = soldExpo * (1 - hedge);
    var totalMargin = nettedSpan + nettedExpo + boughtPrem;
    var marginBenefit = totalPositionMargin - totalMargin;
    var netPremium = positionMargin.reduce(function (a, p) { return a + p.premium; }, 0);

    // strip the private flag from the public per-leg payload
    var cleanLegs = positionMargin.map(function (p) {
      return {
        premium: p.premium, exchange: p.exchange, contract: p.contract, product: p.product,
        strikePrice: p.strikePrice, qty: p.qty, instrumentType: p.instrumentType,
        tradeType: p.tradeType, optionType: p.optionType,
        SPANMargin: p.SPANMargin, exposureMargin: p.exposureMargin, totalMargin: p.totalMargin,
      };
    });

    return {
      margin: {
        netPremium: round2(netPremium),
        SPANMargin: round2(nettedSpan),
        exposureMargin: round2(nettedExpo),
        totalMargin: round2(totalMargin),
        marginBenefit: round2(marginBenefit),
        deliveryMargin: 0, additionalMargin: 0, tenderMargin: 0,
        specialMargin: 0, additionalPreExpiryMargin: 0,
      },
      totalPositionMargin: round2(totalPositionMargin),
      positionMargin: cleanLegs,
    };
  }

  // Display-only ticker rows (indices + top stocks). A live feed can replace
  // getTickerQuotes() without any UI change.
  var TICKER = [
    { symbol: "NIFTY 50",  price: 24800,  change: 93.70 },
    { symbol: "BANK NIFTY", price: 52000, change: 210.40 },
    { symbol: "FINNIFTY",  price: 23500,  change: 64.20 },
    { symbol: "SENSEX",    price: 81000,  change: 312.50 },
    { symbol: "RELIANCE",  price: 1450,   change: 12.35 },
    { symbol: "HDFCBANK",  price: 1680,   change: -8.60 },
    { symbol: "TCS",       price: 3920,   change: 28.45 },
    { symbol: "INFOSYS",   price: 1550,   change: 6.90 },
    { symbol: "ICICIBANK", price: 1235,   change: -4.15 },
    { symbol: "SBIN",      price: 842,    change: 9.30 },
  ];
  function getTickerQuotes() {
    return TICKER.map(function (t) {
      return { symbol: t.symbol, price: t.price, change: t.change, changePct: Math.round((t.change / t.price) * 10000) / 100, up: t.change >= 0 };
    });
  }

  global.MarketData = {
    getExchanges: getExchanges,
    getProducts: getProducts,
    getInstruments: getInstruments,
    getInstrument: getInstrument,
    getExpiries: getExpiries,
    getStrikes: getStrikes,
    getQuote: getQuote,
    getTickerQuotes: getTickerQuotes,
    calcMargin: calcMargin,
    // small internal helpers the UI may use for ATM / expiry lookups
    _atmOf: atmOf,
    _expiryByDate: expiryByDate,
  };
})(window);
