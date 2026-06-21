/* ============================================================
   Nubra Margin Calculator — Market Data Service
   ------------------------------------------------------------
   Mock spot/LTP data is used for the payoff chart and option
   pricing model. Real lot sizes, expiries, and strikes are
   loaded asynchronously from /api/catalog and /api/strikes.
   Margin figures come from the real Angel One SPAN API via
   /api/margin (calcMarginAsync).

   To wire a live market data feed later, replace the TICKER,
   INSTRUMENTS spot/change values, and _priceOption() — the
   rest of the engine and all UI bindings stay unchanged.
   ============================================================ */
(function (global) {
  "use strict";

  /* Idempotent: the DC helmet can inject this script more than once. Keep a single
     module instance so there is one _updateCbs list, one catalog fetch, and the
     onUpdate hook always fires on the module that getStrikes/_fetchStrikes use. */
  if (global.MarketData) return;

  /* ---- Seed: instruments (mock spot/change; real lotSize patched from catalog) ---- */
  var INSTRUMENTS = {
    NIFTY:     { symbol: "NIFTY",     name: "Nifty 50",        exchange: "NFO", segment: "index",     lotSize: 75,   spot: 24800, change: 93.70,  strikeStep: 50 },
    BANKNIFTY: { symbol: "BANKNIFTY", name: "Nifty Bank",      exchange: "NFO", segment: "index",     lotSize: 35,   spot: 52000, change: 210.40, strikeStep: 100 },
    FINNIFTY:  { symbol: "FINNIFTY",  name: "Nifty Financial", exchange: "NFO", segment: "index",     lotSize: 65,   spot: 23500, change: 64.20,  strikeStep: 50 },
    MIDCPNIFTY:{ symbol: "MIDCPNIFTY",name: "Nifty Midcap",    exchange: "NFO", segment: "index",     lotSize: 50,   spot: 12500, change: 45.00,  strikeStep: 25 },
    HDFCBANK:  { symbol: "HDFCBANK",  name: "HDFC Bank",       exchange: "NFO", segment: "stock",     lotSize: 550,  spot: 1680,  change: -8.60,  strikeStep: 20 },
    RELIANCE:  { symbol: "RELIANCE",  name: "Reliance Inds",   exchange: "NFO", segment: "stock",     lotSize: 500,  spot: 1450,  change: 12.35,  strikeStep: 10 },
    SENSEX:    { symbol: "SENSEX",    name: "BSE Sensex",      exchange: "BFO", segment: "index",     lotSize: 20,   spot: 81000, change: 312.50, strikeStep: 100 },
    BANKEX:    { symbol: "BANKEX",    name: "BSE Bankex",      exchange: "BFO", segment: "index",     lotSize: 15,   spot: 56000, change: 180.00, strikeStep: 100 },
    CRUDEOIL:  { symbol: "CRUDEOIL",  name: "Crude Oil",       exchange: "MCX", segment: "commodity", lotSize: 100,  spot: 6200,  change: -34.00, strikeStep: 50 },
    GOLD:      { symbol: "GOLD",      name: "Gold",            exchange: "MCX", segment: "commodity", lotSize: 100,  spot: 71000, change: 220.00, strikeStep: 100 },
  };
  Object.keys(INSTRUMENTS).forEach(function (k) {
    var i = INSTRUMENTS[k];
    i.changePct = Math.round((i.change / (i.spot || 1)) * 10000) / 100;
  });

  /* ---- Mock expiry fallback (used until catalog loads) ---- */
  var _MOCK_EXPIRIES = [
    { date: "2026-06-30", angel: "30JUN26", label: "30 Jun 2026", short: "30 Jun", type: "monthly", days: 11 },
    { date: "2026-07-28", angel: "28JUL26", label: "28 Jul 2026", short: "28 Jul", type: "monthly", days: 39 },
    { date: "2026-08-25", angel: "25AUG26", label: "25 Aug 2026", short: "25 Aug", type: "monthly", days: 67 },
  ];

  /* ---- Real catalog state ---- */
  var ALLOWED_EX       = ["NFO", "BFO", "MCX"];  // only these are surfaced
  var _realByKey       = {};   // "EXCHANGE:SYMBOL" -> instrument obj (per-exchange)
  var _realInstruments = [];   // flat list (same objects, catalog order)
  var _realExpiries    = {};   // { "2026-06-30": expiry-obj } — all known dates
  var _strikesCache    = {};   // { "NFO:OPTION:NIFTY-30JUN26:CALL": [24000, ...] }
  var _fetchingKeys    = {};   // in-flight strike requests
  var _updateCbs       = [];   // fired when new catalog / strike data arrives

  function _fireUpdate() {
    _updateCbs.forEach(function (cb) { try { cb(); } catch (e) {} });
  }

  function onUpdate(cb) { _updateCbs.push(cb); }

  /* ------------------------------------------------------------------ */
  /* Catalog init — fetches /api/catalog once on page load               */
  /* Serves localStorage cache instantly, then refreshes from API         */
  /* ------------------------------------------------------------------ */
  var _LS_KEY = 'nubra-catalog-v1';

  function _applyCatalogData(data) {
    var insts = data.instruments || [];
    var list = [];
    insts.forEach(function (inst) {
      if (ALLOWED_EX.indexOf(inst.exchange) < 0) return;  // 3 exchanges only
      var sym = inst.symbol, ex = inst.exchange, key = ex + ":" + sym;
      var seed = INSTRUMENTS[sym];               // mock seed (for spot/strikeStep)
      var obj = _realByKey[key] || {
        symbol: sym, name: seed ? seed.name : sym,
        exchange: ex,
        spot:       seed ? seed.spot       : 0,
        change:     seed ? seed.change     : 0,
        changePct:  seed ? seed.changePct  : 0,
        strikeStep: seed ? seed.strikeStep : 10,
      };
      obj.segment    = inst.segment;
      obj.lotSize    = inst.lotSize;
      obj.hasOptions = inst.hasOptions;
      obj.hasFutures = inst.hasFutures;
      obj._expByProd = inst.expiries;
      _realByKey[key] = obj;
      list.push(obj);
      ["OPTION", "FUTURE"].forEach(function (p) {
        (inst.expiries[p] || []).forEach(function (e) { _realExpiries[e.date] = e; });
      });
    });
    _realInstruments = list;
    _fireUpdate();
  }

  /* Resolve a (symbol, exchange) pair to its instrument object.
     With an exchange, returns that exact listing (NFO:DRREDDY vs BFO:DRREDDY).
     Without one, prefers NFO > BFO > MCX, then falls back to the mock seed. */
  function _resolve(symbol, exchange) {
    if (exchange && _realByKey[exchange + ":" + symbol]) return _realByKey[exchange + ":" + symbol];
    for (var i = 0; i < ALLOWED_EX.length; i++) {
      var e = _realByKey[ALLOWED_EX[i] + ":" + symbol];
      if (e) return e;
    }
    return INSTRUMENTS[symbol] || null;
  }

  function initCatalog() {
    /* 1. Instant load from localStorage (no network wait) */
    try {
      var stored = localStorage.getItem(_LS_KEY);
      if (stored) {
        var cached = JSON.parse(stored);
        if (cached && Array.isArray(cached.instruments) && cached.instruments.length > 0) {
          _applyCatalogData(cached);
        }
      }
    } catch (e) {}

    /* 2. Always fetch fresh from API — update UI + save to localStorage */
    fetch("/api/catalog")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _applyCatalogData(data);
        try { localStorage.setItem(_LS_KEY, JSON.stringify(data)); } catch (e) {}
      })
      .catch(function () { /* mock data still works as final fallback */ });
  }

  /* ------------------------------------------------------------------ */
  /* Strikes — background fetch, cached in memory                        */
  /* ------------------------------------------------------------------ */
  function _fetchStrikes(exchange, product, contract, symbol) {
    var callKey = exchange + ":" + product + ":" + contract + ":CALL";
    var putKey  = exchange + ":" + product + ":" + contract + ":PUT";
    if (_strikesCache[callKey] || _fetchingKeys[callKey]) return;

    _fetchingKeys[callKey] = true;
    var base = "/api/strikes?exchange=" + encodeURIComponent(exchange) +
               "&product="   + encodeURIComponent(product) +
               "&contract="  + encodeURIComponent(contract);

    Promise.all([
      fetch(base + "&optionType=CALL").then(function (r) { return r.json(); }),
      fetch(base + "&optionType=PUT" ).then(function (r) { return r.json(); }),
    ]).then(function (res) {
      var cStrikes = res[0].strikes || [];
      var pStrikes = res[1].strikes || [];
      _strikesCache[callKey] = cStrikes;
      _strikesCache[putKey]  = pStrikes;
      delete _fetchingKeys[callKey];

      /* Update strikeStep + derive a spot for the symbol from real strikes */
      if (symbol && cStrikes.length >= 2) {
        var step = cStrikes[1] - cStrikes[0];
        var inst = _resolve(symbol, exchange);
        if (inst) {
          if (step > 0) inst.strikeStep = step;
          /* Catalog has no spot for stocks — approximate with the median strike */
          if (!inst.spot) inst.spot = cStrikes[Math.floor(cStrikes.length / 2)];
        }
      }
      _fireUpdate();
    }).catch(function () { delete _fetchingKeys[callKey]; });
  }

  /* ------------------------------------------------------------------ */
  /* Expiry helpers                                                       */
  /* ------------------------------------------------------------------ */
  function _expiriesFor(symbol, productFilter, exchange) {
    var inst = _resolve(symbol, exchange);
    if (inst && inst._expByProd) {
      var key = productFilter || "OPTION";
      var exps = inst._expByProd[key];
      if (exps && exps.length) return exps.slice();
      /* Fall back to the other product's expiries */
      var other = key === "OPTION" ? "FUTURE" : "OPTION";
      exps = inst._expByProd[other];
      if (exps && exps.length) return exps.slice();
    }
    /* Mock fallback */
    var seg = inst ? inst.segment : "index";
    return seg === "index"
      ? _MOCK_EXPIRIES.slice()
      : _MOCK_EXPIRIES.filter(function (e) { return e.type === "monthly"; });
  }

  function _expiryByDate(dateStr) {
    if (_realExpiries[dateStr]) return _realExpiries[dateStr];
    for (var i = 0; i < _MOCK_EXPIRIES.length; i++) {
      if (_MOCK_EXPIRIES[i].date === dateStr) return _MOCK_EXPIRIES[i];
    }
    /* Last resort: return first known real expiry or mock */
    var keys = Object.keys(_realExpiries);
    return keys.length ? _realExpiries[keys[0]] : _MOCK_EXPIRIES[0];
  }

  /* ------------------------------------------------------------------ */
  /* Mock pricing model (illustrative LTP — not live quotes)             */
  /* ------------------------------------------------------------------ */
  function round2(n) { return Math.round(n * 100) / 100; }

  function _atmOf(symbol, exchange) {
    var inst = _resolve(symbol, exchange);
    if (!inst) return 0;

    /* If real strikes are cached use the median as ATM approximation */
    if (inst._expByProd && inst.exchange) {
      var optExps = inst._expByProd["OPTION"] || [];
      if (optExps.length) {
        var exp = optExps[0];
        var cKey = inst.exchange + ":OPTION:" + symbol + "-" + exp.angel + ":CALL";
        var strikes = _strikesCache[cKey];
        if (strikes && strikes.length) {
          return strikes[Math.floor(strikes.length / 2)];
        }
      }
    }
    var spot = inst.spot || 0;
    var step = inst.strikeStep || 50;
    return Math.round(spot / step) * step;
  }

  function _priceOption(symbol, strike, opt, days, exchange) {
    var inst = _resolve(symbol, exchange);
    var spot = inst ? (inst.spot || 0) : 0;
    if (!spot) return 0;
    var intrinsic = opt === "CE" ? Math.max(spot - strike, 0) : Math.max(strike - spot, 0);
    var atmTV = spot * 0.012 * Math.sqrt(Math.max(days, 1) / 30);
    var dist  = Math.abs(strike - spot) / spot;
    var tv    = atmTV * Math.exp(-Math.pow(dist / 0.05, 2));
    return round2(intrinsic + tv);
  }

  /* ======================  PUBLIC ACCESSORS  ====================== */

  function getExchanges() {
    if (_realInstruments.length) {
      var seen = {};
      _realInstruments.forEach(function (i) { seen[i.exchange] = true; });
      return ALLOWED_EX.filter(function (e) { return seen[e]; });
    }
    return ALLOWED_EX.slice();
  }

  function getProducts(/* exchange */) {
    return ["Options", "Futures"];
  }

  /* segment filter: "index" | "stock" | "commodity" | undefined (all) */
  function getInstruments(exchange, segment) {
    var source = _realInstruments.length
      ? _realInstruments
      : Object.keys(INSTRUMENTS).map(function (k) { return INSTRUMENTS[k]; });
    return source.filter(function (i) {
      return (!exchange || i.exchange === exchange) &&
             (!segment  || i.segment  === segment);
    });
  }

  function getInstrument(symbol, exchange) { return _resolve(symbol, exchange); }

  /* productFilter: "OPTION" | "FUTURE" | undefined  (defaults to OPTION) */
  function getExpiries(symbol, productFilter, exchange) {
    return _expiriesFor(symbol, productFilter, exchange);
  }

  function getStrikes(symbol, expiryDate, exchange) {
    var inst = _resolve(symbol, exchange);
    if (!inst) return [];
    var ex = inst.exchange;

    var expObj = _realExpiries[expiryDate] || _expiryByDate(expiryDate);
    var days   = expObj ? expObj.days : 30;
    var angel  = expObj ? expObj.angel : null;

    if (ex && angel) {
      var contract = symbol + "-" + angel;
      var callKey  = ex + ":OPTION:" + contract + ":CALL";
      var putKey   = ex + ":OPTION:" + contract + ":PUT";

      if (_strikesCache[callKey] && _strikesCache[putKey]) {
        /* Real strikes available — attach mock LTPs */
        return _strikesCache[callKey].map(function (s) {
          var ce = _priceOption(symbol, s, "CE", days, ex);
          var pe = _priceOption(symbol, s, "PE", days, ex);
          return { strike: s, ce: { ltp: ce, price: ce }, pe: { ltp: pe, price: pe } };
        });
      }
      /* Trigger background fetch; return mock while loading */
      _fetchStrikes(ex, "OPTION", contract, symbol);
    }

    /* Mock fallback — generate synthetic strikes around ATM */
    var atm  = _atmOf(symbol, ex);
    if (!atm) return [];
    var step = inst.strikeStep || 50;
    var out  = [];
    for (var k = -12; k <= 12; k++) {
      var s = atm + k * step;
      if (s <= 0) continue;
      var ce = _priceOption(symbol, s, "CE", days, ex);
      var pe = _priceOption(symbol, s, "PE", days, ex);
      out.push({ strike: s, ce: { ltp: ce, price: ce }, pe: { ltp: pe, price: pe } });
    }
    return out;
  }

  function getQuote(symbol, expiryDate, strike, opt, exchange) {
    var expObj = _expiryByDate(expiryDate);
    var days   = expObj ? expObj.days : 30;
    var p = _priceOption(symbol, strike, opt, days, exchange);
    return { ltp: p, price: p };
  }

  /* Real (exchange-sourced) strike numbers for a contract, or [] if not yet
     loaded. Used to snap a draft strike onto a valid value once strikes arrive. */
  function getStrikeList(symbol, expiryDate, exchange) {
    var inst = _resolve(symbol, exchange);
    if (!inst || !inst.exchange) return [];
    var expObj = _realExpiries[expiryDate] || _expiryByDate(expiryDate);
    var angel  = expObj ? expObj.angel : null;
    if (!angel) return [];
    var callKey = inst.exchange + ":OPTION:" + symbol + "-" + angel + ":CALL";
    return _strikesCache[callKey] ? _strikesCache[callKey].slice() : [];
  }

  /* ---- Sync margin calc (mock — used as immediate placeholder) ---- */
  var _RATES = {
    index:     { span: 0.060, expo: 0.035 },
    stock:     { span: 0.105, expo: 0.050 },
    commodity: { span: 0.085, expo: 0.045 },
    currency:  { span: 0.040, expo: 0.020 },
  };
  function _exCode(ex) { return ex === "NFO" ? "nse_fo" : ex === "BFO" ? "bse_fo" : "mcx_fo"; }
  function _prodCode(seg, isOpt) {
    if (seg === "index")     return isOpt ? "OPTIDX" : "FUTIDX";
    if (seg === "commodity") return isOpt ? "OPTFUT" : "FUTCOM";
    return isOpt ? "OPTSTK" : "FUTSTK";
  }

  function calcMargin(legs) {
    var perLeg = legs.map(function (l) {
      var inst     = _resolve(l.symbol, l.exchange) || { lotSize: 1, spot: 0, segment: "stock", exchange: l.exchange || "NFO" };
      var lot      = inst.lotSize, spot = inst.spot || 0, qty = l.lots * lot;
      var r        = _RATES[inst.segment] || _RATES.stock;
      var isOpt    = l.product === "Options";
      var px       = l.price != null ? l.price
                   : (isOpt ? getQuote(l.symbol, l.expiry, l.strike, l.optionType, l.exchange).price : spot);
      var shortRisk = l.product === "Futures" || (isOpt && l.tradeType === "SELL");
      var span = 0, expo = 0, total = 0;
      if (shortRisk) { span = spot * qty * r.span; expo = spot * qty * r.expo; total = span + expo; }
      else           { total = px * qty; }
      var prem = (l.tradeType === "SELL" ? -1 : 1) * px * qty;
      return {
        _short: shortRisk, premium: round2(prem),
        exchange:      _exCode(inst.exchange),
        contract:      l.symbol + "-" + l.expiry + (isOpt ? "-" + l.strike + l.optionType : "-FUT"),
        product:       _prodCode(inst.segment, isOpt),
        strikePrice:   isOpt ? Number(l.strike).toFixed(2) : "0.00",
        qty: qty, instrumentType: _prodCode(inst.segment, isOpt),
        tradeType: l.tradeType, optionType: isOpt ? (l.optionType === "CE" ? "C" : "P") : "",
        SPANMargin: round2(span), exposureMargin: round2(expo), totalMargin: round2(total),
      };
    });

    var tpm      = perLeg.reduce(function (a, p) { return a + p.totalMargin; }, 0);
    var soldSpan = perLeg.filter(function (p) { return p._short; }).reduce(function (a, p) { return a + p.SPANMargin; }, 0);
    var soldExpo = perLeg.filter(function (p) { return p._short; }).reduce(function (a, p) { return a + p.exposureMargin; }, 0);
    var bPrem    = perLeg.filter(function (p) { return !p._short; }).reduce(function (a, p) { return a + p.totalMargin; }, 0);
    var nShort   = perLeg.filter(function (p) { return p._short; }).length;
    var nLong    = legs.filter(function (l) { return l.product === "Options" && l.tradeType === "BUY"; }).length;
    var hedge    = (nShort > 0 && nLong > 0 && legs.length >= 2) ? Math.min(0.82, 0.34 * nLong) : 0;
    var nSpan    = soldSpan * (1 - hedge);
    var nExpo    = soldExpo * (1 - hedge);
    var totalM   = nSpan + nExpo + bPrem;
    var netPrem  = perLeg.reduce(function (a, p) { return a + p.premium; }, 0);

    var clean = perLeg.map(function (p) {
      return {
        premium: p.premium, exchange: p.exchange, contract: p.contract, product: p.product,
        strikePrice: p.strikePrice, qty: p.qty, instrumentType: p.instrumentType,
        tradeType: p.tradeType, optionType: p.optionType,
        SPANMargin: p.SPANMargin, exposureMargin: p.exposureMargin, totalMargin: p.totalMargin,
      };
    });
    return {
      margin: {
        netPremium: round2(netPrem), SPANMargin: round2(nSpan), exposureMargin: round2(nExpo),
        totalMargin: round2(totalM), marginBenefit: round2(tpm - totalM),
        deliveryMargin: 0, additionalMargin: 0, tenderMargin: 0,
        specialMargin: 0, additionalPreExpiryMargin: 0,
      },
      totalPositionMargin: round2(tpm),
      positionMargin: clean,
    };
  }

  /* ---- Async margin — real Angel One SPAN API ---- */
  function calcMarginAsync(legs) {
    var enriched = legs.map(function (leg) {
      var inst = _resolve(leg.symbol, leg.exchange) || {};
      return Object.assign({}, leg, { qty: leg.lots * (inst.lotSize || 1) });
    });
    return fetch("/api/margin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ legs: enriched }),
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  /* ---- Ticker (mock — replace getTickerQuotes with live feed) ---- */
  var _TICKER = [
    { symbol: "NIFTY 50",   price: 24800, change: 93.70 },
    { symbol: "BANK NIFTY", price: 52000, change: 210.40 },
    { symbol: "FINNIFTY",   price: 23500, change: 64.20 },
    { symbol: "SENSEX",     price: 81000, change: 312.50 },
    { symbol: "RELIANCE",   price: 1450,  change: 12.35 },
    { symbol: "HDFCBANK",   price: 1680,  change: -8.60 },
    { symbol: "TCS",        price: 3920,  change: 28.45 },
    { symbol: "INFOSYS",    price: 1550,  change: 6.90 },
    { symbol: "ICICIBANK",  price: 1235,  change: -4.15 },
    { symbol: "SBIN",       price: 842,   change: 9.30 },
  ];
  function getTickerQuotes() {
    return _TICKER.map(function (t) {
      return {
        symbol: t.symbol, price: t.price, change: t.change,
        changePct: Math.round((t.change / t.price) * 10000) / 100,
        up: t.change >= 0,
      };
    });
  }

  /* ---- Greeks (illustrative — based on mock spot) ---- */
  function getGreeks(legs) {
    var g = { delta: 0, theta: 0, gamma: 0, vega: 0 };
    legs.forEach(function (l) {
      var inst = _resolve(l.symbol, l.exchange);
      if (!inst || !inst.spot) return;
      var qty  = l.lots * inst.lotSize;
      var sign = l.tradeType === "SELL" ? -1 : 1;
      if (l.product === "Futures") { g.delta += sign * qty; return; }
      var spot = inst.spot, strike = l.strike;
      var expObj = _expiryByDate(l.expiry);
      var days   = expObj ? expObj.days : 30;
      var t      = Math.max(days, 1) / 365;
      var denom  = spot * 0.06 * Math.sqrt(Math.max(days, 1) / 30) || 1;
      var m      = (spot - strike) / denom;
      var cd     = 1 / (1 + Math.exp(-m));
      var d      = l.optionType === "CE" ? cd : (cd - 1);
      var nd     = Math.exp(-m * m / 2) / Math.sqrt(2 * Math.PI);
      g.delta += sign * d * qty;
      g.gamma += sign * (nd / denom) * qty;
      g.vega  += sign * (spot * nd * Math.sqrt(t) * 0.01) * qty;
      g.theta += sign * (-(spot * 0.18 * nd) / (2 * Math.sqrt(t)) / 365) * qty;
    });
    return {
      delta: Math.round(g.delta * 100) / 100,
      theta: Math.round(g.theta),
      gamma: Math.round(g.gamma * 10000) / 10000,
      vega:  Math.round(g.vega),
    };
  }

  /* ---- Boot ---- */
  initCatalog();

  global.MarketData = {
    getExchanges:    getExchanges,
    getProducts:     getProducts,
    getInstruments:  getInstruments,
    getInstrument:   getInstrument,
    getExpiries:     getExpiries,
    getStrikes:      getStrikes,
    getStrikeList:   getStrikeList,
    getQuote:        getQuote,
    getTickerQuotes: getTickerQuotes,
    getGreeks:       getGreeks,
    calcMargin:      calcMargin,
    calcMarginAsync: calcMarginAsync,
    onUpdate:        onUpdate,
    _atmOf:          _atmOf,
    _expiryByDate:   _expiryByDate,
  };
})(window);
