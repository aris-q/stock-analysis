from flask import Flask, render_template, request, redirect, jsonify
import json
import os
import logging
import threading
from config import WATCHLIST, FMP_API_KEY, OUTPUT_PATH
from fetcher import fetch_yfinance, fetch_daily_gainers
from compute import process_watchlist
from ai_summary import generate_summary
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
EST = timezone(timedelta(hours=-5))

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

watchlist = list(WATCHLIST)
fetch_status = {"running": False, "message": "Idle"}
last_fetched_tickers = set()

# def run_fetch(tickers_to_fetch):
#     global fetch_status, last_fetched_tickers
#     fetch_status = {"running": True, "message": f"Fetching {len(tickers_to_fetch)} ticker(s)..."}
#     log.info(f"=== Fetch Started: {tickers_to_fetch} ===")

#     try:
#         with open(OUTPUT_PATH, "r") as f:
#             existing = json.load(f)
#         existing_watchlist = {s["ticker"]: s for s in existing.get("watchlist", [])}
#         existing_gainers = existing.get("dailyGainers", [])
#     except Exception:
#         existing_watchlist = {}
#         existing_gainers = []

#     for ticker in tickers_to_fetch:
#         log.info(f"--- Fetching: {ticker} ---")
#         yf_data = fetch_yfinance(ticker)
#         existing_watchlist[ticker] = {
#             "ticker": ticker,
#             "fetchedAt": datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M %Z"),
#             "price": yf_data.get("price") if yf_data else None,
#             "volume": yf_data.get("volume") if yf_data else None,
#             "marketCap": yf_data.get("marketCap") if yf_data else None,
#             "sector": yf_data.get("sector") if yf_data else None,
#             "industry": yf_data.get("industry") if yf_data else None,
#             "calendar": yf_data.get("calendar") if yf_data else {},
#             "events": yf_data.get("events") if yf_data else {},
#             "dividends": yf_data.get("dividends") if yf_data else [],
#             "annualIncome": yf_data.get("annualIncome") if yf_data else [],
#             "quarterlyIncome": yf_data.get("quarterlyIncome") if yf_data else [],
#             "annualBalance": yf_data.get("annualBalance") if yf_data else [],
#             "quarterlyBalance": yf_data.get("quarterlyBalance") if yf_data else [],
#             "annualCashflow": yf_data.get("annualCashflow") if yf_data else [],
#             "quarterlyCashflow": yf_data.get("quarterlyCashflow") if yf_data else [],
#         }
#         last_fetched_tickers.add(ticker)

#     gainers = fetch_daily_gainers()
#     results = [existing_watchlist[t] for t in watchlist if t in existing_watchlist]
#     results = process_watchlist(results)
#     results = enrich_with_ai(results)

#     log.info(f"Total results before save: {len(results)} | tickers: {[r['ticker'] for r in results]}")

#     with open(OUTPUT_PATH, "w") as f:
#         json.dump({
#             "watchlist": results,
#             "dailyGainers": gainers if gainers else existing_gainers,
#             "lastUpdated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
#         }, f, indent=2)

#     fetch_status = {"running": False, "message": f"Done! {len(tickers_to_fetch)} ticker(s) updated."}
#     log.info("=== Fetch Complete ===")
def run_fetch(tickers_to_fetch):
    global fetch_status, last_fetched_tickers
    fetch_status = {"running": True, "message": f"Fetching {len(tickers_to_fetch)} ticker(s)..."}
    log.info(f"=== Fetch Started: {tickers_to_fetch} ===")

    try:
        with open(OUTPUT_PATH, "r") as f:
            existing = json.load(f)
        existing_watchlist = {s["ticker"]: s for s in existing.get("watchlist", [])}
        existing_gainers = existing.get("dailyGainers", [])
    except Exception:
        existing_watchlist = {}
        existing_gainers = []

    for ticker in tickers_to_fetch:
        log.info(f"--- Fetching: {ticker} ---")
        yf_data = fetch_yfinance(ticker)
        existing_watchlist[ticker] = {
            "ticker": ticker,
            "fetchedAt": datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M %Z"),
            "price": yf_data.get("price") if yf_data else None,
            "volume": yf_data.get("volume") if yf_data else None,
            "marketCap": yf_data.get("marketCap") if yf_data else None,
            "sector": yf_data.get("sector") if yf_data else None,
            "industry": yf_data.get("industry") if yf_data else None,
            "calendar": yf_data.get("calendar") if yf_data else {},
            "events": yf_data.get("events") if yf_data else {},
            "dividends": yf_data.get("dividends") if yf_data else [],
            "annualIncome": yf_data.get("annualIncome") if yf_data else [],
            "quarterlyIncome": yf_data.get("quarterlyIncome") if yf_data else [],
            "annualBalance": yf_data.get("annualBalance") if yf_data else [],
            "quarterlyBalance": yf_data.get("quarterlyBalance") if yf_data else [],
            "annualCashflow": yf_data.get("annualCashflow") if yf_data else [],
            "quarterlyCashflow": yf_data.get("quarterlyCashflow") if yf_data else [],
        }
        last_fetched_tickers.add(ticker)

    gainers = fetch_daily_gainers()
    log.info(f"Daily gainers fetched: {len(gainers)}")

    results = [existing_watchlist[t] for t in watchlist if t in existing_watchlist]
    results = process_watchlist(results)

    fetch_status = {"running": True, "message": f"Generating AI summaries for {len(tickers_to_fetch)} ticker(s)..."}
    log.info("=== AI Summaries Started ===")
    for stock in results:
        if stock["ticker"] in tickers_to_fetch:
            log.info(f"--- AI Summary: {stock['ticker']} ---")
            stock["aiSummary"] = generate_summary(stock)
        else:
            log.info(f"--- AI Summary skipped (cached): {stock['ticker']} ---")

    log.info(f"Total results before save: {len(results)} | tickers: {[r['ticker'] for r in results]}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump({
            "watchlist": results,
            "dailyGainers": gainers if gainers else existing_gainers,
            "lastUpdated": datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M %Z")
        }, f, indent=2)

    fetch_status = {"running": False, "message": f"Done! {len(tickers_to_fetch)} ticker(s) updated."}
    log.info("=== Fetch Complete ===")

@app.route("/fetch")
def trigger_fetch():
    if not fetch_status["running"]:
        thread = threading.Thread(target=run_fetch, args=(list(watchlist),))
        thread.start()
    return redirect("/")


@app.route("/fetch/new")
def trigger_fetch_new():
    if not fetch_status["running"]:
        try:
            with open(OUTPUT_PATH, "r") as f:
                existing = json.load(f)
            existing_tickers = {s["ticker"] for s in existing.get("watchlist", [])}
        except Exception:
            existing_tickers = set()
        new_tickers = [t for t in watchlist if t not in existing_tickers]
        if not new_tickers:
            log.info("Fetch New: no new tickers found")
            return redirect("/")
        thread = threading.Thread(target=run_fetch, args=(new_tickers,))
        thread.start()
    return redirect("/")


@app.route("/fetch/ticker/<ticker>")
def trigger_fetch_ticker(ticker):
    if not fetch_status["running"] and ticker in watchlist:
        thread = threading.Thread(target=run_fetch, args=([ticker],))
        thread.start()
    return redirect("/")

@app.route("/")
def index():
    return render_template("index.html", watchlist=watchlist, status=fetch_status)


@app.route("/add", methods=["POST"])
def add_ticker():
    ticker = request.form.get("ticker", "").upper().strip()
    if ticker and ticker not in watchlist:
        watchlist.append(ticker)
        log.info(f"Added ticker: {ticker}")
    return redirect("/")


@app.route("/remove/<ticker>")
def remove_ticker(ticker):
    if ticker in watchlist:
        watchlist.remove(ticker)
        log.info(f"Removed ticker: {ticker}")
    return redirect("/")

@app.route("/status")
def status():
    return jsonify(fetch_status)


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
        with open(OUTPUT_PATH, "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        log.error(f"Data load FAIL: {e}")
        return jsonify({"watchlist": [], "dailyGainers": []})

if __name__ == "__main__":
    app.run(debug=True, port=5050)