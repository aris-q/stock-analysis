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
        rsi = round(rsi_series.iloc[-1], 1) if not rsi_series.empty else None

        # 20-day and 50-day moving averages
        ma20 = round(hist['Close'].rolling(20).mean().iloc[-1], 2) if len(hist) >= 20 else None
        ma50 = round(hist['Close'].rolling(50).mean().iloc[-1], 2) if len(hist) >= 35 else None

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
            rsi = round(float(rsi_series.iloc[-1]), 1) if not rsi_series.empty else None
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
