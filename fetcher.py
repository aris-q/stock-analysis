import requests
import yfinance as yf
import logging

log = logging.getLogger(__name__)


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

        return {
            "price": info.get("currentPrice"),
            "volume": info.get("volume"),
            "marketCap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "calendar": calendar_data,
            "events": events_data,
            "dividends": recent_dividends,
            "annualIncome": extract_periods(annual_income, INCOME_FIELDS, 3),
            "quarterlyIncome": extract_periods(quarterly_income, INCOME_FIELDS, 4),
            "annualBalance": extract_periods(annual_balance, BALANCE_FIELDS, 3),
            "quarterlyBalance": extract_periods(quarterly_balance, BALANCE_FIELDS, 4),
            "annualCashflow": extract_periods(annual_cashflow, CASHFLOW_FIELDS, 3),
            "quarterlyCashflow": extract_periods(quarterly_cashflow, CASHFLOW_FIELDS, 4),
        }
    except Exception as e:
        log.error(f"yfinance FAIL: {ticker} | {e}")
        return None


def fetch_daily_gainers():
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
        log.info(f"Daily gainers fetched: {len(gainers)}")
        return gainers
    except Exception as e:
        log.error(f"Daily gainers FAIL: {e}")
        return []