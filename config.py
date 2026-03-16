import os
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")

WATCHLIST = ["KGC", "GOLD", "NEM", "AEM"]

OUTPUT_PATH = "output/analysis.json"

LOG_FILE = "logs/app.log"
