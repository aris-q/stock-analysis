import ollama
import json
import logging

log = logging.getLogger(__name__)

MODEL = "gemma2:9b"

SYSTEM_PROMPT = """You are an expert financial analyst specializing in mining and natural resource companies.
You analyze quantitative financial data and generate concise, professional investment summaries.
Always respond with valid JSON only. No preamble, no markdown, no explanation outside the JSON."""


def build_prompt(stock):
    ticker = stock.get("ticker")
    annual = stock.get("annualIncome", [])
    quarterly = stock.get("quarterlyIncome", [])
    balance = stock.get("annualBalance", [])
    cashflow = stock.get("annualCashflow", [])
    changes = stock.get("annualChanges", {})
    q_changes = stock.get("quarterlyChanges", {})
    calendar = stock.get("calendar", {})
    events = stock.get("events", {})

    return f"""Analyze this financial data for {ticker} and return a JSON object with exactly these fields:

{{
  "highlight": "2-3 sentence investment thesis focusing on key strengths and risks",
  "marketPosition": "1 sentence describing competitive position among peers",
  "majorGrowthProjects": ["project or catalyst 1", "project or catalyst 2"],
  "shareholderReturns": "1 sentence on dividends and buybacks",
  "balanceSheetSummary": "1 sentence on financial health",
  "riskFactors": ["risk 1", "risk 2"],
  "analystSentiment": "bullish/neutral/bearish based on data trends"
}}

FINANCIAL DATA:
Ticker: {ticker}
Sector: {stock.get("sector")} | Industry: {stock.get("industry")}
Price: ${stock.get("price")} | Market Cap: ${stock.get("marketCap")}

Latest Annual Income:
{json.dumps(annual[0] if annual else {}, indent=2)}

Latest Quarterly Income:
{json.dumps(quarterly[0] if quarterly else {}, indent=2)}

Balance Sheet:
{json.dumps(balance[0] if balance else {}, indent=2)}

Cash Flow:
{json.dumps(cashflow[0] if cashflow else {}, indent=2)}

Annual Changes (YoY):
{json.dumps(changes, indent=2)}

Quarterly Changes (QoQ/YoY):
{json.dumps(q_changes, indent=2)}

Upcoming Events:
Earnings Date: {calendar.get("earningsDateStart")}
EPS Estimate: {calendar.get("earningsEPSAvg")}
Revenue Estimate: {calendar.get("revenueEstimateAvg")}
Ex-Dividend: {calendar.get("exDividendDate")}
Dividend Yield: {events.get("dividendYield")}
Earnings Growth YoY: {events.get("earningsGrowthYoY")}

Net Cash: ${stock.get("netCash")}
Annual Profit Margin: {stock.get("annualProfitMargin")}
Quarterly Profit Margin: {stock.get("quarterlyProfitMargin")}
Latest FCF: ${stock.get("latestFCF")}
Latest CapEx: ${stock.get("latestCapex")}
"""


def generate_summary(stock):
    ticker = stock.get("ticker")
    try:
        log.info(f"AI generating summary for: {ticker}")
        prompt = build_prompt(stock)
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        raw = response["message"]["content"].strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        summary = json.loads(raw)
        log.info(f"AI OK: {ticker} | sentiment:{summary.get('analystSentiment')}")
        return summary
    except json.JSONDecodeError as e:
        log.error(f"AI JSON parse FAIL: {ticker} | {e} | raw: {raw[:200]}")
        return default_summary(ticker)
    except Exception as e:
        log.error(f"AI FAIL: {ticker} | {e}")
        return default_summary(ticker)


def default_summary(ticker):
    return {
        "highlight": f"Analysis unavailable for {ticker}",
        "marketPosition": "N/A",
        "majorGrowthProjects": [],
        "shareholderReturns": "N/A",
        "balanceSheetSummary": "N/A",
        "riskFactors": [],
        "analystSentiment": "neutral"
    }


def enrich_with_ai(watchlist):
    log.info("=== Phase 4: AI Summaries Started ===")
    for stock in watchlist:
        summary = generate_summary(stock)
        stock["aiSummary"] = summary
        log.info(f"AI enriched: {stock['ticker']}")
    log.info("=== Phase 4: AI Summaries Done ===")
    return watchlist