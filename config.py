import os
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
WATCHLIST = ["KGC", "GOLD", "NEM", "AEM"]
OUTPUT_PATH = "output/analysis.json"
NEWS_PATH = "output/news.json"
WATCHLIST_PATH = "watchlist.json"
LOG_FILE = "logs/app.log"
FOLLOWUP_PATH = "output/followup.json"
FRED_API_KEY = os.getenv("FRED_API_KEY")
NEWSAPI_KEY  = os.getenv("NEWSAPI_KEY")
MACRO_PATH   = "output/macro.json"
TRADES_PATH  = "output/trades.json"
TRADE_CANDIDATES_PATH = "output/trade_candidates.json"
TRADES_AI_PATH = "output/trades_ai.json"
TRADE_AI_CANDIDATES_PATH = "output/trade_ai_candidates.json"
OLLAMA_URL   = "http://localhost:11434"
OLLAMA_MODEL = "gemma2:9b"
