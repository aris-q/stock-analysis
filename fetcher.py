import requests
import yfinance as yf
import logging
import math
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

def fetch_daily_gainers():
    us_gainers = fetch_us_gainers()
    cdn_gainers = fetch_cdn_gainers()
    return {"us": us_gainers, "cdn": cdn_gainers}


def fetch_us_gainers():
    try:
        screener = yf.screen("day_gainers")
        quotes = screener.get("quotes", [])
        gainers = [
            {
                "ticker": q.get("symbol"),
                "percentGain": round(q.get("regularMarketChangePercent", 0), 2),
                "price": q.get("regularMarketPrice"),
                "volume": q.get("regularMarketVolume"),
            }
            for q in quotes[:10]
        ]
        log.info(f"US gainers fetched: {len(gainers)}")
        return gainers
    except Exception as e:
        log.error(f"US gainers FAIL: {e}")
        return []


def fetch_cdn_gainers():
    try:
        r = requests.post(
            'https://app-money.tmx.com/graphql',
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Content-Type': 'application/json',
                'Origin': 'https://money.tmx.com',
                'Referer': 'https://money.tmx.com/'
            },
            json={'query': '{ getMarketMovers(statExchange: "TSX", sortOrder: "DESC", limit: 100) { symbol percentChange price volume } }'},
            timeout=10
        )
        data = r.json()
        movers = data.get('data', {}).get('getMarketMovers', [])
        gainers = [
            {
                "ticker": f"{m['symbol']}.TO",
                "percentGain": round(m['percentChange'], 2),
                "price": m['price'],
                "volume": m['volume'],
            }
            for m in movers
            if m.get('percentChange', 0) > 0
        ]
        gainers.sort(key=lambda x: x['percentGain'], reverse=True)
        top = gainers[:10]
        log.info(f"CDN gainers fetched: {len(top)}")
        return top
    except Exception as e:
        log.error(f"CDN gainers FAIL: {e}")
        return []

def fetch_news(ticker):
    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        filtered = []
        for item in news:
            try:
                content = item.get("content", {})
                pub_date_str = content.get("pubDate") or content.get("displayTime")
                if not pub_date_str:
                    continue
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                if pub_date < cutoff:
                    continue
                filtered.append({
                    "title": content.get("title", ""),
                    "summary": content.get("summary", ""),
                    "pubDate": pub_date_str,
                    "url": content.get("canonicalUrl", {}).get("url", ""),
                    "provider": content.get("provider", {}).get("displayName", ""),
                })
            except Exception as e:
                log.warning(f"News item parse FAIL: {ticker} | {e}")
                continue
        log.info(f"News fetched: {ticker} | {len(filtered)} articles (last 7 days)")
        return filtered
    except Exception as e:
        log.error(f"News FAIL: {ticker} | {e}")
        return []
    
def safe_get(df, field):
    try:
        if df is not None and field in df.index and not df.empty:
            val = df.loc[field].iloc[0]
            return None if val != val else int(val)
    except Exception:
        pass
    return None


def extract_periods(df, fields, max_periods):
    result = []
    if df is None or df.empty:
        return result
    cols = df.columns[:max_periods]
    for col in cols:
        period = {"date": str(col.date())}
        for field in fields:
            try:
                val = df.loc[field, col] if field in df.index else None
                period[field] = None if val != val else int(val)
            except Exception:
                period[field] = None
        result.append(period)
    return result


INCOME_FIELDS = [
    "Total Revenue",
    "Gross Profit",
    "Operating Income",
    "EBITDA",
    "Net Income",
    "Basic EPS",
    "Interest Expense",
    "Tax Provision",
    "Operating Expense",
    "Research And Development",
]

BALANCE_FIELDS = [
    "Cash And Cash Equivalents",
    "Total Debt",
    "Total Assets",
    "Total Liabilities Net Minority Interest",
    "Stockholders Equity",
    "Working Capital",
    "Current Assets",
    "Current Liabilities",
    "Long Term Debt",
    "Retained Earnings",
]

CASHFLOW_FIELDS = [
    "Operating Cash Flow",
    "Capital Expenditure",
    "Free Cash Flow",
    "Investing Cash Flow",
    "Financing Cash Flow",
    "Dividends Paid",
    "Repurchase Of Capital Stock",
    "Issuance Of Debt",
    "Repayment Of Debt",
    "Depreciation And Amortization",
]


from datetime import datetime, timezone

def epoch_to_date(ts):
    try:
        return str(datetime.fromtimestamp(ts, tz=timezone.utc).date())
    except Exception:
        return None

def fetch_yfinance(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        calendar = stock.calendar
        dividends = stock.dividends

        annual_income = stock.financials
        quarterly_income = stock.quarterly_financials
        annual_balance = stock.balance_sheet
        quarterly_balance = stock.quarterly_balance_sheet
        annual_cashflow = stock.cashflow
        quarterly_cashflow = stock.quarterly_cashflow

        calendar_data = {}
        if isinstance(calendar, dict):
            earnings_dates = calendar.get("Earnings Date", [])
            calendar_data = {
                "earningsDateStart": str(earnings_dates[0]) if len(earnings_dates) > 0 else None,
                "earningsDateEnd": str(earnings_dates[1]) if len(earnings_dates) > 1 else None,
                "earningsEPSHigh": calendar.get("Earnings High"),
                "earningsEPSLow": calendar.get("Earnings Low"),
                "earningsEPSAvg": calendar.get("Earnings Average"),
                "revenueEstimateHigh": calendar.get("Revenue High"),
                "revenueEstimateLow": calendar.get("Revenue Low"),
                "revenueEstimateAvg": calendar.get("Revenue Average"),
                "exDividendDate": str(calendar.get("Ex-Dividend Date")) if calendar.get("Ex-Dividend Date") else None,
                "dividendPayDate": str(calendar.get("Dividend Date")) if calendar.get("Dividend Date") else None,
            }
            log.info(f"Calendar OK: {ticker} | earnings:{calendar_data.get('earningsDateStart')} exDiv:{calendar_data.get('exDividendDate')}")
        else:
            log.warning(f"Calendar unexpected format: {ticker} | {type(calendar)}")

        events_data = {
            "dividendRate": info.get("dividendRate"),
            "dividendYield": info.get("dividendYield"),
            "trailingAnnualDividendRate": info.get("trailingAnnualDividendRate"),
            "fiveYearAvgDividendYield": info.get("fiveYearAvgDividendYield"),
            "lastDividendValue": info.get("lastDividendValue"),
            "lastDividendDate": epoch_to_date(info.get("lastDividendDate")) if info.get("lastDividendDate") else None,
            "exDividendDate": epoch_to_date(info.get("exDividendDate")) if info.get("exDividendDate") else None,
            "dividendDate": epoch_to_date(info.get("dividendDate")) if info.get("dividendDate") else None,
            "earningsTimestamp": epoch_to_date(info.get("earningsTimestamp")) if info.get("earningsTimestamp") else None,
            "earningsCallStart": epoch_to_date(info.get("earningsCallTimestampStart")) if info.get("earningsCallTimestampStart") else None,
            "earningsCallEnd": epoch_to_date(info.get("earningsCallTimestampEnd")) if info.get("earningsCallTimestampEnd") else None,
            "isEarningsDateEstimate": info.get("isEarningsDateEstimate"),
            "earningsGrowthYoY": info.get("earningsGrowth"),
            "earningsQuarterlyGrowth": info.get("earningsQuarterlyGrowth"),
            "lastSplitFactor": info.get("lastSplitFactor"),
            "lastSplitDate": epoch_to_date(info.get("lastSplitDate")) if info.get("lastSplitDate") else None,
        }
        log.info(f"Events OK: {ticker} | div_date:{events_data.get('dividendDate')} earnings_call:{events_data.get('earningsCallStart')}")

        recent_dividends = []
        if dividends is not None and not dividends.empty:
            recent_dividends = [
                {"date": str(d), "amount": float(v)}
                for d, v in dividends[-3:].items()
            ]

        log.info(f"yfinance OK: {ticker} | rev_annual:{safe_get(annual_income, 'Total Revenue')} rev_q:{safe_get(quarterly_income, 'Total Revenue')}")

        previous_close = None
        try:
            hist2 = stock.history(period="5d")
            if len(hist2) >= 2:
                previous_close = round(float(hist2['Close'].iloc[-2]), 2)
                log.info(f"previousClose OK: {ticker} | {previous_close}")
        except Exception as e:
            log.warning(f"previousClose FAIL: {ticker} | {e}")

        return {
            "price": info.get("currentPrice"),
            "previousClose": previous_close,
            "volume": info.get("volume"),
            "marketCap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "calendar": calendar_data,
            "events": events_data,
            "dividends": recent_dividends,
            "annualIncome": extract_periods(annual_income, INCOME_FIELDS, 3),
            "quarterlyIncome": extract_periods(quarterly_income, INCOME_FIELDS, 8),
            "annualBalance": extract_periods(annual_balance, BALANCE_FIELDS, 3),
            "quarterlyBalance": extract_periods(quarterly_balance, BALANCE_FIELDS, 8),
            "annualCashflow": extract_periods(annual_cashflow, CASHFLOW_FIELDS, 3),
            "quarterlyCashflow": extract_periods(quarterly_cashflow, CASHFLOW_FIELDS, 8),
        }
    except Exception as e:
        log.error(f"yfinance FAIL: {ticker} | {e}")
        return None


# def fetch_daily_gainers():
#     try:
#         screener = yf.screen("day_gainers")
#         quotes = screener.get("quotes", [])
#         gainers = [
#             {
#                 "ticker": q.get("symbol"),
#                 "percentGain": round(q.get("regularMarketChangePercent", 0), 2),
#                 "price": q.get("regularMarketPrice"),
#                 "volume": q.get("regularMarketVolume"),
#             }
#             for q in quotes
#             if q.get("symbol", "").endswith(".TO")
#         ][:10]
#         log.info(f"Daily gainers (.TO) fetched: {len(gainers)}")
#         return gainers
#     except Exception as e:
#         log.error(f"Daily gainers FAIL: {e}")
#         return []

def clean_float(v):
    if v is None:
        return None
    try:
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 2)
    except Exception:
        return None

def fetch_price_context(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="35d")
        if hist.empty:
            log.warning(f"Price context empty: {ticker}")
            return {}

        current_price = hist['Close'].iloc[-1]
        price_1d_ago = hist['Close'].iloc[-2] if len(hist) >= 2 else None
        price_7d_ago = hist['Close'].iloc[-7] if len(hist) >= 7 else None
        price_30d_ago = hist['Close'].iloc[-30] if len(hist) >= 30 else None

        vol_today = hist['Volume'].iloc[-1]
        vol_avg_30d = hist['Volume'].iloc[-30:].mean()
        vol_ratio = round(vol_today / vol_avg_30d, 2) if vol_avg_30d else None

        def pct(current, prev):
            if prev and prev != 0:
                return round((current - prev) / prev * 100, 2)
            return None

        # RSI calculation (14-day)
        delta = hist['Close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        _rsi_val = rsi_series.iloc[-1]
        rsi = round(float(_rsi_val), 1) if not rsi_series.empty and not math.isnan(float(_rsi_val)) else None

        # 20-day and 50-day moving averages
        ma20 = round(hist['Close'].rolling(20).mean().iloc[-1], 2) if len(hist) >= 20 else None
        _ma50_val = hist['Close'].rolling(50).mean().iloc[-1]
        ma50 = round(float(_ma50_val), 2) if not math.isnan(float(_ma50_val)) else None
        
        # Bollinger Bands %B (20-day, 2 std)
        bb_percent = None
        try:
            close = hist['Close']
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std
            last_close = close.iloc[-1]
            last_upper = bb_upper.iloc[-1]
            last_lower = bb_lower.iloc[-1]
            band_width = last_upper - last_lower
            if band_width and band_width != 0:
                bb_percent = round((last_close - last_lower) / band_width, 3)
        except Exception as e:
            log.warning(f"BB%B calc FAIL: {ticker} | {e}")

        context = {
            "currentPrice": clean_float(current_price),
            "change1d": clean_float(pct(current_price, price_1d_ago)),
            "change7d": clean_float(pct(current_price, price_7d_ago)),
            "change30d": clean_float(pct(current_price, price_30d_ago)),
            "volumeToday": int(vol_today),
            "volumeAvg30d": int(vol_avg_30d),
            "volumeRatio": clean_float(vol_ratio),
            "rsi14": clean_float(rsi),
            "bbPercent": clean_float(bb_percent),
            "ma20": clean_float(ma20),
            "ma50": clean_float(ma50),
            "priceVsMa20": clean_float(pct(current_price, ma20) if ma20 else None),
            "priceVsMa50": clean_float(pct(current_price, ma50) if ma50 else None),
        }
        log.info(f"Price context OK: {ticker} | rsi:{rsi} bbPct:{bb_percent} vol_ratio:{vol_ratio} 7d:{context['change7d']}%")
        return context
    except Exception as e:
        log.error(f"Price context FAIL: {ticker} | {e}")
        return {}

def fetch_price_only(ticker):
    """Price + technicals fetch: price, previousClose, volume, marketCap, rsi14, bbPercent."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="35d")

        previous_close = None
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        if len(hist) >= 2:
            previous_close = round(float(hist['Close'].iloc[-2]), 2)
        if current_price is None and not hist.empty:
            current_price = round(float(hist['Close'].iloc[-1]), 2)

        rsi = None
        bb_percent = None
        try:
            delta = hist['Close'].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            _rsi_val = rsi_series.iloc[-1]
            rsi = round(float(_rsi_val), 1) if not rsi_series.empty and not math.isnan(float(_rsi_val)) else None
        except Exception as e:
            log.warning(f"RSI calc FAIL in fetch_price_only: {ticker} | {e}")

        try:
            close = hist['Close']
            bb_mid = close.rolling(20).mean()
            bb_std = close.rolling(20).std()
            bb_upper = bb_mid + 2 * bb_std
            bb_lower = bb_mid - 2 * bb_std
            last_close = close.iloc[-1]
            band_width = bb_upper.iloc[-1] - bb_lower.iloc[-1]
            if band_width and band_width != 0:
                bb_percent = round(float((last_close - bb_lower.iloc[-1]) / band_width), 3)
        except Exception as e:
            log.warning(f"BB%B calc FAIL in fetch_price_only: {ticker} | {e}")

        result = {
            "price": current_price,
            "previousClose": previous_close,
            "volume": info.get("volume"),
            "marketCap": info.get("marketCap"),
            "rsi14": rsi,
            "bbPercent": bb_percent,
        }
        log.info(f"fetch_price_only OK: {ticker} | price:{current_price} prevClose:{previous_close} rsi:{rsi} bb:{bb_percent}")
        return result
    except Exception as e:
        log.error(f"fetch_price_only FAIL: {ticker} | {e}")
        return None


# ── MACRO DATA ────────────────────────────────────────────────────────────────

FRED_SERIES = {
    "fed_rate":       {"id": "FEDFUNDS",   "label": "Fed Funds Rate",      "unit": "%"},
    "cpi":            {"id": "CPIAUCSL",   "label": "CPI (YoY)",           "unit": "%",  "yoy": True},
    "unemployment":   {"id": "UNRATE",     "label": "Unemployment Rate",   "unit": "%"},
    "gdp_growth":     {"id": "A191RL1Q225SBEA", "label": "GDP Growth",     "unit": "%"},
    "ten_yr_yield":   {"id": "DGS10",      "label": "10-Yr Treasury Yield","unit": "%"},
    "two_yr_yield":   {"id": "DGS2",       "label": "2-Yr Treasury Yield", "unit": "%"},
    "vix":            {"id": "VIXCLS",     "label": "VIX (Fear Index)",    "unit": ""},
    "dollar_index":   {"id": "DTWEXBGS",   "label": "USD Dollar Index",    "unit": ""},
    "oil_wti":        {"id": "DCOILWTICO", "label": "WTI Crude Oil",       "unit": "$"},
    "sp500":          {"id": "SP500",      "label": "S&P 500",             "unit": ""},
}

def fetch_fred_series(series_id, api_key, limit=2):
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
            f"&sort_order=desc&limit={limit}"
        )
        r = requests.get(url, timeout=10)
        obs = r.json().get("observations", [])
        valid = [o for o in obs if o.get("value") not in (".", None, "")]
        return valid
    except Exception as e:
        log.warning(f"FRED FAIL: {series_id} | {e}")
        return []

def fetch_macro_data(fred_api_key, newsapi_key=None):
    log.info("=== Macro fetch started ===")
    indicators = {}

    for key, cfg in FRED_SERIES.items():
        obs = fetch_fred_series(cfg["id"], fred_api_key, limit=14 if cfg.get("yoy") else 2)
        if not obs:
            indicators[key] = {"label": cfg["label"], "value": None, "date": None, "unit": cfg["unit"], "change": None}
            continue
        try:
            latest = float(obs[0]["value"])
            prev   = float(obs[1]["value"]) if len(obs) > 1 else None
            # YoY calculation (CPI: compare to 12 months ago = ~obs[12])
            if cfg.get("yoy") and len(obs) >= 13:
                year_ago = float(obs[12]["value"])
                change = round(((latest - year_ago) / year_ago) * 100, 2)
            else:
                change = round(latest - prev, 2) if prev is not None else None
            indicators[key] = {
                "label":  cfg["label"],
                "value":  round(latest, 2),
                "prev":   round(prev, 2) if prev is not None else None,
                "change": change,
                "date":   obs[0]["date"],
                "unit":   cfg["unit"],
            }
            log.info(f"FRED OK: {key} | {latest} ({obs[0]['date']})")
        except Exception as e:
            log.warning(f"FRED parse FAIL: {key} | {e}")
            indicators[key] = {"label": cfg["label"], "value": None, "date": None, "unit": cfg["unit"], "change": None}

    # Yield curve spread
    try:
        t10 = indicators.get("ten_yr_yield", {}).get("value")
        t2  = indicators.get("two_yr_yield",  {}).get("value")
        if t10 is not None and t2 is not None:
            indicators["yield_curve"] = {
                "label": "Yield Curve (10Y-2Y)",
                "value": round(t10 - t2, 2),
                "unit":  "%",
                "date":  indicators["ten_yr_yield"]["date"],
                "change": None,
            }
    except Exception:
        pass

    # Headlines — NewsAPI if key provided, else fallback to yfinance market news
    headlines = []
    if newsapi_key and newsapi_key not in ("your_newsapi_key_here", "", None):
        try:
            r = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"category": "business", "language": "en", "pageSize": 10, "apiKey": newsapi_key},
                timeout=10
            )
            articles = r.json().get("articles", [])
            headlines = [
                {"title": a.get("title",""), "source": a.get("source",{}).get("name",""), "url": a.get("url",""), "publishedAt": a.get("publishedAt","")}
                for a in articles if a.get("title")
            ]
            log.info(f"NewsAPI OK: {len(headlines)} headlines")
        except Exception as e:
            log.warning(f"NewsAPI FAIL: {e}")

    # Fallback: pull news from a few major market tickers via yfinance
    if not headlines:
        log.info("Headlines: falling back to yfinance news (SPY, QQQ, GLD)")
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=3)
            seen = set()
            for sym in ["SPY", "QQQ", "GLD", "TLT"]:
                try:
                    stock = yf.Ticker(sym)
                    for item in (stock.news or []):
                        content_block = item.get("content", {})
                        title = content_block.get("title", "")
                        if not title or title in seen:
                            continue
                        pub = content_block.get("pubDate") or content_block.get("displayTime", "")
                        try:
                            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                            if pub_dt < cutoff:
                                continue
                        except Exception:
                            pass
                        seen.add(title)
                        headlines.append({
                            "title": title,
                            "source": content_block.get("provider", {}).get("displayName", sym),
                            "url": content_block.get("canonicalUrl", {}).get("url", ""),
                            "publishedAt": pub,
                        })
                        if len(headlines) >= 12:
                            break
                except Exception as e:
                    log.warning(f"yfinance news FAIL: {sym} | {e}")
                if len(headlines) >= 12:
                    break
            log.info(f"yfinance fallback headlines: {len(headlines)}")
        except Exception as e:
            log.warning(f"Headlines fallback FAIL: {e}")

    log.info("=== Macro fetch complete ===")
    return {"indicators": indicators, "headlines": headlines}


# ── DREAM STOCK SCANNER ───────────────────────────────────────────────────────

ARK_ETFS = ["ARKK", "ARKG", "ARKW", "ARKQ", "ARKF"]

def fetch_ark_holdings():
    """Pull current ARK ETF holdings via yfinance."""
    tickers = set()
    for etf in ARK_ETFS:
        try:
            fund = yf.Ticker(etf)
            holdings = fund.funds_data.top_holdings if hasattr(fund, 'funds_data') and fund.funds_data else None
            if holdings is not None and not holdings.empty:
                for sym in holdings.index[:15]:
                    tickers.add(str(sym).upper())
                log.info(f"ARK {etf}: {len(holdings)} holdings fetched")
            else:
                # Fallback: get from info
                info = fund.info
                log.info(f"ARK {etf}: fallback info only | {info.get('symbol','?')}")
        except Exception as e:
            log.warning(f"ARK {etf} FAIL: {e}")
    log.info(f"ARK holdings total unique tickers: {len(tickers)}")
    return list(tickers)


def fetch_yf_growth_screener():
    """Screen for high-growth stocks via all yfinance screeners."""
    tickers = []
    queries = [
        "day_gainers",
        "most_actives",
        "growth_technology_stocks",
        "undervalued_growth_stocks",
        "aggressive_small_caps",
        "small_cap_gainers",
        "undervalued_large_caps",
    ]
    for q in queries:
        try:
            result = yf.screen(q)
            quotes = result.get("quotes", [])
            added = 0
            for quote in quotes[:25]:
                sym = quote.get("symbol", "")
                if sym:
                    tickers.append(sym)
                    added += 1
            log.info(f"Screener {q}: {added} tickers")
        except Exception as e:
            log.warning(f"Screener {q} FAIL: {e}")
    return list(set(tickers))


def fetch_sp500_tickers():
    """Hardcoded S&P 500 components — updated May 2025. No API needed."""
    sp500 = [
        "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB","AKAM",
        "ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN","AMCR","AEE",
        "AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH","ADI","ANSS","AON","APA",
        "APO","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG","AIZ","T","ATO","ADSK",
        "ADP","AZO","AVB","AVY","AXON","BKR","BALL","BAC","BAX","BDX","BRK.B","BBY",
        "TECH","BIO","BIIB","BLK","BX","BA","BKNG","BWA","BSX","BMY","AVGO","BR","BRO",
        "BF.B","BLDR","CHRW","CDNS","CZR","CPT","CPB","COF","CAH","KMX","CCL","CARR",
        "CTLT","CAT","CBOE","CBRE","CDW","CE","COR","CNC","CNP","CF","CHTR","CVX","CMG",
        "CB","CHD","CI","CINF","CTAS","CSCO","C","CFG","CLX","CME","CMS","KO","CTSH",
        "CL","CMCSA","CAG","COP","ED","STZ","CEG","COO","CPRT","GLW","CPAY","CTVA",
        "CSGP","COST","CTRA","CRWD","CCI","CSX","CMI","CVS","DHR","DRI","DVA","DAY",
        "DE","DAL","XRAY","DVN","DXCM","FANG","DLR","DFS","DG","DLTR","D","DPZ","DOV",
        "DOW","DHI","DTE","DUK","DD","EMN","ETN","EBAY","ECL","EIX","EW","EA","ELV",
        "LLY","EMR","ENPH","ETR","EOG","EPAM","EQT","EFX","EQIX","EQR","ESS","EL",
        "ETSY","EG","EVRST","ES","EXC","EXPE","EXPD","EXR","XOM","FFIV","FDS","FICO",
        "FAST","FRT","FDX","FIS","FITB","FSLR","FE","FI","FMC","F","FTNT","FTV","FOXA",
        "FOX","BEN","FCX","GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS","GM",
        "GPC","GILD","GS","HAL","HIG","HAS","HCA","DOC","HSIC","HSY","HES","HPE","HLT",
        "HOLX","HD","HON","HRL","HST","HWM","HPQ","HUBB","HUM","HBAN","HII","IBM","IEX",
        "IDXX","ITW","INCY","IR","PODD","INTC","ICE","IFF","IP","IPG","INTU","ISRG",
        "IVZ","INVH","IQV","IRM","JBAL","JKHY","J","JBL","JNPR","JPM","JNPR","K","KVUE",
        "KDP","KEY","KEYS","KMB","KIM","KMI","KLAC","KHC","KR","LHX","LH","LRCX","LW",
        "LVS","LDOS","LEN","LIN","LYV","LKQ","LMT","L","LOW","LULU","LYB","MTB","MRO",
        "MPC","MKTX","MAR","MMC","MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT","MRK",
        "META","MET","MTD","MGM","MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP","MDLZ",
        "MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NFLX","NEM","NWSA",
        "NWS","NEE","NKE","NI","NDSN","NSC","NTRS","NOC","NCLH","NRG","NUE","NVDA","NVR",
        "NXPI","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR","PKG","PLTR",
        "PH","PAYX","PAYC","PYPL","PNR","PEP","PFE","PCG","PM","PSX","PNW","PNC","POOL",
        "PPG","PPL","PFG","PG","PGR","PLD","PRU","PEG","PTC","PSA","PHM","QRVO","PWR",
        "QCOM","DGX","RL","RJF","RTX","O","REG","REGN","RF","RSG","RMD","RVTY","ROK",
        "ROL","ROP","ROST","RCL","SPGI","CRM","SBAC","SLB","STX","SRE","NOW","SHW",
        "SPG","SWKS","SJM","SW","SNA","SOLV","SO","LUV","SWK","SBUX","STT","STLD","STE",
        "SYK","SMCI","SYF","SNPS","SYY","TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL",
        "TDY","TFX","TER","TSLA","TXN","TXT","TMO","TJX","TSCO","TT","TDG","TRV","TRMB",
        "TFC","TYL","TSN","USB","UBER","UDR","ULTA","UNP","UAL","UPS","URI","UNH","UHS",
        "VLO","VTR","VLTO","VRSN","VRSK","VZ","VRTX","VLTO","VFC","VTRS","VICI","V",
        "VST","VMC","WRB","GWW","WAB","WBA","WMT","DIS","WBD","WM","WAT","WEC","WFC",
        "WELL","WST","WDC","WHR","WMB","WTW","WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS"
    ]
    log.info(f"S&P 500: {len(sp500)} tickers (hardcoded)")
    return sp500


def fetch_tsx60_tickers():
    """Fetch TSX 60 components — hardcoded as they rarely change."""
    tsx60 = [
        "AEM.TO","AGI.TO","ATD.TO","BAM.TO","BCE.TO","BHC.TO","BMO.TO","BNS.TO",
        "CAE.TO","CCL-B.TO","CCO.TO","CHP-UN.TO","CM.TO","CNQ.TO","CNR.TO","CP.TO",
        "CSU.TO","CVE.TO","DOL.TO","DSG.TO","EMA.TO","ENB.TO","EQB.TO","FM.TO",
        "FNV.TO","FTS.TO","GFL.TO","GIB-A.TO","GWO.TO","H.TO","IFC.TO","IMO.TO",
        "K.TO","KXS.TO","L.TO","LSPD.TO","LUN.TO","MFC.TO","MG.TO","MRU.TO",
        "NA.TO","NTR.TO","NVEI.TO","OVV.TO","POU.TO","POW.TO","PPL.TO","QBR-B.TO",
        "RCI-B.TO","RY.TO","SAP.TO","SHOP.TO","SLF.TO","SNC.TO","SU.TO","T.TO",
        "TD.TO","TECK-B.TO","TRP.TO","WCN.TO"
    ]
    log.info(f"TSX 60: {len(tsx60)} tickers")
    return tsx60


def score_dream_stock(ticker, info, hist, financials):
    """Score a stock 0-100 on dream criteria."""
    score = 0
    breakdown = {}
    flags_good = []
    flags_warn = []

    try:
        # 1. Revenue Growth (20pts)
        rev_growth = info.get("revenueGrowth")
        if rev_growth is not None:
            rev_pct = round(rev_growth * 100, 1)
            if rev_pct >= 40:
                score += 20
                flags_good.append(f"Revenue +{rev_pct}% YoY")
            elif rev_pct >= 20:
                score += 10
                flags_good.append(f"Revenue +{rev_pct}% YoY")
            else:
                flags_warn.append(f"Revenue growth weak: +{rev_pct}%")
            breakdown["revenueGrowth"] = rev_pct
        else:
            flags_warn.append("Revenue growth N/A")
            breakdown["revenueGrowth"] = None

        # 2. Gross Margin (15pts)
        gross_margin = info.get("grossMargins")
        if gross_margin is not None:
            gm_pct = round(gross_margin * 100, 1)
            if gm_pct >= 60:
                score += 15
                flags_good.append(f"Gross margin {gm_pct}%")
            elif gm_pct >= 40:
                score += 8
                flags_good.append(f"Gross margin {gm_pct}%")
            else:
                flags_warn.append(f"Low margin: {gm_pct}%")
            breakdown["grossMargin"] = gm_pct
        else:
            breakdown["grossMargin"] = None

        # 3. Momentum — RSI position (15pts)
        rsi = None
        bb_pct = None
        if hist is not None and not hist.empty and len(hist) >= 15:
            delta = hist['Close'].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss
            rsi_series = 100 - (100 / (1 + rs))
            _rsi_val = rsi_series.iloc[-1]
            rsi = round(float(_rsi_val), 1) if not rsi_series.empty and not math.isnan(float(_rsi_val)) else None
        if rsi is not None:
            if 45 <= rsi <= 65:
                score += 15
                flags_good.append(f"RSI {rsi} — momentum, not overextended")
            elif 35 <= rsi < 45:
                score += 10
                flags_good.append(f"RSI {rsi} — building momentum")
            elif rsi > 70:
                score += 5
                flags_warn.append(f"RSI {rsi} — overbought, risky entry")
            else:
                flags_warn.append(f"RSI {rsi} — weak momentum")
            breakdown["rsi"] = rsi
        else:
            breakdown["rsi"] = None

        # 4. Price trend — above MA50 + near 52w high (15pts)
        trend_score = 0
        week52_high = info.get("fiftyTwoWeekHigh")
        week52_low = info.get("fiftyTwoWeekLow")
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        ma50 = None
        if hist is not None and len(hist) >= 35:
            _ma50_val = hist['Close'].rolling(50).mean().iloc[-1]
            ma50 = round(float(_ma50_val), 2) if not math.isnan(float(_ma50_val)) else None
        if current_price and ma50 and current_price > ma50:
            trend_score += 8
            flags_good.append("Above MA50")
        if current_price and week52_high:
            pct_from_high = (current_price / week52_high) * 100
            if pct_from_high >= 85:
                trend_score += 7
                flags_good.append(f"{round(pct_from_high,0):.0f}% of 52w high — strong trend")
            elif pct_from_high >= 70:
                trend_score += 3
        score += trend_score
        breakdown["ma50"] = ma50
        breakdown["week52High"] = week52_high
        breakdown["priceVs52wHigh"] = round((current_price / week52_high * 100), 1) if current_price and week52_high else None

        # 5. Balance sheet — net cash + FCF (15pts)
        total_cash = info.get("totalCash")
        total_debt = info.get("totalDebt")
        fcf = info.get("freeCashflow")
        bs_score = 0
        if total_cash and total_debt:
            net_cash = total_cash - total_debt
            if net_cash > 0:
                bs_score += 8
                flags_good.append("Net cash positive")
            else:
                flags_warn.append("Net debt position")
            breakdown["netCash"] = net_cash
        if fcf and fcf > 0:
            bs_score += 7
            flags_good.append("FCF positive")
        elif fcf and fcf < 0:
            flags_warn.append("FCF negative — burning cash")
        score += bs_score
        breakdown["fcf"] = fcf

        # 6. Institutional ownership (10pts)
        inst_pct = info.get("institutionPercentHeld")
        if inst_pct is not None:
            inst_val = round(inst_pct * 100, 1)
            if inst_val >= 50:
                score += 10
                flags_good.append(f"Institutional {inst_val}%")
            elif inst_val >= 25:
                score += 5
                flags_good.append(f"Institutional {inst_val}%")
            else:
                flags_warn.append(f"Low institutional: {inst_val}%")
            breakdown["institutionalPct"] = inst_val
        else:
            breakdown["institutionalPct"] = None

        # 7. Market cap — emerging leader (10pts)
        mcap = info.get("marketCap")
        if mcap:
            if 500_000_000 <= mcap <= 10_000_000_000:
                score += 10
                flags_good.append("Emerging leader size ($500M-$10B)")
            elif mcap < 500_000_000:
                score += 5
                flags_warn.append("Micro-cap — higher risk")
            else:
                score += 6
        breakdown["marketCap"] = mcap

        score = min(100, score)

    except Exception as e:
        log.warning(f"Score calc FAIL: {ticker} | {e}")

    return score, breakdown, flags_good, flags_warn


def fetch_dream_candidates(watchlist_tickers, gainer_tickers):
    """Fetch and score all dream stock candidates."""
    log.info("=== Dream Scan: fetching candidates ===")

    # Gather all unique tickers from all sources
    ark_tickers      = fetch_ark_holdings()
    screener_tickers = fetch_yf_growth_screener()
    sp500_tickers    = fetch_sp500_tickers()
    tsx60_tickers    = fetch_tsx60_tickers()

    all_tickers = {}
    for t in watchlist_tickers:
        all_tickers[t] = "Watchlist"
    for t in gainer_tickers:
        if t not in all_tickers:
            all_tickers[t] = "Daily Gainer"
    for t in ark_tickers:
        if t not in all_tickers:
            all_tickers[t] = "ARK ETF"
    for t in screener_tickers:
        if t not in all_tickers:
            all_tickers[t] = "Screener"
    for t in sp500_tickers:
        if t not in all_tickers:
            all_tickers[t] = "S&P 500"
    for t in tsx60_tickers:
        if t not in all_tickers:
            all_tickers[t] = "TSX 60"

    log.info(
        f"Dream scan total candidates: {len(all_tickers)} | "
        f"watchlist:{len(watchlist_tickers)} gainers:{len(gainer_tickers)} "
        f"ark:{len(ark_tickers)} screener:{len(screener_tickers)} "
        f"sp500:{len(sp500_tickers)} tsx60:{len(tsx60_tickers)}"
    )

    candidates = []
    for ticker, source in all_tickers.items():
        log.info(f"--- Dream scoring: {ticker} [{source}] ---")
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if not info.get("regularMarketPrice") and not info.get("currentPrice"):
                log.warning(f"Dream skip (no price): {ticker}")
                continue
            hist = stock.history(period="60d")

            # Get top 3 institutional holders
            institutions = []
            try:
                holders = stock.institutional_holders
                if holders is not None and not holders.empty:
                    for _, row in holders.head(3).iterrows():
                        name = str(row.get("Holder", row.get("Name", "Unknown")))
                        pct = row.get("% Out", row.get("pctHeld", None))
                        pct_str = f"{round(float(pct)*100,1)}%" if pct is not None else ""
                        institutions.append({"name": name, "pct": pct_str})
            except Exception as e:
                log.warning(f"Institutions FAIL: {ticker} | {e}")

            score, breakdown, flags_good, flags_warn = score_dream_stock(ticker, info, hist, None)

            candidates.append({
                "ticker": ticker,
                "source": source,
                "score": score,
                "name": info.get("shortName", ticker),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "marketCap": info.get("marketCap"),
                "breakdown": breakdown,
                "flagsGood": flags_good,
                "flagsWarn": flags_warn,
                "institutions": institutions,
                "description": (info.get("longBusinessSummary") or "")[:300],
            })
            log.info(f"Dream scored: {ticker} | score:{score} source:{source}")
        except Exception as e:
            log.error(f"Dream candidate FAIL: {ticker} | {e}")
            continue

    candidates.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"=== Dream Scan complete: {len(candidates)} scored ===")
    return {"candidates": candidates}
