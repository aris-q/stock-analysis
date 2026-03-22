from flask import Flask, render_template, request, redirect, jsonify
import json, os, logging, threading
from config import WATCHLIST, OUTPUT_PATH, NEWS_PATH, WATCHLIST_PATH
from fetcher import fetch_yfinance, fetch_daily_gainers, fetch_news, fetch_price_context
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

fetch_status = {"running": False, "message": "Idle"}
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def sync_watchlist_to_analysis(existing_watchlist, watchlist):
    """Ensure all tickers in watchlist exist in analysis, never remove existing cards."""
    existing_map = {s["ticker"]: s for s in existing_watchlist}
    for ticker in watchlist:
        if ticker not in existing_map:
            log.info(f"Adding missing ticker to analysis: {ticker}")
            existing_map[ticker] = {"ticker": ticker, "fetchedAt": None}
    return existing_map


def run_fetch(tickers_to_fetch, mode="all"):
    global fetch_status, last_fetched_tickers
    fetch_status = {"running": True, "message": f"[{mode.upper()}] Fetching {len(tickers_to_fetch)} ticker(s)..."}
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

    fetch_status = {"running": True, "message": f"Generating AI summaries for {len(tickers_to_fetch)} ticker(s)..."}
    for stock in results:
        if stock["ticker"] in tickers_to_fetch:
            log.info(f"--- AI Summary: {stock['ticker']} ---")
            stock["aiSummary"] = generate_summary(stock)

    log.info(f"Generating recommendations...")
    recommendations = generate_recommendations(results)

    log.info(f"Total before save: {len(results)} | {[r['ticker'] for r in results]}")
    save_json(OUTPUT_PATH, {
        "watchlist": results,
        "dailyGainers": gainers.get("us", []),
        "dailyGainersCDN": gainers.get("cdn", []),
        "recommendations": recommendations,
        "lastUpdated": ts()
    })
    fetch_status = {"running": False, "message": f"Done! [{mode}] {len(tickers_to_fetch)} ticker(s) updated."}
    log.info("=== Fetch Complete ===")


def run_smart_refresh():
    global fetch_status
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

    fetch_status = {"running": True, "message": "Smart refresh: updating AI summaries..."}
    for stock in results:
        if stock["ticker"] in tickers_needing_refresh and refresh_plans.get(stock["ticker"], {}).get("ai"):
            log.info(f"AI update: {stock['ticker']}")
            stock["aiSummary"] = generate_summary(stock)

    gainers = fetch_daily_gainers()
    recommendations = generate_recommendations(results)

    save_json(OUTPUT_PATH, {
        "watchlist": results,
        "dailyGainers": gainers or existing.get("dailyGainers", []),
        "recommendations": recommendations,
        "lastUpdated": ts()
    })
    fetch_status = {"running": False, "message": f"Smart refresh done: {len(tickers_needing_refresh)} ticker(s) updated."}
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
    return redirect("/")

@app.route("/status")
def status():
    return jsonify(fetch_status)

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


@app.route("/add", methods=["POST"])
def add_ticker():
    ticker = request.form.get("ticker", "").upper().strip()
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
            lines = f.readlines()[-50:]
        return "<pre>" + "".join(lines) + "</pre>"
    except Exception as e:
        return f"No logs yet: {e}"

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

if __name__ == "__main__":
    app.run(debug=True, port=5050)