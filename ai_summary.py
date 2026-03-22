import ollama
import json
import logging

log = logging.getLogger(__name__)

MODEL = "gemma2:9b"

SYSTEM_PROMPT = """You are an expert financial analyst and portfolio manager specializing in mining, commodities, and equity markets.
You analyze quantitative financial data and generate concise, professional investment analysis.
Always respond with valid JSON only. No preamble, no markdown, no explanation outside the JSON."""


from datetime import date

def build_stock_prompt(stock):
    ticker = stock.get("ticker")
    annual = stock.get("annualIncome", [])
    quarterly = stock.get("quarterlyIncome", [])
    balance = stock.get("annualBalance", [])
    cashflow = stock.get("annualCashflow", [])
    changes = stock.get("annualChanges", {})
    q_changes = stock.get("quarterlyChanges", {})
    cal = stock.get("calendar", {})
    ev = stock.get("events", {})
    today = date.today().strftime("%Y-%m-%d")

    return f"""Today is {today}. Analyze this stock and return a JSON object with EXACTLY these fields:

{{
  "highlight": "2-3 sentence investment thesis",
  "marketPosition": "1 sentence competitive position",
  "majorGrowthProjects": ["catalyst 1", "catalyst 2"],
  "shareholderReturns": "1 sentence on dividends and buybacks",
  "balanceSheetSummary": "1 sentence on financial health",
  "riskFactors": ["risk 1", "risk 2"],
  "analystSentiment": "bullish OR neutral OR bearish",
  "shortWarning": {{
    "shouldShort": true or false,
    "reason": "explanation or null",
    "confidence": "high OR medium OR low"
  }},
  "eventImpacts": [
    {{
      "event": "event name",
      "date": "YYYY-MM-DD",
      "startWatchingDate": "YYYY-MM-DD (exact date to start paying attention, calculated from today {today})",
      "expectedImpact": "Detailed price impact: what direction, estimated % move range, why",
      "epsEstimate": "exact EPS estimate if available, e.g. $0.78 avg, range $0.65-$0.86",
      "revenueEstimate": "exact revenue estimate if available",
      "whereToMonitor": ["source 1 e.g. Yahoo Finance earnings page", "source 2 e.g. SEC EDGAR", "source 3 e.g. company IR page"],
      "whatToWatchFor": ["specific metric 1 to compare vs estimate", "specific metric 2"],
      "actionPlan": [
        {{"date": "YYYY-MM-DD", "action": "what to do on this specific date"}},
        {{"date": "YYYY-MM-DD", "action": "what to do on this specific date"}},
        {{"date": "YYYY-MM-DD", "action": "what to do on this specific date"}}
      ],
      "strategy": "overall strategy summary"
    }}
  ]
}}

FINANCIAL DATA:
Ticker: {ticker}
Sector: {stock.get("sector")} | Industry: {stock.get("industry")}
Price: ${stock.get("price")} | Market Cap: ${stock.get("marketCap")}
Annual Profit Margin: {stock.get("annualProfitMargin")} | Quarterly Margin: {stock.get("quarterlyProfitMargin")}
Net Cash: ${stock.get("netCash")} | Latest FCF: ${stock.get("latestFCF")} | CapEx: ${stock.get("latestCapex")}

Latest Annual Income:
{json.dumps(annual[0] if annual else {}, indent=2)}

Latest Quarterly Income:
{json.dumps(quarterly[0] if quarterly else {}, indent=2)}

Balance Sheet:
{json.dumps(balance[0] if balance else {}, indent=2)}

Annual Cash Flow:
{json.dumps(cashflow[0] if cashflow else {}, indent=2)}

Annual Changes YoY:
{json.dumps(changes, indent=2)}

Quarterly Changes QoQ/YoY:
{json.dumps(q_changes, indent=2)}

Upcoming Events:
Earnings Date: {cal.get("earningsDateStart")}
EPS Estimate High/Low/Avg: {cal.get("earningsEPSHigh")} / {cal.get("earningsEPSLow")} / {cal.get("earningsEPSAvg")}
Revenue Estimate High/Low/Avg: {cal.get("revenueEstimateHigh")} / {cal.get("revenueEstimateLow")} / {cal.get("revenueEstimateAvg")}
Ex-Dividend Date: {cal.get("exDividendDate")}
Dividend Pay Date: {cal.get("dividendPayDate")}
Earnings Call: {ev.get("earningsCallStart")}
Dividend Yield: {ev.get("dividendYield")}
Earnings Growth YoY: {ev.get("earningsGrowthYoY")}
Earnings Quarterly Growth: {ev.get("earningsQuarterlyGrowth")}
Last Dividend: ${ev.get("lastDividendValue")} on {ev.get("lastDividendDate")}
"""


def build_recommendations_prompt(watchlist):
    context = []
    for s in watchlist:
        context.append({
            "ticker": s.get("ticker"),
            "sector": s.get("sector"),
            "industry": s.get("industry"),
            "annualProfitMargin": s.get("annualProfitMargin"),
            "netCash": s.get("netCash"),
            "latestFCF": s.get("latestFCF"),
            "marketCap": s.get("marketCap"),
            "analystSentiment": s.get("aiSummary", {}).get("analystSentiment"),
        })

    return f"""Based on the user's current watchlist below, recommend 5-10 stocks they should consider purchasing from the broader market.
Consider diversification, sector exposure, market conditions, and complement their existing holdings.
Focus on stocks with strong fundamentals, reasonable valuations, and growth catalysts.

User's current watchlist context:
{json.dumps(context, indent=2)}

Return a JSON object with EXACTLY this structure:
{{
  "recommendations": [
    {{
      "ticker": "TICKER",
      "companyName": "Full Company Name",
      "reason": "2-3 sentence explanation of why to buy",
      "sector": "sector name",
      "catalysts": ["catalyst 1", "catalyst 2"],
      "riskLevel": "low OR medium OR high",
      "timeHorizon": "short-term OR medium-term OR long-term"
    }}
  ],
  "marketContext": "1-2 sentence summary of current market conditions influencing recommendations",
  "generatedAt": "today's date"
}}"""


def generate_summary(stock):
    ticker = stock.get("ticker")
    try:
        log.info(f"AI generating summary: {ticker}")
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_stock_prompt(stock)}
            ]
        )
        raw = response["message"]["content"].strip()
        # Strip markdown code blocks
        raw = raw.replace("```json", "").replace("```", "").strip()
        # Find first { and last } to extract just the JSON
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        summary = json.loads(raw)
        log.info(f"AI OK: {ticker} | sentiment:{summary.get('analystSentiment')} | short:{summary.get('shortWarning', {}).get('shouldShort')}")
        return summary
    except json.JSONDecodeError as e:
        log.error(f"AI JSON parse FAIL: {ticker} | {e} | raw:{raw[:200]}")
        return default_summary(ticker)
    except Exception as e:
        log.error(f"AI FAIL: {ticker} | {e}")
        return default_summary(ticker)


def generate_recommendations(watchlist):
    try:
        log.info("AI generating buy recommendations...")
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_recommendations_prompt(watchlist)}
            ]
        )
        raw = response["message"]["content"].strip()
        # Strip markdown code blocks
        raw = raw.replace("```json", "").replace("```", "").strip()
        # Find first { and last } to extract just the JSON
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        result = json.loads(raw)
        log.info(f"AI recommendations OK: {len(result.get('recommendations', []))} stocks")
        return result
    except Exception as e:
        log.error(f"AI recommendations FAIL: {e}")
        return {"recommendations": [], "marketContext": "Unavailable", "generatedAt": ""}

def generate_followup(stock, event_name):
    ticker = stock.get("ticker")
    today = date.today().strftime("%Y-%m-%d")
    ai = stock.get("aiSummary", {})
    event = next((e for e in ai.get("eventImpacts", []) if e.get("event") == event_name), {})

    prompt = f"""Today is {today}. The user just clicked to get a follow-up plan for {ticker} regarding: {event_name}.

Event details: {json.dumps(event, indent=2)}
Stock context: Ticker={ticker}, Price=${stock.get('price')}, Sentiment={ai.get('analystSentiment')}
Latest quarterly changes: {json.dumps(stock.get('quarterlyChanges', {}), indent=2)}

Generate a detailed step-by-step follow-up plan. Return JSON with EXACTLY:
{{
  "summary": "1-2 sentence current situation summary",
  "steps": [
    {{
      "date": "YYYY-MM-DD",
      "title": "short action title",
      "instructions": "detailed instructions what to do, what to look for, what numbers to check",
      "fetchRequired": true or false,
      "sources": ["where to check"]
    }}
  ],
  "redFlags": ["warning sign 1 to watch for", "warning sign 2"],
  "greenFlags": ["positive signal 1", "positive signal 2"],
  "decisionPoint": "date and condition that triggers buy/sell/hold decision"
}}"""

    try:
        log.info(f"AI followup: {ticker} | {event_name}")
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        raw = response["message"]["content"].strip()
        # Strip markdown code blocks
        raw = raw.replace("```json", "").replace("```", "").strip()
        # Find first { and last } to extract just the JSON
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        result = json.loads(raw)
        log.info(f"AI followup OK: {ticker}")
        return result
    except Exception as e:
        log.error(f"AI followup FAIL: {ticker} | {e}")
        return {"error": "Follow-up generation failed"}

def default_summary(ticker):
    return {
        "highlight": f"Analysis unavailable for {ticker}",
        "marketPosition": "N/A",
        "majorGrowthProjects": [],
        "shareholderReturns": "N/A",
        "balanceSheetSummary": "N/A",
        "riskFactors": [],
        "analystSentiment": "neutral",
        "shortWarning": {"shouldShort": False, "reason": None, "confidence": "low"},
        "eventImpacts": []
    }

def generate_news_impact(ticker, news_items, stock, price_context={}):
    try:
        log.info(f"AI news impact: {ticker} | {len(news_items)} articles")
        price = stock.get("price")
        sector = stock.get("sector")
        sentiment = stock.get("aiSummary", {}).get("analystSentiment", "neutral")

        news_text = "\n".join([
            f"- [{n['pubDate'][:10]}] {n['title']} ({n['provider']}): {n['summary'][:200]}"
            for n in news_items
        ])

        prompt = f"""Today is {date.today()}. Analyze the following recent news for {ticker} and return JSON with EXACTLY:
{{
  "overallSentiment": "bullish OR bearish OR neutral",
  "sentimentScore": number from -10 (very bearish) to +10 (very bullish),
  "summary": "2-3 sentence overall news impact summary",
  "priceImpact": "assessment of likely short-term price impact with estimated % range",
  "keyThemes": ["theme 1", "theme 2", "theme 3"],
  "tradingImplication": "what should investor do based on this news: buy/hold/sell/wait with reasoning",
  "watchFor": "what upcoming catalyst or confirmation to watch for",
  "newsItems": [
    {{
      "title": "article title",
      "impact": "positive OR negative OR neutral",
      "significance": "high OR medium OR low",
      "oneLineSummary": "one sentence impact on stock"
    }}
  ]
}}

Stock context: {ticker} | Price: ${price} | Sector: {sector} | Prior sentiment: {sentiment}

Recent news (last 7 days):
{news_text}
"""
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )
        raw = response["message"]["content"].strip()
        # Strip markdown code blocks
        raw = raw.replace("```json", "").replace("```", "").strip()
        # Find first { and last } to extract just the JSON
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        log.info(f"AI news raw response: {raw[:500]}")
        result = json.loads(raw)
        log.info(f"AI news impact OK: {ticker} | sentiment:{result.get('overallSentiment')} score:{result.get('sentimentScore')}")
        return result
    except Exception as e:
        log.error(f"AI news impact FAIL: {ticker} | {e}")
        return {
            "overallSentiment": "neutral",
            "sentimentScore": 0,
            "summary": "News analysis unavailable",
            "priceImpact": "Unknown",
            "keyThemes": [],
            "tradingImplication": "N/A",
            "watchFor": "N/A",
            "newsItems": []
        }