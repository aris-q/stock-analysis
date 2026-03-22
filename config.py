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