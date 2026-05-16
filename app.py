from flask import Flask, render_template, request, redirect, jsonify
import json, os, logging, threading
from config import WATCHLIST, OUTPUT_PATH, NEWS_PATH, WATCHLIST_PATH
try:
    from config import FRED_API_KEY, NEWSAPI_KEY, MACRO_PATH
except ImportError:
    FRED_API_KEY = None
    NEWSAPI_KEY  = None
    MACRO_PATH   = "output/macro.json"
DREAM_PATH = "output/dream.json"
from fetcher import fetch_yfinance, fetch_daily_gainers, fetch_news, fetch_price_context, fetch_price_only, fetch_macro_data, fetch_dream_candidates
from compute import process_watchlist
from ai_summary import generate_summary, generate_recommendations, generate_followup, generate_news_impact
from refresh_manager import check_what_needs_refresh, needs_news_refresh, now
from datetime import datetime
from zoneinfo import ZoneInfo

os.makedirs("logs", exist_ok=True)
os.makedirs("output", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler()
    ]
)

log = logging.getLogger(__name__)
app = Flask(__name__)


def _sanitize_str(s):
    if not isinstance(s, str):
        return s
    return s.replace('\x00', '').replace('\r', ' ')

def _sanitize_news(items):
    return [{k: _sanitize_str(v) for k, v in item.items()} for item in items]


# watchlist = list(WATCHLIST)

def load_watchlist():
    try:
        with open(WATCHLIST_PATH, "r") as f:
            return json.load(f)
    except Exception:
        log.info("No watchlist.json found, using config default")
        return list(WATCHLIST)

def save_watchlist():
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(watchlist, f)
    log.info(f"Watchlist saved: {watchlist}")

watchlist = load_watchlist()

fetch_status = {"running": False, "message": "Idle", "operation": None}
op_timestamps = {"prices": None, "smart": None, "new": None, "all": None}
last_fetched_tickers = set()



TZ = ZoneInfo("America/Toronto")

def ts():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    log.debug(f"[save_json] cwd:{os.getcwd()} path:{path} tmp:{tmp}")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, allow_nan=False, default=lambda v: None)
    os.replace(tmp, path)

def sync_watchlist_to_analysis(existing_watchlist, watchlist):
    """Ensure all tickers in watchlist exist in analysis, never remove existing cards."""
    existing_map = {s["ticker"]: s for s in existing_watchlist}
    for ticker in watchlist:
        if ticker not in existing_map:
            log.info(f"Adding missing ticker to analysis: {ticker}")
            existing_map[ticker] = {"ticker": ticker, "fetchedAt": None}
    return existing_map


def run_price_refresh(triggered_by="startup"):
    global fetch_status, op_timestamps
    fetch_status = {"running": True, "message": f"⚡ Updating prices for all tickers...", "operation": "prices"}
    log.info(f"=== Price Refresh Started [{triggered_by}]: {watchlist} ===")

    existing = load_json(OUTPUT_PATH, {"watchlist": [], "dailyGainers": []})
    existing_map = {s["ticker"]: s for s in existing.get("watchlist", [])}

    for ticker in watchlist:
        log.info(f"--- Price refresh: {ticker} ---")
        try:
            price_data = fetch_price_only(ticker)
            if not price_data:
                log.error(f"Price refresh no data: {ticker}")
                continue
            stock = existing_map.get(ticker, {"ticker": ticker})
            stock.update({
                "ticker": ticker,
                "price": price_data.get("price"),
                "previousClose": price_data.get("previousClose"),
                "volume": price_data.get("volume"),
                "marketCap": price_data.get("marketCap"),
                "rsi14": price_data.get("rsi14"),
                "bbPercent": price_data.get("bbPercent"),
                "priceFetchedAt": ts(),
            })
            existing_map[ticker] = stock
            log.info(f"Price refresh OK: {ticker} | price:{price_data.get('price')} prevClose:{price_data.get('previousClose')} rsi:{price_data.get('rsi14')} bb:{price_data.get('bbPercent')}")
        except Exception as e:
            log.error(f"Price refresh FAIL: {ticker} | {e}")

    now_ts = ts()
    op_timestamps["prices"] = now_ts

    results = [existing_map[t] for t in watchlist if t in existing_map]
    out = load_json(OUTPUT_PATH, {"watchlist": [], "dailyGainers": []})
    out["watchlist"] = results
    out["lastPriceRefresh"] = now_ts
    save_json(OUTPUT_PATH, out)

    fetch_status = {"running": False, "message": f"Prices updated: {now_ts}", "operation": None}
    log.info(f"=== Price Refresh Complete [{triggered_by}] ===")


def run_ai_summary(ticker):
    global fetch_status
    fetch_status = {"running": True, "message": f"⚡ Generating AI summary: {ticker}...", "operation": "ai"}
    log.info(f"=== AI Summary Started: {ticker} ===")
    try:
        existing = load_json(OUTPUT_PATH, {"watchlist": []})
        existing_map = {s["ticker"]: s for s in existing.get("watchlist", [])}
        stock = existing_map.get(ticker)
        if not stock:
            log.error(f"AI summary FAIL: {ticker} not found in data")
            fetch_status = {"running": False, "message": f"AI summary FAIL: {ticker} not found.", "operation": None}
            return
        now_ts = ts()
        stock["aiSummary"] = generate_summary(stock)
        stock["aiSummaryUpdatedAt"] = now_ts
        existing_map[ticker] = stock
        out = load_json(OUTPUT_PATH, {})
        out["watchlist"] = [existing_map.get(t, s) for t, s in [(s["ticker"], s) for s in existing.get("watchlist", [])]]
        save_json(OUTPUT_PATH, out)
        fetch_status = {"running": False, "message": f"AI summary done: {ticker} at {now_ts}", "operation": None}
        log.info(f"=== AI Summary Complete: {ticker} ===")
    except Exception as e:
        log.error(f"AI summary FAIL: {ticker} | {e}")
        fetch_status = {"running": False, "message": f"AI summary FAIL: {ticker}", "operation": None}


def run_fetch(tickers_to_fetch, mode="all"):
    global fetch_status, last_fetched_tickers, op_timestamps
    fetch_status = {"running": True, "message": f"[{mode.upper()}] Fetching {len(tickers_to_fetch)} ticker(s)...", "operation": mode}
    log.info(f"=== Fetch Started [{mode}]: {tickers_to_fetch} ===")

    existing = load_json(OUTPUT_PATH, {"watchlist": [], "dailyGainers": []})
    existing_map = reconcile_with_watchlist(
    {s["ticker"]: s for s in existing.get("watchlist", [])}
)

    for ticker in tickers_to_fetch:
        log.info(f"--- Fetching [{mode}]: {ticker} ---")
        try:
            yf_data = fetch_yfinance(ticker)
            if not yf_data:
                log.error(f"No data returned for {ticker}")
                continue
            stock = existing_map.get(ticker, {"ticker": ticker})
            stock.update({
                "ticker": ticker,
                "fetchedAt": ts(),
                "calendarFetchedAt": ts(),
                "price": yf_data.get("price"),
                "volume": yf_data.get("volume"),
                "marketCap": yf_data.get("marketCap"),
                "sector": yf_data.get("sector"),
                "industry": yf_data.get("industry"),
                "calendar": yf_data.get("calendar", {}),
                "events": yf_data.get("events", {}),
                "dividends": yf_data.get("dividends", []),
                "annualIncome": yf_data.get("annualIncome", []),
                "quarterlyIncome": yf_data.get("quarterlyIncome", []),
                "annualBalance": yf_data.get("annualBalance", []),
                "quarterlyBalance": yf_data.get("quarterlyBalance", []),
                "annualCashflow": yf_data.get("annualCashflow", []),
                "quarterlyCashflow": yf_data.get("quarterlyCashflow", []),
            })
            existing_map[ticker] = stock
            last_fetched_tickers.add(ticker)
        except Exception as e:
            log.error(f"Fetch FAIL: {ticker} | {e}")

    gainers = fetch_daily_gainers()
    results = [existing_map[t] for t in watchlist if t in existing_map]
    results = process_watchlist(results)

    log.info(f"Generating recommendations...")
    recommendations = generate_recommendations(results)
    log.info("AI summaries skipped — run per ticker manually.")

    log.info(f"Total before save: {len(results)} | {[r['ticker'] for r in results]}")
    now_ts = ts()
    if mode == "all":
        op_timestamps["all"] = now_ts
    elif mode == "new":
        op_timestamps["new"] = now_ts
    out = load_json(OUTPUT_PATH, {})
    out.update({
        "watchlist": results,
        "dailyGainers": gainers.get("us", []),
        "dailyGainersCDN": gainers.get("cdn", []),
        "recommendations": recommendations,
        "lastUpdated": now_ts,
        "opTimestamps": {**out.get("opTimestamps", {}), **{k: v for k, v in op_timestamps.items() if v}},
    })
    save_json(OUTPUT_PATH, out)
    fetch_status = {"running": False, "message": f"Done! [{mode}] {len(tickers_to_fetch)} ticker(s) updated.", "operation": None}
    log.info("=== Fetch Complete ===")


def run_smart_refresh():
    global fetch_status, op_timestamps
    fetch_status = {"running": True, "message": "Smart refresh: checking what needs updating..."}
    log.info("=== Smart Refresh Started ===")

    existing = load_json(OUTPUT_PATH, {"watchlist": [], "dailyGainers": []})
    existing_map = reconcile_with_watchlist(
    {s["ticker"]: s for s in existing.get("watchlist", [])}
)

    tickers_needing_refresh = []
    refresh_plans = {}

    for ticker in watchlist:
        stock = existing_map.get(ticker, {"ticker": ticker})
        plan = check_what_needs_refresh(stock, None)
        if any([plan["price"], plan["quarterly"], plan["annual"], plan["calendar"]]):
            tickers_needing_refresh.append(ticker)
            refresh_plans[ticker] = plan

    if not tickers_needing_refresh:
        fetch_status = {"running": False, "message": "Smart refresh: everything up to date."}
        log.info("Smart refresh: nothing to update")
        return

    fetch_status = {"running": True, "message": f"Smart refresh: updating {len(tickers_needing_refresh)} ticker(s)..."}
    log.info(f"Smart refresh: {tickers_needing_refresh}")

    for ticker in tickers_needing_refresh:
        plan = refresh_plans[ticker]
        stock = existing_map.get(ticker, {"ticker": ticker})
        try:
            yf_data = plan.get("_freshData") or fetch_yfinance(ticker)
            if not yf_data:
                continue
            if plan["price"]:
                stock.update({
                    "fetchedAt": ts(),
                    "price": yf_data.get("price"),
                    "volume": yf_data.get("volume"),
                    "marketCap": yf_data.get("marketCap"),
                })
            if plan["quarterly"]:
                stock["quarterlyIncome"] = yf_data.get("quarterlyIncome", [])
                stock["quarterlyBalance"] = yf_data.get("quarterlyBalance", [])
                stock["quarterlyCashflow"] = yf_data.get("quarterlyCashflow", [])
            if plan["annual"]:
                stock["annualIncome"] = yf_data.get("annualIncome", [])
                stock["annualBalance"] = yf_data.get("annualBalance", [])
                stock["annualCashflow"] = yf_data.get("annualCashflow", [])
            if plan["calendar"]:
                stock["calendar"] = yf_data.get("calendar", {})
                stock["events"] = yf_data.get("events", {})
                stock["dividends"] = yf_data.get("dividends", [])
                stock["calendarFetchedAt"] = ts()
            existing_map[ticker] = stock
        except Exception as e:
            log.error(f"Smart refresh FAIL: {ticker} | {e}")

    results = list(existing_map.values())
    results = process_watchlist(results)

    gainers = fetch_daily_gainers()
    recommendations = generate_recommendations(results)
    log.info("Smart refresh: AI summaries skipped — run per ticker manually.")

    now_ts = ts()
    op_timestamps["smart"] = now_ts
    out = load_json(OUTPUT_PATH, {})
    out.update({
        "watchlist": results,
        "dailyGainers": gainers or existing.get("dailyGainers", []),
        "recommendations": recommendations,
        "lastUpdated": now_ts,
        "opTimestamps": {**out.get("opTimestamps", {}), **{k: v for k, v in op_timestamps.items() if v}},
    })
    save_json(OUTPUT_PATH, out)
    fetch_status = {"running": False, "message": f"Smart refresh done: {len(tickers_needing_refresh)} ticker(s) updated.", "operation": None}
    log.info("=== Smart Refresh Complete ===")

def reconcile_with_watchlist(existing_map):
    """Remove tickers from existing_map that are no longer in watchlist."""
    removed = [t for t in list(existing_map.keys()) if t not in watchlist]
    for t in removed:
        del existing_map[t]
        log.info(f"Reconcile: removed {t} (no longer in watchlist)")
    added = [t for t in watchlist if t not in existing_map]
    for t in added:
        existing_map[t] = {"ticker": t, "fetchedAt": None}
        log.info(f"Reconcile: added placeholder for {t}")
    return existing_map

@app.route("/fetch")
def trigger_fetch():
    if not fetch_status["running"]:
        thread = threading.Thread(target=run_fetch, args=(list(watchlist), "all"))
        thread.start()
    return redirect("/")


@app.route("/fetch/new")
def trigger_fetch_new():
    if not fetch_status["running"]:
        existing = load_json(OUTPUT_PATH, {"watchlist": []})
        existing_tickers = {s["ticker"] for s in existing.get("watchlist", [])}
        new_tickers = [t for t in watchlist if t not in existing_tickers]
        log.info(f"Fetch New: new={new_tickers}")
        thread = threading.Thread(target=run_fetch, args=(new_tickers or [], "new"))
        thread.start()
    return redirect("/")


@app.route("/fetch/prices")
def trigger_fetch_prices():
    if not fetch_status["running"]:
        thread = threading.Thread(target=run_price_refresh, args=("manual",))
        thread.start()
    return redirect("/")


@app.route("/fetch/smart")
def trigger_smart_refresh():
    if not fetch_status["running"]:
        thread = threading.Thread(target=run_smart_refresh)
        thread.start()
    return redirect("/")


@app.route("/fetch/ticker/<ticker>")
def trigger_fetch_ticker(ticker):
    if not fetch_status["running"] and ticker in watchlist:
        thread = threading.Thread(target=run_fetch, args=([ticker], "single"))
        thread.start()
    # return redirect("/")
    return "", 204

@app.route("/fetch/ticker/<ticker>/ai")
def trigger_fetch_ticker_ai(ticker):
    if not fetch_status["running"] and ticker in watchlist:
        thread = threading.Thread(target=run_ai_summary, args=(ticker,))
        thread.start()
    return redirect("/")

@app.route("/status")
def status():
    out = load_json(OUTPUT_PATH, {})
    return jsonify({
        **fetch_status,
        "opTimestamps": out.get("opTimestamps", {}),
        "lastPriceRefresh": out.get("lastPriceRefresh"),
    })

@app.route("/news/<ticker>")
def get_news(ticker):
    try:
        today_only = request.args.get("today") == "1"
        news_db = load_json(NEWS_PATH, {})
        news_entry = news_db.get(ticker, {})

        if needs_news_refresh(news_entry, today_only=today_only):
            all_news = fetch_news(ticker)
            if today_only:
                from datetime import date as dt_date
                today_str = str(dt_date.today())
                news_items = [n for n in all_news if n.get("pubDate", "").startswith(today_str)]
                news_entry["todayItems"] = news_items
                news_entry["todayFetchedAt"] = ts()
            else:
                news_entry["sevenDayItems"] = all_news
                news_entry["sevenDayFetchedAt"] = ts()
            news_db[ticker] = news_entry
            save_json(NEWS_PATH, news_db)
            log.info(f"News saved: {ticker} | today:{today_only}")
        else:
            news_items = news_entry.get("todayItems" if today_only else "sevenDayItems", [])
            log.info(f"News from cache: {ticker} | today:{today_only} | {len(news_items)} articles")

        news_items = news_entry.get("todayItems" if today_only else "sevenDayItems", [])
        news_items = _sanitize_news(news_items)

        existing = load_json(OUTPUT_PATH, {"watchlist": []})
        stock = next((s for s in existing.get("watchlist", []) if s["ticker"] == ticker), {})
        price_context = fetch_price_context(ticker)

        if not news_items:
            return jsonify({"error": "No news found", "items": [], "impact": None, "priceContext": price_context})

        impact = None
        try:
            impact = generate_news_impact(ticker, news_items, stock, price_context)
        except Exception as e:
            log.error(f"News impact generation FAIL: {ticker} | {e}")
            impact = {
                "overallSentiment": "neutral",
                "sentimentScore": 0,
                "marketConfirmation": "UNKNOWN",
                "summary": "AI analysis unavailable",
                "priceImpact": "Unknown",
                "keyThemes": [],
                "tradingImplication": "N/A",
                "watchFor": "N/A",
                "newsItems": []
            }

        impact_key = "todayImpact" if today_only else "sevenDayImpact"
        impact_ts_key = "todayImpactAt" if today_only else "sevenDayImpactAt"
        news_entry[impact_key] = impact
        news_entry[impact_ts_key] = ts()
        news_db[ticker] = news_entry
        save_json(NEWS_PATH, news_db)
        log.info(f"News impact saved: {ticker} | today:{today_only} | sentiment:{impact.get('overallSentiment')}")

        log.info(f"News route OK: {ticker} | items:{len(news_items)} sentiment:{impact.get('overallSentiment')}")
        return jsonify({
            "items": news_items,
            "impact": impact,
            "priceContext": price_context,
            "cached": not needs_news_refresh(news_entry, today_only)
        })
    except Exception as e:
        log.error(f"News route FAIL: {ticker} | {e}")
        return jsonify({"error": str(e), "items": [], "impact": None, "priceContext": {}})


@app.route("/news/cached-impact/<ticker>")
def get_cached_news_impact(ticker):
    try:
        news_db = load_json(NEWS_PATH, {})
        entry = news_db.get(ticker, {})
        result = {
            "sevenDay": {
                "impact": entry.get("sevenDayImpact"),
                "fetchedAt": entry.get("sevenDayImpactAt"),
            },
            "today": {
                "impact": entry.get("todayImpact"),
                "fetchedAt": entry.get("todayImpactAt"),
            }
        }
        log.info(f"Cached impact served: {ticker} | 7d:{bool(result['sevenDay']['impact'])} today:{bool(result['today']['impact'])}")
        return jsonify(result)
    except Exception as e:
        log.error(f"Cached impact FAIL: {ticker} | {e}")
        return jsonify({"sevenDay": {}, "today": {}})


@app.route("/")
def index():
    return render_template("index.html", watchlist=watchlist, status=fetch_status)


@app.route("/add", methods=["POST", "GET"])
def add_ticker():
    ticker = (request.form.get("ticker") or request.args.get("ticker") or "").upper().strip()
    if not ticker or ticker in watchlist:
        return redirect("/")
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            log.warning(f"Ticker validation FAIL: {ticker} — not found on yfinance")
            return redirect("/?error=invalid_ticker")
        watchlist.append(ticker)
        save_watchlist()
        log.info(f"Added ticker: {ticker}")
    except Exception as e:
        log.error(f"Ticker validation error: {ticker} | {e}")
    return redirect("/")


@app.route("/remove/<ticker>")
def remove_ticker(ticker):
    if ticker in watchlist:
        watchlist.remove(ticker)
        save_watchlist()
        log.info(f"Removed ticker: {ticker}")
    try:
        existing = load_json(OUTPUT_PATH, {"watchlist": [], "dailyGainers": []})
        existing["watchlist"] = [s for s in existing["watchlist"] if s["ticker"] != ticker]
        save_json(OUTPUT_PATH, existing)
        log.info(f"Removed {ticker} from analysis.json")
    except Exception as e:
        log.error(f"Remove from analysis FAIL: {ticker} | {e}")
    return redirect("/")


@app.route("/logs")
def view_logs():
    try:
        with open("logs/app.log", "r") as f:
            lines = f.readlines()
        count = len(lines)
        last = lines[-500:]
        return jsonify({"lines": [l.rstrip() for l in last], "total": count})
    except Exception as e:
        return jsonify({"lines": [], "total": 0, "error": str(e)})

@app.route("/logs/clear", methods=["POST"])
def clear_logs():
    try:
        with open("logs/app.log", "w") as f:
            f.write("")
        log.info("Log file cleared by user")
        return jsonify({"status": "cleared"})
    except Exception as e:
        log.error(f"Log clear FAIL: {e}")
        return jsonify({"error": str(e)})

@app.route("/data")
def get_data():
    try:
        data = load_json(OUTPUT_PATH, {"watchlist": [], "dailyGainers": []})
        return jsonify(data)
    except Exception as e:
        log.error(f"Data load FAIL: {e}")
        return jsonify({"watchlist": [], "dailyGainers": []})
    
from config import WATCHLIST, OUTPUT_PATH, NEWS_PATH, WATCHLIST_PATH, FOLLOWUP_PATH

@app.route("/followup/<ticker>/<event_name>")
def followup_plan(ticker, event_name):
    try:
        force = request.args.get("refresh") == "1"
        followup_db = load_json(FOLLOWUP_PATH, {})
        cache_key = f"{ticker}_{event_name}".replace(" ", "_")

        if not force and cache_key in followup_db:
            log.info(f"Followup from cache: {ticker} | {event_name}")
            return jsonify({**followup_db[cache_key], "cached": True})

        with open(OUTPUT_PATH, "r") as f:
            data = json.load(f)
        stock = next((s for s in data["watchlist"] if s["ticker"] == ticker), None)
        if not stock:
            return jsonify({"error": "Ticker not found"})

        plan = generate_followup(stock, event_name)
        plan["savedAt"] = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M %Z")
        plan["cached"] = False

        followup_db[cache_key] = plan
        save_json(FOLLOWUP_PATH, followup_db)
        log.info(f"Followup saved: {ticker} | {event_name}")
        return jsonify(plan)
    except Exception as e:
        log.error(f"Followup FAIL: {ticker} | {e}")
        return jsonify({"error": str(e)})

@app.route("/followup/check/<ticker>/<event_name>")
def followup_check(ticker, event_name):
    followup_db = load_json(FOLLOWUP_PATH, {})
    cache_key = f"{ticker}_{event_name}".replace(" ", "_")
    entry = followup_db.get(cache_key)
    return jsonify({"exists": entry is not None, "savedAt": entry.get("savedAt") if entry else None})

@app.route("/technical/<ticker>")
def technical_analysis(ticker):
    try:
        existing = load_json(OUTPUT_PATH, {"watchlist": []})
        stock = next((s for s in existing.get("watchlist", []) if s["ticker"] == ticker), {})
        rsi = stock.get("rsi14")
        bb = stock.get("bbPercent")
        log.info(f"Technical analysis: {ticker} | rsi:{rsi} bb:{bb}")

        if rsi is None and bb is None:
            return jsonify({"error": "No technical data. Run a price refresh first.", "ticker": ticker})

        def rsi_label(v):
            if v is None: return "Unknown", "neutral"
            if v < 30: return "Oversold", "bullish"
            if v > 70: return "Overbought", "bearish"
            if v < 45: return "Mildly Oversold", "mild-bullish"
            if v > 55: return "Mildly Overbought", "mild-bearish"
            return "Neutral", "neutral"

        def bb_label(v):
            if v is None: return "Unknown", "neutral"
            if v < 0: return "Below Lower Band", "bullish"
            if v > 1: return "Above Upper Band", "bearish"
            if v < 0.2: return "Near Lower Band", "mild-bullish"
            if v > 0.8: return "Near Upper Band", "mild-bearish"
            return "Mid-Range", "neutral"

        rsi_text, rsi_signal = rsi_label(rsi)
        bb_text, bb_signal = bb_label(bb)

        signals = [rsi_signal, bb_signal]
        bullish = signals.count("bullish") + signals.count("mild-bullish") * 0.5
        bearish = signals.count("bearish") + signals.count("mild-bearish") * 0.5

        if bullish > bearish:
            if bullish >= 2:
                verdict = "STRONG BUY WATCH"
                action = "Both indicators confirm oversold conditions. This is a potential bounce candidate. Watch for a reversal confirmation candle (e.g. green day on above-average volume) before entering. Set a stop below recent low."
            else:
                verdict = "MILD BUY WATCH"
                action = "One indicator suggests oversold but signals are mixed. Proceed cautiously. Wait for price to stabilize or show momentum before considering entry."
        elif bearish > bullish:
            if bearish >= 2:
                verdict = "CAUTION — OVERBOUGHT"
                action = "Both indicators confirm overbought conditions. Elevated pullback risk. Avoid chasing the price here. If you hold, consider tightening your stop-loss or taking partial profits."
            else:
                verdict = "MILD CAUTION"
                action = "One indicator suggests overbought. Not an immediate sell signal, but avoid adding to position at current levels. Monitor for signs of weakening momentum."
        else:
            verdict = "NEUTRAL"
            action = "Indicators show no strong directional bias. The stock is trading within normal range. No immediate action required — wait for a clearer signal before committing."

        rsi_str = f"RSI {rsi}" if rsi is not None else "RSI N/A"
        bb_str = f"BB%B {bb}" if bb is not None else "BB%B N/A"

        return jsonify({
            "ticker": ticker,
            "rsi14": rsi,
            "bbPercent": bb,
            "rsiLabel": rsi_text,
            "bbLabel": bb_text,
            "verdict": verdict,
            "action": action,
            "summary": f"{rsi_str} ({rsi_text}) · {bb_str} ({bb_text})",
        })
    except Exception as e:
        log.error(f"Technical analysis FAIL: {ticker} | {e}")
        return jsonify({"error": str(e), "ticker": ticker})



def run_macro_refresh():
    global fetch_status
    fetch_status = {"running": True, "message": "Fetching macro data...", "operation": "macro"}
    log.info("=== Macro Refresh Started ===")
    try:
        if not FRED_API_KEY or FRED_API_KEY == "your_fred_api_key_here":
            log.error("Macro refresh FAIL: FRED_API_KEY not set in config.py")
            fetch_status = {"running": False, "message": "Macro FAIL: FRED_API_KEY not set", "operation": None}
            return
        data = fetch_macro_data(FRED_API_KEY, NEWSAPI_KEY)
        now_ts = ts()
        data["fetchedAt"] = now_ts
        save_json(MACRO_PATH, data)
        fetch_status = {"running": False, "message": f"Macro updated: {now_ts}", "operation": None}
        log.info(f"=== Macro Refresh Complete: {now_ts} ===")
    except Exception as e:
        log.error(f"Macro refresh FAIL: {e}")
        fetch_status = {"running": False, "message": f"Macro FAIL: {e}", "operation": None}


@app.route("/macro")
def get_macro():
    data = load_json(MACRO_PATH, {})
    return jsonify(data)


@app.route("/macro/refresh", methods=["GET","POST"])
def macro_refresh():
    if fetch_status.get("running"):
        return jsonify({"error": "Another operation is running"}), 409
    t = threading.Thread(target=run_macro_refresh, daemon=True)
    t.start()
    log.info("Macro refresh triggered via UI")
    return jsonify({"status": "started"})


@app.route("/macro/ai", methods=["GET","POST"])
def macro_ai():
    try:
        data = load_json(MACRO_PATH, {})
        if not data:
            return jsonify({"error": "No macro data. Run a refresh first."})
        indicators = data.get("indicators", {})
        headlines  = data.get("headlines", [])
        fetched_at = data.get("fetchedAt", "unknown")

        # Build prompt for Ollama
        ind_lines = []
        for k, v in indicators.items():
            if v.get("value") is None:
                continue
            unit = v.get("unit","")
            chg  = f" (chg: {v['change']:+.2f}{unit})" if v.get("change") is not None else ""
            ind_lines.append(f"- {v['label']}: {v['value']}{unit}{chg} as of {v.get('date','?')}")

        headline_lines = [f"- {h['title']} ({h['source']})" for h in headlines[:8]]

        ind_block = "\n".join(ind_lines)
        hl_block  = "\n".join(headline_lines) if headline_lines else "None available"
        prompt = (
            "You are a macro-economic analyst. Based on the following current macro indicators and market headlines, "
            "provide a concise analysis of the current market environment. "
            "Focus on: (1) what these indicators signal for equity markets, "
            "(2) key risks and opportunities, "
            "(3) sectors likely to benefit or suffer. "
            "Keep the response under 250 words, structured with short paragraphs."
            "\n\nMACRO INDICATORS:\n" + ind_block +
            "\n\nRECENT HEADLINES:\n" + hl_block +
            "\n\nAnalysis:"
        )

        import requests as req
        resp = req.post("http://localhost:11434/api/generate",
            json={"model": "gemma2:9b", "prompt": prompt, "stream": False},
            timeout=120
        )
        result = resp.json().get("response", "").strip()
        now_ts = ts()

        # Save AI summary back to macro.json
        data["aiSummary"] = result
        data["aiSummaryAt"] = now_ts
        save_json(MACRO_PATH, data)

        log.info(f"Macro AI summary generated: {now_ts} | {len(result)} chars")
        return jsonify({"summary": result, "generatedAt": now_ts})
    except Exception as e:
        log.error(f"Macro AI FAIL: {e}")
        return jsonify({"error": str(e)})



def run_dream_scan(triggered_by="manual"):
    global fetch_status
    fetch_status = {"running": True, "message": "Running Dream Stock Scan...", "operation": "dream"}
    log.info(f"=== Dream Scan Started [{triggered_by}] ===")
    try:
        existing = load_json(OUTPUT_PATH, {"watchlist": [], "dailyGainers": [], "dailyGainersCDN": []})
        watchlist_tickers = [s["ticker"] for s in existing.get("watchlist", [])]
        us_gainers  = existing.get("dailyGainers", []) or []
        cdn_gainers = existing.get("dailyGainersCDN", []) or []
        gainer_tickers = [g["ticker"] for g in us_gainers + cdn_gainers if g.get("ticker")]
        results = fetch_dream_candidates(watchlist_tickers, gainer_tickers)
        now_ts = ts()
        results["scannedAt"] = now_ts
        save_json(DREAM_PATH, results)
        fetch_status = {"running": False, "message": f"Dream scan complete: {now_ts}", "operation": None}
        log.info(f"=== Dream Scan Complete: {now_ts} | {len(results.get('candidates',[]))} candidates ===")
    except Exception as e:
        log.error(f"Dream scan FAIL: {e}")
        fetch_status = {"running": False, "message": f"Dream scan FAIL: {e}", "operation": None}


@app.route("/dream")
def get_dream():
    data = load_json(DREAM_PATH, {})
    return jsonify(data)


@app.route("/dream/scan", methods=["GET", "POST"])
def dream_scan():
    if fetch_status.get("running"):
        return jsonify({"error": "Another operation is running"}), 409
    t = threading.Thread(target=run_dream_scan, args=("manual",), daemon=True)
    t.start()
    log.info("Dream scan triggered via UI")
    return jsonify({"status": "started"})


def _maybe_run_dream_scan():
    import time
    time.sleep(60)
    if fetch_status.get("running"):
        log.info("Dream auto-scan skipped — another operation running")
        return
    dream = load_json(DREAM_PATH, {})
    scanned_at = dream.get("scannedAt")
    if scanned_at:
        try:
            from datetime import datetime
            last = datetime.strptime(scanned_at[:16], "%Y-%m-%d %H:%M")
            diff = (datetime.now() - last).total_seconds() / 3600
            if diff < 20:
                log.info(f"Dream auto-scan skipped — last ran {diff:.1f}h ago")
                return
        except Exception:
            pass
    log.info("Dream auto-scan starting (stale or never run)")
    run_dream_scan("startup")


# Auto price refresh on startup
_startup_thread = threading.Thread(target=run_price_refresh, args=("startup",), daemon=True)
_startup_thread.start()
log.info("=== Startup price refresh triggered ===")
_dream_thread = threading.Thread(target=_maybe_run_dream_scan, daemon=True)
_dream_thread.start()

if __name__ == "__main__":
    app.run(debug=True, port=5050)